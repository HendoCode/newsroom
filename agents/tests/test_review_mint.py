"""Mint service tests (D4/D11; domain model §1.14/§1.15).

Covers: internal keeps the editorial block; external strips it + adds the DRAFT banner + warns
(never blocks) on open GAPs/clearances; the piece↔Doc link + round metadata land in Mongo work-
state; round numbers increment; the not-in-review-stage / no-revision guards.
"""

from __future__ import annotations

import pytest

from app.models import Piece, PieceStage, ShareMode
from app.review.docs_client import DocRef
from app.review.errors import NoRevisionToMint, NotInReviewStage, UnsafeExternalShareError
from app.review.mint import ReviewMintService


class FakeDocsClient:
    def __init__(self) -> None:
        self.created: list[tuple[str, str, str]] = []
        self.parent_ids: list[str | None] = []
        self.shared: list[tuple[str, list[str] | None, str]] = []

    async def create_doc_from_html(
        self, title: str, html: str, *, description: str = "", parent_id: str | None = None
    ) -> DocRef:
        doc_id = f"doc-{len(self.created) + 1}"
        self.created.append((title, html, description))
        self.parent_ids.append(parent_id)
        return DocRef(doc_id=doc_id, url=f"https://docs.google.com/document/d/{doc_id}/edit")

    async def share_file(self, doc_id: str, *, emails: list[str] | None = None, role: str = "commenter") -> None:
        self.shared.append((doc_id, emails, role))


async def _piece(
    store,
    content,
    *,
    slug: str = "token-vs-storage",
    voice: str = "demo-mira",
    open_gaps: int = 0,
    open_clearances: int = 0,
    stage: PieceStage = PieceStage.review,
    with_revision: bool = True,
) -> Piece:
    latest_revision = None
    if with_revision:
        # The brain fixture's "seed brain" commit already committed draft.html verbatim — reuse
        # that existing revision sha rather than re-committing identical content (which would be
        # a no-op commit and raise NothingToCommit).
        history = content.revision_history(slug, max_count=1)
        latest_revision = history[0].sha
    piece = Piece(
        slug=slug,
        voice=voice,
        stage=stage,
        latest_revision=latest_revision,
        open_gaps=open_gaps,
        open_clearances=open_clearances,
    )
    return await store.pieces.insert(piece)


async def test_mint_internal_keeps_editorial_block_and_has_no_warnings(store, content_store):
    piece = await _piece(store, content_store)
    docs = FakeDocsClient()
    service = ReviewMintService(store, content_store, docs)

    result = await service.mint(piece.id, share_mode=ShareMode.internal)

    assert result.warnings == []
    assert result.round.round_number == 1
    assert result.round.doc.share_mode == ShareMode.internal
    html_sent = docs.created[0][1]
    assert 'class="editorial"' in html_sent
    assert "cmw-draft-banner" not in html_sent

    updated = await store.pieces.get(piece.id)
    assert updated.current_review_round_id == result.round.id


async def test_mint_external_with_open_clearances_hard_blocks(store, content_store):
    """Open clearances → hard block (409). The brain's feedback-intake.md says 'Never share
    externally while piece.md lists open clearances' — the webapp now enforces that."""
    piece = await _piece(store, content_store, open_gaps=0, open_clearances=1)
    service = ReviewMintService(store, content_store, FakeDocsClient())

    with pytest.raises(UnsafeExternalShareError, match="1 open clearance"):
        await service.mint(piece.id, share_mode=ShareMode.external)


async def test_mint_external_with_open_gaps_only_warns(store, content_store):
    """Open GAPs without clearances → warn only (D11 v1 — ordinary information gaps)."""
    piece = await _piece(store, content_store, open_gaps=3, open_clearances=0)
    docs = FakeDocsClient()
    service = ReviewMintService(store, content_store, docs)

    result = await service.mint(piece.id, share_mode=ShareMode.external)

    assert len(result.warnings) == 1
    assert "3 open GAP" in result.warnings[0]
    assert "clearance" not in result.warnings[0]
    html_sent = docs.created[0][1]
    assert 'class="editorial"' not in html_sent
    assert "DRAFT — not for external distribution" in html_sent


async def test_mint_external_with_both_gaps_and_clearances_hard_blocks(store, content_store):
    """Both open GAPs and clearances → hard block (clearances take priority)."""
    piece = await _piece(store, content_store, open_gaps=2, open_clearances=1)
    service = ReviewMintService(store, content_store, FakeDocsClient())

    with pytest.raises(UnsafeExternalShareError, match="1 open clearance"):
        await service.mint(piece.id, share_mode=ShareMode.external)


async def test_mint_external_with_nothing_open_has_no_warning(store, content_store):
    piece = await _piece(store, content_store, open_gaps=0, open_clearances=0)
    service = ReviewMintService(store, content_store, FakeDocsClient())

    result = await service.mint(piece.id, share_mode=ShareMode.external)

    assert result.warnings == []


async def test_mint_shares_per_reviewer_email(store, content_store):
    piece = await _piece(store, content_store)
    docs = FakeDocsClient()
    service = ReviewMintService(store, content_store, docs)

    await service.mint(piece.id, reviewer_emails=["a@x.com", "b@x.com"])

    # "writer", not "commenter" (cmw-reviewer-can-edit-doc) — reviewers edit the Doc directly.
    assert docs.shared[0] == ("doc-1", ["a@x.com", "b@x.com"], "writer")


