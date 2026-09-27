"""The publish flow: finalized → published, a HITL button press (v1 reversal of the original
"distribution is out of scope" design — see docs/design.md's D13 note and models/piece.py).

Mints durable, PUBLIC outputs from the piece's current final revision:

- branded HTML + PDF, uploaded to a plain public-read S3 bucket (:mod:`app.publish.storage`) under
  an immutable, per-publish key (``published/<slug>/<release>/...`` — never overwritten in place),
- a Google Doc snapshot of the same content, shared anyone-with-the-link/reader.

Reuses the exact rendering seams :class:`~app.render.step.FinalizeStep` uses — the editorial strip
(:mod:`app.render.editorial`), semantic extraction (:mod:`app.render.semantic`), brand tokens
(:mod:`app.render.brand`), and the versioned template (:mod:`app.render.template`) — never a second
implementation of that pipeline. It does NOT reuse the finalize step's own render output: that
render is documented as disposable/regenerable and instance-local (git-ignored, written straight to
the working tree), so it may not even exist on whichever container handles this request in a
multi-instance or since-redeployed setup. This service performs its own fresh render instead.

Google-Doc sharing reuses ``share_file`` — the exact call
:class:`~app.review.mint.ReviewMintService`'s ``ShareMode.external`` path uses — rather than
calling that service directly (it always mints a *review-round* Doc, which this must never create).
The "DRAFT — not for external distribution" banner that path also adds is deliberately NOT reused
here: it would be false on content that is genuinely, intentionally being published.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.derivatives.quality import derivative_publish_gate
from app.drive.folder import DriveFolderClient, DriveFolderError, PieceDriveFolders
from app.git.brain import GitBrain
from app.git.content import GitContentStore
from app.models import DocRef, Piece, PieceStage, ShareMode, is_released_stage, utcnow
from app.models.publication import PublicationRelease, ReleaseActor
from app.orchestration.machine import PieceMachine
from app.piece_detail import read_draft_content
from app.piece_md import ensure_doc_html
from app.publish.errors import (
    ApprovalInvalidated,
    DerivativeGateBlocked,
    NoRevisionToPublish,
    NotReleasableStage,
    PublishError,
)
from app.release.approval import approval_status
from app.publish.storage import PublishStorage, PublishStorageError
from app.render.brand import LogoFetchError, BrandTokens, derive_brand_tokens_safe, fetch_logo_data_uri
from app.render.editorial import strip_editorial_block
from app.render.pdf import PdfRenderer, PdfRenderError
from app.render.semantic import extract_semantic_body, extract_title
from app.render.template import TemplateStore, render_branded_html
from app.repositories import WorkStateStore
from app.review.docs_client import ReviewDocsClient

TEAM_VOICE_SLUG = "demo-dana"


@dataclass(frozen=True)
class PublishResult:
    piece: Piece
    warnings: list[str] = field(default_factory=list)


class PublishService:
    """Mints durable, public outputs and closes the ``finalized → published`` gate."""

    def __init__(
        self,
        store: WorkStateStore,
        content: GitContentStore,
        brain: GitBrain,
        template_store: TemplateStore,
        storage: PublishStorage | None,
        docs_client: ReviewDocsClient,
        machine: PieceMachine,
        *,
        pdf_renderer: PdfRenderer | None = None,
        drive_client: DriveFolderClient | None = None,
        root_folder_name: str = "",
    ) -> None:
        self.store = store
        self.content = content
        self.brain = brain
        self.template_store = template_store
        self.storage = storage
        self.docs_client = docs_client
        self.machine = machine
        self.pdf_renderer = pdf_renderer
        # cmw-drive-named-folder-scoping: unconfigured by default — the published Doc keeps
        # landing at the Drive root and no Drive copies of html/pdf are made, exactly as before
        # this ticket.
        self.drive_folders = PieceDriveFolders(store, drive_client, root_folder_name)

    def _brand_tokens(self, voice_slug: str) -> tuple[BrandTokens, list[str]]:
        """Brand tokens for ``voice_slug`` if it carries a visual identity, else fall back to
        the shared ``demo-dana`` pack, else render plain with a warning."""
        if voice_slug:
            pack = self.brain.read_voice(voice_slug)
            if pack.visual_identity:
                return derive_brand_tokens_safe(pack.visual_identity)
        pack = self.brain.read_voice(TEAM_VOICE_SLUG)
        if pack.visual_identity:
            return derive_brand_tokens_safe(pack.visual_identity)
        return derive_brand_tokens_safe(None)

    async def publish(self, piece_id: str, *, actor: str | None = None) -> PublishResult:
        """HUMAN AuthorizeRelease: mint durable public outputs and an immutable numbered
        Publication Release. Legal from ``finalized`` (first release, enters ``released``) or
        ``released`` (subsequent numbered release, stage unchanged). The machine never calls this.
        """
        piece = await self._get_piece(piece_id)
        stage = PieceStage(piece.stage)
        if stage != PieceStage.finalized and not is_released_stage(stage):
            raise NotReleasableStage(
                f"piece {piece_id!r} is not finalized or released (stage={piece.stage})"
            )
        if not piece.latest_revision:
            raise NoRevisionToPublish(f"piece {piece_id!r} has no committed revision to publish")
        # Grandfather: pieces that reached finalized before approved_revision existed. Stamp now
        # so a later canonical edit can still invalidate. New pieces are stamped by PieceMachine
        # when they enter finalized.
        if piece.approved_revision is None and stage == PieceStage.finalized:
            await self.store.pieces.update(
                piece_id,
                {"approved_revision": piece.latest_revision, "approved_at": utcnow()},
            )
            piece = await self._get_piece(piece_id)
        waivers = await self.store.trivial_edit_waivers.by_piece(piece_id)
        status = approval_status(
            approved_revision=piece.approved_revision,
            latest_revision=piece.latest_revision,
            waivers=waivers,
        )
        if not status.valid:
            raise ApprovalInvalidated(status.reason)

        # Derivative quality bar: a native derivative publishes only after clearing ITS OWN
        # destination-specific council at 9/10 against the revision about to ship, with no
        # universal hard gate (facts, safety) tripped. Anchors/legacy pieces pass through.
        gate = await derivative_publish_gate(self.store, piece)
        if not gate.cleared:
            raise DerivativeGateBlocked(
                f"derivative {piece_id!r} has not cleared its quality bar: " + "; ".join(gate.reasons)
            )

        if self.storage is None:
            raise PublishStorageError(
                "published-assets bucket is not configured (PUBLISHED_ASSETS_BUCKET)"
            )

        raw_html = self.content.try_read_revision(piece.slug, piece.latest_revision)
        if raw_html is None:
            raw_html = read_draft_content(self.content, piece.slug)
        if raw_html is None:
            raise NoRevisionToPublish(
                f"piece {piece_id!r} has no readable revision content to publish "
                f"(revision={piece.latest_revision})"
            )
        # Content safety (not part of what's left open to iterate later): the editorial/GAP block
        # must never reach a public artifact. Reuses the exact D11/D13 strip — never reimplemented.
        stripped = strip_editorial_block(raw_html)
        title = extract_title(stripped) or piece.title or piece.slug
        article_html = extract_semantic_body(stripped)

        tokens, brand_warnings = self._brand_tokens(piece.voice)
        template = self.template_store.read()
        rendered_at = utcnow()

        warnings: list[str] = list(brand_warnings)
        logo_src = await self._inline_logo(tokens, warnings)
        branded_html = render_branded_html(
            template,
            title=title,
            article_html=article_html,
            tokens_css=tokens.css_root_block,
            font_import_html=tokens.font_import_html,
            logo_src=logo_src,
            source_revision=piece.latest_revision,
            rendered_at=rendered_at.isoformat(),
        )

        # Immutable-key discipline: number from the PublicationRelease collection (not a
        # last-write-wins counter on Piece) so a later authorization only ever appends N+1.
        release = await self.store.releases.next_number(piece_id)
        base_key = f"published/{piece.slug}/{release}"
        html_url = await self.storage.put(
            f"{base_key}/branded.html",
            branded_html.encode("utf-8"),
            content_type="text/html; charset=utf-8",
        )

        pdf_url: str | None = None
        pdf_bytes: bytes | None = None
        if self.pdf_renderer is None:
            warnings.append("pdf skipped: no PdfRenderer configured")
        else:
            try:
                pdf_bytes = await self.pdf_renderer.render(branded_html)
                pdf_url = await self.storage.put(
                    f"{base_key}/branded.pdf", pdf_bytes, content_type="application/pdf"
                )
            except PdfRenderError as exc:
                warnings.append(f"pdf skipped: {exc}")

        description = (
            f"newsroom publish · piece {piece.slug} · revision {piece.latest_revision} · "
            f"release {release}"
        )
        # cmw-drive-piece-folders: publish's own re-rendered copies go in the piece folder's
        # `Published/` subfolder — never the finalize originals living alongside it in the piece
        # folder, moved or re-parented (Hendo's call: the folder should honestly show both what
        # was finalized and what actually shipped, which can differ). A no-op unless
        # GOOGLE_DRIVE_ROOT_FOLDER_NAME is configured — the Doc then lands at the Drive root exactly as
        # before this ticket, and no Drive copies of html/pdf are made.
        published_folder = await self.drive_folders.ensure_published_subfolder(piece)
        doc = await self.docs_client.create_doc_from_html(
            title,
            ensure_doc_html(article_html),
            description=description,
            parent_id=published_folder.file_id if published_folder else None,
        )
        # The same `share_file` call ShareMode.external goes through in app.review.mint — anyone
        # with the link may read, matching the bucket's own generally-public decision (Hendo, v1).
        await self.docs_client.share_file(doc.doc_id, emails=None, role="reader")

        drive_html_ref = None
        drive_pdf_ref = None
        if published_folder is not None and self.drive_folders.client is not None:
            try:
                drive_html_ref = await self.drive_folders.client.upload_file(
                    "branded.html",
                    branded_html.encode("utf-8"),
                    "text/html",
                    parent_id=published_folder.file_id,
                )
                await self.docs_client.share_file(drive_html_ref.file_id, emails=None, role="reader")
            except DriveFolderError as exc:
                warnings.append(f"drive html upload skipped: {exc}")
            if pdf_bytes is not None:
                try:
                    drive_pdf_ref = await self.drive_folders.client.upload_file(
                        "branded.pdf", pdf_bytes, "application/pdf", parent_id=published_folder.file_id
                    )
                    await self.docs_client.share_file(drive_pdf_ref.file_id, emails=None, role="reader")
                except DriveFolderError as exc:
                    warnings.append(f"drive pdf upload skipped: {exc}")

        changes: dict[str, object] = {
            "published_release": release,
            "published_html_url": html_url,
            "published_pdf_url": pdf_url,
            "published_doc": {
                "doc_id": doc.doc_id,
                "url": doc.url,
                "share_mode": ShareMode.external.value,
            },
            "published_at": rendered_at,
        }
        if drive_html_ref is not None:
            changes["published_drive_html"] = {"file_id": drive_html_ref.file_id, "url": drive_html_ref.url}
        if drive_pdf_ref is not None:
            changes["published_drive_pdf"] = {"file_id": drive_pdf_ref.file_id, "url": drive_pdf_ref.url}
        await self.store.pieces.update(piece_id, changes)
        await self.store.releases.insert(
            PublicationRelease(
                piece_id=piece_id,
                content_project_id=piece.content_project_id,
                release_number=release,
                revision=piece.latest_revision,
                authorized_by=ReleaseActor(
                    subject_id=actor or piece.owner or "unknown",
                    email=actor or piece.owner,
                ),
                authorized_at=rendered_at,
                html_url=html_url,
                pdf_url=pdf_url,
                doc=DocRef(
                    doc_id=doc.doc_id,
                    url=doc.url,
                    share_mode=ShareMode.external,
                ),
                warnings=list(warnings),
            )
        )
        # The literal stage flip is the machine's alone (see PieceMachine.publish) — only reached
        # once every external side effect above has already succeeded, so a failure here never
        # leaves the piece flipped with no real links. Subsequent authorizations from `released`
        # do not change stage (repeatable numbered releases).
        published_piece = await self.machine.publish(piece_id, actor=actor)
        return PublishResult(piece=published_piece, warnings=warnings)

    async def _inline_logo(self, tokens: BrandTokens, warnings: list[str]) -> str:
        """Best-effort base64-inline the logo (D13 self-contained discipline); on failure, warn and
        fall back to the remote URL rather than block the publish."""
        try:
            return await fetch_logo_data_uri(tokens.logo_url)
        except LogoFetchError as exc:
            warnings.append(f"logo inline failed, using remote URL: {exc}")
            return tokens.logo_url

    async def _get_piece(self, piece_id: str) -> Piece:
        piece = await self.store.pieces.get(piece_id)
        if piece is None:
            raise KeyError(f"no piece {piece_id!r}")
        return piece


@dataclass(frozen=True)
class UnpublishResult:
    piece: Piece
    warnings: list[str] = field(default_factory=list)


class UnpublishService:
    """Unpublish flow: flip published S3 objects + Drive Published/ subfolder to non-public (permissions only, never delete)."""

    def __init__(
        self,
        store: WorkStateStore,
        storage: PublishStorage | None,
        docs_client: ReviewDocsClient,
        drive_folders: PieceDriveFolders | None = None,
    ) -> None:
        self.store = store
        self.storage = storage
        self.docs_client = docs_client
        self.drive_folders = drive_folders

    async def unpublish(self, piece_id: str, *, actor: str | None = None) -> UnpublishResult:
        piece = await self._get_piece(piece_id)
        if self.storage is None:
            raise PublishStorageError(
                "published-assets bucket is not configured (PUBLISHED_ASSETS_BUCKET)"
            )
        warnings: list[str] = []
        # S3: construct keys from published_release if present; make_private is resilient to missing
        if piece.published_release > 0 and piece.slug:
            base_key = f"published/{piece.slug}/{piece.published_release}"
            for suffix in ("branded.html", "branded.pdf"):
                key = f"{base_key}/{suffix}"
                try:
                    await self.storage.make_private(key)
                except Exception as exc:  # already guarded inside make_private, but catch any
                    warnings.append(f"s3 {key} unpublish skipped: {exc}")
        # Drive: unshare the Published/ subfolder (if pointer exists on piece)
        if piece.drive_published_folder_id and self.docs_client is not None:
            try:
                await self.docs_client.unshare_public(piece.drive_published_folder_id)
            except Exception as exc:
                warnings.append(f"drive Published/ unshare skipped: {exc}")
        # Also unshare any published_drive_* files if recorded (belt-and-suspenders)
        for ref in (piece.published_drive_html, piece.published_drive_pdf):
            if ref is not None:
                try:
                    await self.docs_client.unshare_public(ref.file_id)
                except Exception as exc:
                    warnings.append(f"drive file {ref.file_id} unshare skipped: {exc}")
        # No stage change; piece stays published but artifacts are now private
        updated = await self.store.pieces.get(piece_id) or piece
        return UnpublishResult(piece=updated, warnings=warnings)

    async def _get_piece(self, piece_id: str) -> Piece:
        piece = await self.store.pieces.get(piece_id)
        if piece is None:
            raise KeyError(f"no piece {piece_id!r}")
        return piece
