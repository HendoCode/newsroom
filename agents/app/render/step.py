"""The finalize batch step (D13, Item 5; domain model §1.19 BrandedTemplate & BrandedRender).

Turns the piece's current semantic ``draft.html`` revision into the branded distribution outputs.
A pure render — **no LLM call**. Runs in the ``finalizing`` stage;
:class:`~app.orchestration.machine.PieceMachine` already owns advancing ``finalizing → finalized``
on this step's success (§1.9) — this step only does the one stage's actual work, per the
:class:`~app.orchestration.steps.BatchStep` seam.

Pipeline (verbatim from the settled Item 5 mechanism):

1. Read the piece's current ``draft.html`` (the semantic master, D4/D13) via ``ctx.content``.
2. Strip the trailing editorial/GAP block — the SAME shared routine a future D11 external-share
   ticket reuses (:mod:`app.render.editorial`).
3. Extract the semantic title + body content (:mod:`app.render.semantic`, stdlib-only).
4. Derive brand tokens from ``demo-dana/visual-identity.md`` (the single source of truth — never
   duplicated, Item 5) via ``ctx.brain`` (:mod:`app.render.brand`).
5. Inject content + tokens into the versioned branded template (:mod:`app.render.template` — Git is
   the versioning, same store as the brain/content; Item 5 rejected a second Mongo scheme).
6. Render branded HTML → PDF via headless Chromium (:mod:`app.render.pdf` — from the SAME HTML, so
   the two match) and/or export a clean Google Doc (:mod:`app.render.docs_export`) — whichever
   ``formats`` were requested (use case J: outputs are "selectable at finalize").
7. Record source revision + template version on every output: a visible footer line on the branded
   HTML/PDF, and the Drive file ``description`` on the Doc — reproducible re-render, never a second
   store-of-record (BrandedRender is disposable, domain model §1.19). The Doc *link* itself is
   recorded on the :class:`~app.models.Piece` (``final_doc``), per design.md's "the system records
   the final piece and its final Google-Doc link" (use case G).

A missing/failing renderer for one requested format **warns and skips that format** rather than
failing the whole job (mirrors Item 4's "one editor's failure completes-with-gap, never aborts the
whole council") — only a run that produces *zero* of its requested formats is a real failure.

``formats`` default to all three (:data:`ALL_FORMATS`); ``ctx.job.formats`` narrows a specific run
to a subset when set (use case J), without requiring this step to own any HTTP-layer plumbing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.drive.folder import DriveFileRef, DriveFolderClient, DriveFolderError, PieceDriveFolders
from app.git.content import GitContentStore
from app.llm.pricing import Usage
from app.models import JobType
from app.piece_md import ensure_doc_html
from app.orchestration.retry import PermanentStepError
from app.orchestration.steps import BatchStep, StepContext, StepResult
from app.piece_detail import read_draft_content
from app.render.brand import BrandTokens, LogoFetchError, derive_brand_tokens_safe, fetch_logo_data_uri
from app.render.docs_export import DocRef, DocsExportError, GoogleDocsClient
from app.render.editorial import strip_editorial_block
from app.render.pdf import PdfRenderer, PdfRenderError
from app.render.semantic import extract_semantic_body, extract_title
from app.render.template import TemplateStore, render_branded_html

ALL_FORMATS: tuple[str, ...] = ("html", "pdf", "doc")
TEAM_VOICE_SLUG = "demo-dana"


@dataclass(frozen=True)
class FinalizeOutputs:
    """What one finalize run produced — the disposable BrandedRender (domain model §1.19)."""

    source_revision: str
    template_version: str
    rendered_at: str
    branded_html: str | None = None
    pdf_bytes: bytes | None = None
    doc: DocRef | None = None
    # The Drive-side copies of the same html/pdf (cmw-drive-piece-folders) — `None` whenever no
    # Shared Drive folder is configured/available, exactly like `doc` is `None` when "doc" wasn't
    # requested or the Docs client is unset.
    drive_html: DriveFileRef | None = None
    drive_pdf: DriveFileRef | None = None
    warnings: list[str] = field(default_factory=list)


class FinalizeStep(BatchStep):
    job_type = JobType.finalize

    def __init__(
        self,
        *,
        template_store: TemplateStore,
        pdf_renderer: PdfRenderer | None = None,
        docs_client: GoogleDocsClient | None = None,
        default_formats: tuple[str, ...] = ALL_FORMATS,
        drive_client: DriveFolderClient | None = None,
        root_folder_name: str = "",
    ) -> None:
        self.template_store = template_store
        self.pdf_renderer = pdf_renderer
        self.docs_client = docs_client
        self.default_formats = default_formats
        # cmw-drive-named-folder-scoping: both default to "unconfigured" (no drive_client, blank
        # name), which makes every call below a no-op — the exact pre-ticket behavior.
        self.drive_client = drive_client
        self.root_folder_name = root_folder_name

    def _brand_tokens(self, brain, voice_slug: str) -> tuple[BrandTokens, list[str]]:
        """Brand tokens for ``voice_slug`` if it carries a visual identity, else fall back to
        the shared ``demo-dana`` pack, else render plain with a warning."""
        if voice_slug:
            pack = brain.read_voice(voice_slug)
            if pack.visual_identity:
                return derive_brand_tokens_safe(pack.visual_identity)
        pack = brain.read_voice(TEAM_VOICE_SLUG)
        if pack.visual_identity:
            return derive_brand_tokens_safe(pack.visual_identity)
        return derive_brand_tokens_safe(None)

    async def run(self, ctx: StepContext) -> StepResult:
        await ctx.beat()
        if ctx.piece is None:
            raise ValueError("finalize requires a piece")
        if ctx.content is None:
            raise ValueError("finalize requires the Git content store")
        if ctx.brain is None:
            raise ValueError("finalize requires the Git brain (for visual-identity.md)")

        piece = ctx.piece
        slug = piece.slug
        requested = tuple(ctx.job.formats) if ctx.job.formats else self.default_formats
        unknown = set(requested) - set(ALL_FORMATS)
        if unknown:
            raise ValueError(f"unknown finalize format(s) {sorted(unknown)}; expected {ALL_FORMATS}")

        warnings: list[str] = []

        raw_draft = read_draft_content(ctx.content, slug)
        if raw_draft is None:
            raise PermanentStepError(
                f"finalize: piece {slug!r} has no draft.html or readable piece.md content"
            )
        stripped = strip_editorial_block(raw_draft)
        title = extract_title(stripped) or slug
        article_html = extract_semantic_body(stripped)

        tokens, brand_warnings = self._brand_tokens(ctx.brain, piece.voice)
        warnings.extend(brand_warnings)

        # A brain with no branded template (the neutral demo brain) degrades to the built-in plain
        # template + a warning rather than failing the job (same posture as the brand tokens above).
        template, template_warnings = self.template_store.read_or_plain()
        warnings.extend(template_warnings)
        source_revision = piece.latest_revision or _fallback_revision(ctx.content, slug)
        rendered_at = datetime.now(UTC).isoformat()

        await ctx.beat()
        logo_src = await self._inline_logo(tokens, warnings)

        branded_html = render_branded_html(
            template,
            title=title,
            article_html=article_html,
            tokens_css=tokens.css_root_block,
            font_import_html=tokens.font_import_html,
            logo_src=logo_src,
            source_revision=source_revision,
            rendered_at=rendered_at,
        )

        # cmw-drive-named-folder-scoping: a no-op (`None`) unless GOOGLE_DRIVE_ROOT_FOLDER_NAME is
        # configured — constructed fresh per run since FinalizeStep, unlike
        # ReviewMintService/PublishService, is built once at boot with no `store` available yet
        # (only `ctx.store`, per run).
        piece_folders = PieceDriveFolders(ctx.store, self.drive_client, self.root_folder_name)
        folder = await piece_folders.ensure_piece_folder(piece)

        pdf_bytes, doc, drive_html, drive_pdf = await self._render_requested(
            requested,
            branded_html=branded_html,
            title=title,
            article_html=article_html,
            source_revision=source_revision,
            template_version=template.version,
            rendered_at=rendered_at,
            folder=folder,
            warnings=warnings,
        )

        made_html = "html" in requested
        made_pdf = pdf_bytes is not None
        made_doc = doc is not None
        produced = [
            fmt for fmt, present in (("html", made_html), ("pdf", made_pdf), ("doc", made_doc)) if present
        ]
        if not produced:
            raise PermanentStepError(
                f"finalize produced no outputs for requested formats {requested}: {warnings}"
            )

        outputs = FinalizeOutputs(
            source_revision=source_revision,
            template_version=template.version,
            rendered_at=rendered_at,
            branded_html=branded_html if "html" in requested else None,
            pdf_bytes=pdf_bytes,
            doc=doc,
            drive_html=drive_html,
            drive_pdf=drive_pdf,
            warnings=warnings,
        )
        self._persist_files(ctx.content, slug, outputs)
        await self._persist_piece_state(ctx, piece.id, outputs)

        notes = [f"finalize {slug}: produced {', '.join(produced)} (template {template.version})"]
        notes.extend(outputs.warnings)
        return StepResult(usage=Usage(), notes=notes)

    # --- internals --------------------------------------------------------------------------

    async def _inline_logo(self, tokens: BrandTokens, warnings: list[str]) -> str:
        """Best-effort base64-inline the logo (D13 self-contained discipline); on failure, warn and
        fall back to the remote URL rather than block the render (§5 "warns, does not block")."""
        try:
            return await fetch_logo_data_uri(tokens.logo_url)
        except LogoFetchError as exc:
            warnings.append(f"logo inline failed, using remote URL: {exc}")
            return tokens.logo_url

    async def _render_requested(
        self,
        requested: tuple[str, ...],
        *,
        branded_html: str,
        title: str,
        article_html: str,
        source_revision: str,
        template_version: str,
        rendered_at: str,
        folder: DriveFileRef | None,
        warnings: list[str],
    ) -> tuple[bytes | None, DocRef | None, DriveFileRef | None, DriveFileRef | None]:
        pdf_bytes: bytes | None = None
        doc: DocRef | None = None
        drive_html: DriveFileRef | None = None
        drive_pdf: DriveFileRef | None = None

        if "pdf" in requested:
            if self.pdf_renderer is None:
                warnings.append("pdf skipped: no PdfRenderer configured")
            else:
                try:
                    pdf_bytes = await self.pdf_renderer.render(branded_html)
                except PdfRenderError as exc:
                    warnings.append(f"pdf skipped: {exc}")

        if "doc" in requested:
            if self.docs_client is None:
                warnings.append("doc skipped: no GoogleDocsClient configured")
            else:
                description = (
                    f"newsroom finalize · revision {source_revision} · "
                    f"template {template_version} · rendered {rendered_at}"
                )
                try:
                    doc = await self.docs_client.create_doc_from_html(
                        title,
                        ensure_doc_html(article_html),
                        description=description,
                        parent_id=folder.file_id if folder else None,
                    )
                except DocsExportError as exc:
                    warnings.append(f"doc skipped: {exc}")

        # cmw-drive-piece-folders: real, unconverted text/html/application/pdf uploads into the
        # piece's folder — a no-op whenever no folder is available (Shared Drive unconfigured) or
        # no drive_client was wired. A failed upload warns and skips, same "one output's failure
        # completes-with-gap" discipline as pdf/doc above — the render itself already succeeded.
        if folder is not None and self.drive_client is not None:
            if "html" in requested:
                try:
                    drive_html = await self.drive_client.upload_file(
                        "branded.html", branded_html.encode("utf-8"), "text/html", parent_id=folder.file_id
                    )
                except DriveFolderError as exc:
                    warnings.append(f"drive html upload skipped: {exc}")
            if "pdf" in requested and pdf_bytes is not None:
                try:
                    drive_pdf = await self.drive_client.upload_file(
                        "branded.pdf", pdf_bytes, "application/pdf", parent_id=folder.file_id
                    )
                except DriveFolderError as exc:
                    warnings.append(f"drive pdf upload skipped: {exc}")

        return pdf_bytes, doc, drive_html, drive_pdf

    def _persist_files(self, content: GitContentStore, slug: str, outputs: FinalizeOutputs) -> None:
        """Write the disposable render to the piece's (git-ignored) ``finalized/`` folder —
        NEVER committed (D13: the branded render is disposable, not a system-of-record, §1.19)."""
        out_dir = _finalized_dir(content, slug)
        out_dir.mkdir(parents=True, exist_ok=True)
        if outputs.branded_html is not None:
            (out_dir / "branded.html").write_text(outputs.branded_html, encoding="utf-8")
        if outputs.pdf_bytes is not None:
            (out_dir / "branded.pdf").write_bytes(outputs.pdf_bytes)
        if outputs.doc is not None:
            (out_dir / "google-doc.json").write_text(
                json.dumps(
                    {
                        "doc_id": outputs.doc.doc_id,
                        "url": outputs.doc.url,
                        "source_revision": outputs.source_revision,
                        "template_version": outputs.template_version,
                        "rendered_at": outputs.rendered_at,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

    async def _persist_piece_state(self, ctx: StepContext, piece_id: str | None, outputs: FinalizeOutputs) -> None:
        """Record the final Doc link + render provenance on the Piece (design.md use case G: "the
        system records the final piece and its final Google-Doc link"). Only touches ``final_doc``
        when this run actually produced one, so a formats-subset re-render never clobbers an
        earlier round's recorded Doc link with ``None``."""
        assert piece_id is not None
        changes: dict[str, object] = {
            "final_template_version": outputs.template_version,
            "final_rendered_at": datetime.fromisoformat(outputs.rendered_at).replace(tzinfo=None),
        }
        if outputs.doc is not None:
            changes["final_doc"] = {"doc_id": outputs.doc.doc_id, "url": outputs.doc.url}
        if outputs.drive_html is not None:
            changes["final_drive_html"] = {"file_id": outputs.drive_html.file_id, "url": outputs.drive_html.url}
        if outputs.drive_pdf is not None:
            changes["final_drive_pdf"] = {"file_id": outputs.drive_pdf.file_id, "url": outputs.drive_pdf.url}
        await ctx.store.pieces.update(piece_id, changes)


def _finalized_dir(content: GitContentStore, slug: str) -> Path:
    """The (git-ignored) output folder for a piece's disposable finalize render — computed from
    only ``content``'s public ``prefix``/``repo`` so this module never reaches into its internals."""
    parts = [content.prefix, "drafts", slug, "finalized"] if content.prefix else ["drafts", slug, "finalized"]
    return content.repo.abspath("/".join(parts))


def _fallback_revision(content: GitContentStore, slug: str) -> str:
    """If ``Piece.latest_revision`` is unset, fall back to the Git history head for the draft."""
    history = content.revision_history(slug, max_count=1)
    return history[0].sha if history else "unknown"