async def test_mint_with_no_emails_shares_anyone_with_link(store, content_store):
    piece = await _piece(store, content_store)
    docs = FakeDocsClient()
    service = ReviewMintService(store, content_store, docs)

    await service.mint(piece.id)

    assert docs.shared[0] == ("doc-1", None, "writer")


async def test_mint_round_number_increments_across_rounds(store, content_store):
    piece = await _piece(store, content_store)
    service = ReviewMintService(store, content_store, FakeDocsClient())

    first = await service.mint(piece.id)
    second = await service.mint(piece.id)

    assert first.round.round_number == 1
    assert second.round.round_number == 2


async def test_mint_requires_review_stage(store, content_store):
    piece = await _piece(store, content_store, stage=PieceStage.council)
    service = ReviewMintService(store, content_store, FakeDocsClient())

    with pytest.raises(NotInReviewStage):
        await service.mint(piece.id)


async def test_mint_requires_a_committed_revision(store, content_store):
    piece = await _piece(store, content_store, with_revision=False)
    service = ReviewMintService(store, content_store, FakeDocsClient())

    with pytest.raises(NoRevisionToMint):
        await service.mint(piece.id)


async def test_mint_unknown_piece_raises_key_error(store, content_store):
    service = ReviewMintService(store, content_store, FakeDocsClient())

    with pytest.raises(KeyError):
        await service.mint("does-not-exist")


# --- cmw-drive-piece-folders ------------------------------------------------------------------


class FakeDriveClient:
    def __init__(self) -> None:
        self.folders_created: list[tuple[str, str]] = []

    async def find_or_create_folder(self, name: str, *, parent_id: str = "root"):
        from app.drive.folder import DriveFileRef

        self.folders_created.append((name, parent_id))
        return DriveFileRef(
            file_id="folder-root", url="https://drive.google.com/drive/folders/folder-root"
        )

    async def create_folder(self, name: str, *, parent_id: str):
        from app.drive.folder import DriveFileRef

        self.folders_created.append((name, parent_id))
        return DriveFileRef(file_id="folder-1", url="https://drive.google.com/drive/folders/folder-1")

    async def upload_file(self, name, content, mime_type, *, parent_id):  # pragma: no cover - unused
        raise NotImplementedError


async def test_mint_with_no_root_configured_leaves_the_doc_at_the_root(store, content_store):
    piece = await _piece(store, content_store)
    docs = FakeDocsClient()
    service = ReviewMintService(store, content_store, docs)

    await service.mint(piece.id)

    assert docs.parent_ids == [None]
    updated = await store.pieces.get(piece.id)
    assert updated.drive_folder_id is None


async def test_mint_with_a_named_root_configured_puts_the_doc_in_the_piece_folder(
    store, content_store
):
    piece = await _piece(store, content_store)
    docs = FakeDocsClient()
    drive_client = FakeDriveClient()
    service = ReviewMintService(
        store, content_store, docs, drive_client=drive_client, root_folder_name="content-machine"
    )

    await service.mint(piece.id)

    # Root folder first, then the piece folder parented under it.
    assert drive_client.folders_created == [
        ("content-machine", "root"),
        (piece.slug, "folder-root"),
    ]
    assert docs.parent_ids == ["folder-1"]
    updated = await store.pieces.get(piece.id)
    assert updated.drive_folder_id == "folder-1"

    # A second round on the same piece reuses the same folder (the name root is found, not
    # re-created, but the piece folder is reused by persisted pointer).
    await service.mint(piece.id)
    assert drive_client.folders_created == [
        ("content-machine", "root"),
        (piece.slug, "folder-root"),
    ]
    assert docs.parent_ids == ["folder-1", "folder-1"]


async def test_mint_falls_back_to_piece_md_for_brain_authored_piece(store, content_store):
    """Regression for the live 500 (2026-08-31): a brain-authored piece registered by
    app.brain_sync carries its content in piece.md, not draft.html, so its recorded
    latest_revision has no draft.html at that sha. Mint must fall back to the piece.md content
    section (the same seam app.piece_detail.draft_content_from_files uses), not raise the raw
    GitError up as an Internal Server Error."""
    slug = "amazon-quick-hendo"
    # Write a piece.md with a --- content section; NO draft.html. This is the brain-authored
    # direct-authored shape app.piece_md.piece_md_content_section parses.
    content_store.repo.write_text(
        f"drafts/{slug}/piece.md",
        "---\ntitle: Amazon Quick + Hendo\nvoice: demo-dana\n---\n\n# The seller playbook\n\nBody.\n",
    )
    sha = content_store.repo.commit([f"drafts/{slug}/piece.md"], "brain authored piece", author_name="b", author_email="b@x")
    piece = Piece(slug=slug, voice="demo-dana", stage=PieceStage.review, latest_revision=sha)
    piece = await store.pieces.insert(piece)
    docs = FakeDocsClient()
    service = ReviewMintService(store, content_store, docs)

    result = await service.mint(piece.id, share_mode=ShareMode.internal)

    assert result.round.round_number == 1
    html_sent = docs.created[0][1]
    assert "seller playbook" in html_sent
    # Brain-authored markdown content is wrapped in a full styled document before Drive import.
    assert "<!DOCTYPE html>" in html_sent
    assert "font-family: 'Helvetica Neue', Arial, sans-serif" in html_sent
