"""Brain drafts view (cmw-drafts-view): read-only reading surface for brain-authored drafts.

Covers ``GET /api/brain/drafts`` (list) and ``GET /api/brain/drafts/{slug}`` (read), plus the
additive Google-Doc link lookup when a matching synced Piece exists. Uses the fixture-brain temp
clone, mongomock work-state, and ASGI transport — no Mongo server, no network.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.git import GitContentStore
from app.main import app
from app.models.piece import Piece, PieceStage
from app.repositories import WorkStateStore


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def store() -> WorkStateStore:
    return WorkStateStore(AsyncMongoMockClient()["drafts_test"])


class _StateGuard:
    """Save/restore the app.state attrs these route tests touch."""

    def __enter__(self) -> None:
        self._saved = {k: getattr(app.state, k, None) for k in ("work_state", "git_content")}

    def __exit__(self, *exc: object) -> None:
        for key, value in self._saved.items():
            if value is None:
                try:
                    delattr(app.state, key)
                except (AttributeError, KeyError):
                    pass
            else:
                setattr(app.state, key, value)


async def test_list_drafts_503_without_brain() -> None:
    with _StateGuard():
        try:
            delattr(app.state, "git_content")
        except (AttributeError, KeyError):
            pass
        async with _client() as client:
            resp = await client.get("/api/brain/drafts")
    assert resp.status_code == 503
    assert "brain" in resp.json()["detail"]


async def test_list_drafts_returns_fixture_slugs(store: WorkStateStore, brain_repo: Path) -> None:
    content = GitContentStore(str(brain_repo))
    with _StateGuard():
        app.state.work_state = store
        app.state.git_content = content
        async with _client() as client:
            resp = await client.get("/api/brain/drafts")
    assert resp.status_code == 200
    body = resp.json()
    slugs = {d["slug"] for d in body["items"]}
    assert slugs == {
        "idempotency-is-the-whole-job",
        "rehearse-the-rollback",
        "the-board-on-the-wall",
    }
    # Two of the three demo pieces are drafted in HTML; the third is still mid-interview with
    # transcript + sources but no draft.html yet (its meta.json says "has_draft": false).
    by_slug = {d["slug"]: d for d in body["items"]}
    assert by_slug["rehearse-the-rollback"]["has_html"] is True
    assert by_slug["the-board-on-the-wall"]["has_html"] is True
    assert by_slug["idempotency-is-the-whole-job"]["has_html"] is False
    for d in body["items"]:
        assert d["title"]
        assert d["revision"] is not None


async def test_list_drafts_includes_markdown_only_draft(store: WorkStateStore, brain_repo: Path) -> None:
    """A direct-content brief (content in piece.md, no draft.html) is listed with the right flags."""
    folder = brain_repo / "drafts" / "markdown-brief"
    folder.mkdir()
    (folder / "piece.md").write_text(
        "# Markdown Brief\n\n---\n\nSome **bold** content.\n", encoding="utf-8"
    )
    repo = GitContentStore(str(brain_repo)).repo
    repo.commit(
        ["drafts/markdown-brief/piece.md"],
        "content(drafts): markdown brief",
        "test",
        "t@test",
    )
    content = GitContentStore(str(brain_repo))
    with _StateGuard():
        app.state.work_state = store
        app.state.git_content = content
        async with _client() as client:
            resp = await client.get("/api/brain/drafts")
    assert resp.status_code == 200
    items = {d["slug"]: d for d in resp.json()["items"]}
    assert items["markdown-brief"]["has_html"] is False
    assert items["markdown-brief"]["has_piece_md"] is True


async def test_read_draft_renders_html(store: WorkStateStore, brain_repo: Path) -> None:
    content = GitContentStore(str(brain_repo))
    with _StateGuard():
        app.state.work_state = store
        app.state.git_content = content
        async with _client() as client:
            resp = await client.get("/api/brain/drafts/rehearse-the-rollback")
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "rehearse-the-rollback"
    assert body["content_kind"] == "html"
    assert body["draft_html"] is not None
    assert body["draft_html"].startswith("<")


async def test_read_draft_renders_markdown(store: WorkStateStore, brain_repo: Path) -> None:
    folder = brain_repo / "drafts" / "markdown-brief"
    folder.mkdir()
    (folder / "piece.md").write_text(
        "# Markdown Brief\n\n---\n\nSome **bold** content.\n- item one\n- item two\n",
        encoding="utf-8",
    )
    repo = GitContentStore(str(brain_repo)).repo
    repo.commit(
        ["drafts/markdown-brief/piece.md"],
        "content(drafts): markdown brief",
        "test",
        "t@test",
    )
    content = GitContentStore(str(brain_repo))
    with _StateGuard():
        app.state.work_state = store
        app.state.git_content = content
        async with _client() as client:
            resp = await client.get("/api/brain/drafts/markdown-brief")
    assert resp.status_code == 200
    body = resp.json()
    assert body["content_kind"] == "markdown"
    assert "<strong>bold</strong>" in body["draft_html"]
    assert "<ul>" in body["draft_html"]


async def test_read_draft_404_unknown_slug(store: WorkStateStore, brain_repo: Path) -> None:
    content = GitContentStore(str(brain_repo))
    with _StateGuard():
        app.state.work_state = store
        app.state.git_content = content
        async with _client() as client:
            resp = await client.get("/api/brain/drafts/does-not-exist")
    assert resp.status_code == 404


async def test_read_draft_adds_review_doc_link(store: WorkStateStore, brain_repo: Path) -> None:
    """When a synced Piece has a minted review Doc, the draft reader surfaces it additively."""
    from app.models.review_round import DocRef, ReviewRound, ShareMode

    content = GitContentStore(str(brain_repo))
    # Sync a piece so the slug exists in Mongo.
    from app.brain_sync import sync_brain_pieces

    await sync_brain_pieces(store, content)
    pieces = {p.slug: p for p in await store.pieces.find({})}
    piece = pieces["rehearse-the-rollback"]
    await store.review_rounds.insert(
        ReviewRound(
            piece_id=piece.id,
            round_number=1,
            minted_from_revision="abc123",
            doc=DocRef(doc_id="doc-1", url="https://docs.google.com/review", share_mode=ShareMode.internal),
            status="open",
            opened_at=None,
        )
    )

    with _StateGuard():
        app.state.work_state = store
        app.state.git_content = content
        async with _client() as client:
            resp = await client.get("/api/brain/drafts/rehearse-the-rollback")
    assert resp.status_code == 200
    body = resp.json()
    assert body["review_doc_url"] == "https://docs.google.com/review"


async def test_read_draft_adds_final_doc_link(store: WorkStateStore, brain_repo: Path) -> None:
    """When a synced Piece has a final Doc, the draft reader surfaces it additively."""
    from app.models.review_round import DocRef, ShareMode

    content = GitContentStore(str(brain_repo))
    from app.brain_sync import sync_brain_pieces

    await sync_brain_pieces(store, content)
    pieces = {p.slug: p for p in await store.pieces.find({})}
    piece = pieces["rehearse-the-rollback"]
    piece.final_doc = DocRef(doc_id="doc-2", url="https://docs.google.com/final", share_mode=ShareMode.internal)
    await store.pieces.update(piece.id, piece.model_dump())

    with _StateGuard():
        app.state.work_state = store
        app.state.git_content = content
        async with _client() as client:
            resp = await client.get("/api/brain/drafts/rehearse-the-rollback")
    assert resp.status_code == 200
    body = resp.json()
    assert body["final_doc_url"] == "https://docs.google.com/final"
