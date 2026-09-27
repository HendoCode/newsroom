"""Mint a Google Doc from a frozen revision for one review round (D4/D11; domain model §1.14/§1.15).

"Mint Google Doc ▾: internal | external — external strips the editorial block, adds the DRAFT
banner. Clearance risks hard-block (engine/feedback-intake.md: "Never share externally while
`piece.md` lists open clearances"); ordinary information gaps warn only (D11). A round is born
here: the current committed Revision (Git, canonical) is frozen as ``minted_from_revision``,
pushed to a transient Doc, shared, and the round + piece↔Doc link are recorded in Mongo work-state
(§1.14 "Store owner: Mongo work-state") — the piece-detail screen already reads ``ReviewRound``
straight off the store (``app/piece_detail.py:_review_round_out``), so persisting this record IS
the integration point.

Two versions (feedback-intake.md's "hard guardrail"):

- **internal** — keep the editorial block; it tells colleagues what's still pending.
- **external** — strip the editorial block + add a "DRAFT — not for external distribution" banner.
  The webapp hard-blocks when open clearances (disclosure/clearance risk) remain; ordinary
  information gaps are warned-only (D11 v1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.drive.folder import DriveFolderClient, PieceDriveFolders
from app.git.content import GitContentStore
from app.models import DocRef, Piece, PieceStage, ReviewRound, ReviewRoundStatus, ShareMode, utcnow
from app.piece_md import ensure_doc_html
from app.render.editorial import strip_editorial_block
from app.repositories import WorkStateStore
from app.review.docs_client import ReviewDocsClient
from app.review.errors import NoRevisionToMint, NotInReviewStage, UnsafeExternalShareError

_BODY_OPEN_RE = re.compile(r"(<body\b[^>]*>)", re.IGNORECASE)
# The exact text of the DRAFT banner (see _add_draft_banner) — exposed so app.review.collect can
# recognize and drop the banner block from a diff base. Needed because the banner is authored as a
# non-block <div> (so it never becomes a Block on our own reconstructed "original" side), but
# Drive's HTML-to-Docs conversion turns it into a real <p> on the exported "current" side
# (confirmed live, cmw-phantom-edits-from-doc-roundtrip) — a structural mismatch a class/tag match
# can't paper over, since the "cmw-draft-banner" class itself does not survive the round trip
# either. Matching on this exact, never-organically-occurring text is the only stable handle left.
DRAFT_BANNER_TEXT = "DRAFT — not for external distribution"
_DRAFT_BANNER = (
    '<div class="cmw-draft-banner" '
    'style="background:#fef3c7;color:#78350f;padding:12px 16px;font-weight:600;'
    'border-bottom:2px solid #f59e0b;">'
    f"{DRAFT_BANNER_TEXT}"
    "</div>"
)


def _add_draft_banner(html: str) -> str:
    if _BODY_OPEN_RE.search(html):
        return _BODY_OPEN_RE.sub(lambda m: m.group(1) + _DRAFT_BANNER, html, count=1)
    return _DRAFT_BANNER + html


def render_for_share_mode(html: str, share_mode: ShareMode) -> str:
    """The exact transform applied to a frozen revision's HTML before it becomes a Doc's content:
    internal keeps the editorial block verbatim; external strips it and adds the DRAFT banner
    (D11). This is the single source of truth for "what actually got uploaded" — :mod:`app.review.
    collect` reuses it to reconstruct a round's diff base, instead of assuming a strip that in
    reality only ever happens on an external round (cmw-internal-round-editorial-diff-asymmetry:
    the two used to disagree, since ``diff_edits`` stripped the Git side unconditionally while an
    internal Doc genuinely keeps the block, so every internal round read its own editorial notes as
    reviewer-added content)."""
    if ShareMode(share_mode) == ShareMode.external:
        return _add_draft_banner(strip_editorial_block(html))
    return html


@dataclass(frozen=True)
class MintResult:
    round: ReviewRound
    warnings: list[str] = field(default_factory=list)


class ReviewMintService:
    """Mints internal/external review Docs and records the round + piece↔Doc link in Mongo."""

    def __init__(
        self,
        store: WorkStateStore,
        content: GitContentStore,
        docs_client: ReviewDocsClient | None,
        *,
        drive_client: DriveFolderClient | None = None,
        root_folder_name: str = "",
    ) -> None:
        self.store = store
        self.content = content
        self.docs_client = docs_client
        # cmw-drive-named-folder-scoping: unconfigured by default (no-op — every round Doc lands
        # loose at the Drive root exactly as before this ticket).
        self.drive_folders = PieceDriveFolders(store, drive_client, root_folder_name)

    async def mint(
        self,
        piece_id: str,
        *,
        share_mode: ShareMode = ShareMode.internal,
        reviewer_emails: list[str] | None = None,
    ) -> MintResult:
        piece = await self._get_piece(piece_id)
        if PieceStage(piece.stage) != PieceStage.review:
            raise NotInReviewStage(
                f"piece {piece_id!r} is not in the review stage (stage={piece.stage})"
            )
        if not piece.latest_revision:
            raise NoRevisionToMint(f"piece {piece_id!r} has no committed revision to mint")

        raw_html = self.content.try_read_revision(piece.slug, piece.latest_revision)
        if raw_html is None:
            # Brain-authored direct-authored piece: its content lives in ``piece.md``'s content
            # section, not ``draft.html`` — same fallback ``app.piece_detail.read_draft_content``
            # already uses. Resolve it the same way rather than erroring on a mintable piece.
            from app.piece_detail import draft_content_from_files

            raw_html = draft_content_from_files(self.content.read_piece_files(piece.slug))
        if raw_html is None:
            raise NoRevisionToMint(
                f"piece {piece_id!r} has no readable revision content to mint "
                f"(revision={piece.latest_revision})"
            )
        share_mode = ShareMode(share_mode)
        warnings: list[str] = []
        html = render_for_share_mode(raw_html, share_mode)
        if share_mode == ShareMode.external:
            if piece.open_clearances:
                raise UnsafeExternalShareError(
                    f"external share blocked: {piece.open_clearances} open clearance(s) — "
                    f"a name, figure, or number still needs owner sign-off before it can be "
                    f"shared externally (engine/feedback-intake.md: 'Never share externally "
                    f"while piece.md lists open clearances'). Resolve these first, then re-mint."
                )
            if piece.open_gaps:
                warnings.append(
                    f"external share with {piece.open_gaps} open GAP(s) — proceeding "
                    f"(warns, does not block, D11)"
                )

        folder = await self.drive_folders.ensure_piece_folder(piece)
        if self.docs_client is None:
            warnings.append(
                "review Doc skipped: Google Docs OAuth credentials not configured"
            )
            doc = DocRef(share_mode=share_mode)
        else:
            title = piece.title or piece.slug
            description = (
                f"newsroom review round · piece {piece.slug} · revision {piece.latest_revision}"
            )
            doc = await self.docs_client.create_doc_from_html(
                title, ensure_doc_html(html), description=description, parent_id=folder.file_id if folder else None
            )
            # "writer", not "commenter" (Hendo, cmw-reviewer-can-edit-doc): reviewers must be able to
            # edit the Doc directly, not just comment — voice stays authoritative for the prose either
            # way (see app.review.step._propose_edit_lessons), so widening this is safe. Uniform across
            # both share modes, matching the one-line ask; never touches app.publish.service's separate
            # role="reader" grant for the DIFFERENT (published, not review) artifact.
            await self.docs_client.share_file(doc.doc_id, emails=reviewer_emails, role="writer")

        round_number = await self._next_round_number(piece_id)
        round_ = ReviewRound(
            piece_id=piece_id,
            round_number=round_number,
            minted_from_revision=piece.latest_revision,
            doc=DocRef(doc_id=doc.doc_id, url=doc.url, share_mode=share_mode),
            opened_at=utcnow(),
            status=ReviewRoundStatus.open,
        )
        stored = await self.store.review_rounds.insert(round_)
        assert stored.id is not None
        await self.store.pieces.update(piece_id, {"current_review_round_id": stored.id})
        return MintResult(round=stored, warnings=warnings)

    async def _next_round_number(self, piece_id: str) -> int:
        existing = await self.store.review_rounds.by_piece(piece_id)
        return (max((r.round_number for r in existing), default=0)) + 1

    async def _get_piece(self, piece_id: str) -> Piece:
        piece = await self.store.pieces.get(piece_id)
        if piece is None:
            raise KeyError(f"no piece {piece_id!r}")
        return piece
