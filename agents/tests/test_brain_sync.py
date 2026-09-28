"""Brain-draft visibility sync (cmw-brain-pieces-visibility): brain-authored ``drafts/<slug>/``
folders become real Pieces.

Covers the core sync (identity lifted from piece.md/meta.json, stage ``review``, the
``brain_synced`` provenance flag, idempotence, never-touch-existing), the piece.md-content
readability fallback in ``read_draft_content``, and the ``POST /api/brain/sync`` wire contract.
Same conventions as the sibling route suites: mongomock work-state, the fixture-brain temp clone
(``brain_repo``), ASGI transport — no Mongo server, no network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.brain_sync import SYNCED_STAGE, sync_brain_pieces
from app.git import GitContentStore
from app.main import app
from app.models.piece import Piece, PieceStage
from app.piece_detail import read_draft_content
from app.repositories import WorkStateStore


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def store() -> WorkStateStore:
    return WorkStateStore(AsyncMongoMockClient()["brain_sync"])


def _add_direct_content_draft(root: Path, slug: str) -> None:
    """Write + commit a direct-content brain draft (the 2026-08-31 briefs' shape: content in
    piece.md, identity in meta.json, no draft.html) into the throwaway brain clone."""
    folder = root / "drafts" / slug
    folder.mkdir(parents=True)
    (folder / "piece.md").write_text(
        "# Web Search Brief\n\n## Executive Summary\n\nShort summary.\n\n---\n\n## The playsheet\n\n"
        "Ask these questions.\n",
        encoding="utf-8",
    )
    (folder / "meta.json").write_text(
        json.dumps(
            {
                "title": "Web Search Brief: Seller Edition",
                "voice": "demo-dana",
                "partners": ["aws"],
                "format": "2-page-seller-guide",
            }
        ),
        encoding="utf-8",
    )
    repo = GitContentStore(str(root)).repo
    repo.commit(
        [f"drafts/{slug}/piece.md", f"drafts/{slug}/meta.json"],
        f"content(drafts): add {slug}",
        "test",
        "t@test",
    )


# --- core sync -----------------------------------------------------------------------------------


async def test_sync_registers_every_brain_draft(store: WorkStateStore, brain_repo: Path) -> None:
    content = GitContentStore(str(brain_repo))
    result = await sync_brain_pieces(store, content)

    # The fixture brain holds exactly three draft folders.
    assert sorted(result.created) == [
        "idempotency-is-the-whole-job",
        "rehearse-the-rollback",
        "the-board-on-the-wall",
    ]
    assert result.drafts == 3

    pieces = {p.slug: p for p in await store.pieces.find({})}
    board = pieces["the-board-on-the-wall"]
    assert board.title == "The board on the wall"
    assert board.voice == "demo-mira"  # lifted from piece.md, never defaulted
    assert board.brain_synced is True
    # Provenance pointer: the commit that seeded the throwaway clone of the fixture brain.
    assert board.latest_revision is not None and len(board.latest_revision) == 40

    rollback = pieces["rehearse-the-rollback"]
    assert rollback.title == "Rehearse the rollback"
    assert rollback.voice == "demo-dana"
    # The demo pieces declare no partner in piece.md ("Partners: none configured"), which the
    # metadata block lifts verbatim as the "none" token rather than an empty list.
    assert rollback.partners == ["none"]
    assert rollback.stage == SYNCED_STAGE == PieceStage.review
    assert rollback.target and "practice note" in rollback.target


async def test_sync_is_idempotent(store: WorkStateStore, brain_repo: Path) -> None:
    content = GitContentStore(str(brain_repo))
    first = await sync_brain_pieces(store, content)
    second = await sync_brain_pieces(store, content)

    assert len(first.created) == 3
    assert second.created == []
    assert sorted(second.existing) == [
        "idempotency-is-the-whole-job",
        "rehearse-the-rollback",
        "the-board-on-the-wall",
    ]
    assert len(await store.pieces.find({})) == 3


async def test_sync_never_touches_a_piece_the_pipeline_already_owns(
    store: WorkStateStore, brain_repo: Path
) -> None:
    """A slug that already has a Piece (pipeline-created or previously synced) is skipped whole —
    the sync never re-stages, re-titles, or re-stamps an existing record."""
    original = await store.pieces.insert(
        Piece(slug="rehearse-the-rollback", voice="demo-dana", title="Pipeline title", stage=PieceStage.interviewing)
    )
    content = GitContentStore(str(brain_repo))
    result = await sync_brain_pieces(store, content)

    assert result.created == ["idempotency-is-the-whole-job", "the-board-on-the-wall"]
    assert result.existing == ["rehearse-the-rollback"]
    reloaded = await store.pieces.get(original.id)
    assert reloaded is not None
    assert reloaded.voice == "demo-dana"
    assert reloaded.title == "Pipeline title"
    assert reloaded.stage == PieceStage.interviewing
    assert reloaded.brain_synced is False


async def test_sync_lifts_identity_from_meta_json_for_direct_content_drafts(
    store: WorkStateStore, brain_repo: Path
) -> None:
    _add_direct_content_draft(brain_repo, "web-search-brief")
    content = GitContentStore(str(brain_repo))
    await sync_brain_pieces(store, content)

    pieces = {p.slug: p for p in await store.pieces.find({})}
    brief = pieces["web-search-brief"]
    assert brief.title == "Web Search Brief: Seller Edition"  # from meta.json (no bullets)
    assert brief.voice == "demo-dana"
    assert brief.partners == ["aws"]
    assert brief.target == "2-page-seller-guide"
    assert brief.stage == PieceStage.review


async def test_sync_falls_back_to_draft_html_title_when_no_piece_md(
    store: WorkStateStore, brain_repo: Path
) -> None:
    """Older pipeline-shaped brain drafts carry draft.html + transcript but NO piece.md — the
    document's own <title> beats the raw slug."""
    folder = brain_repo / "drafts" / "legacy-draft"
    folder.mkdir()
    (folder / "draft.html").write_text(
        "<html><head><title>A Legacy Headline</title></head><body><h1>A Legacy Headline</h1>"
        "<p>Body.</p></body></html>",
        encoding="utf-8",
    )
    content = GitContentStore(str(brain_repo))
    await sync_brain_pieces(store, content)

    pieces = {p.slug: p for p in await store.pieces.find({})}
    assert pieces["legacy-draft"].title == "A Legacy Headline"


# --- readability: the piece.md content fallback ---------------------------------------------------


def test_read_draft_content_prefers_draft_html(brain_repo: Path) -> None:
    """A folder WITH a draft.html is read exactly as before this ticket — the fallback never
    shadows a real revision."""
    content = GitContentStore(str(brain_repo))
    draft = read_draft_content(content, "rehearse-the-rollback")
    assert draft is not None
    assert draft.startswith("<")  # the fixture's real draft.html, untouched
    assert "Piece: rehearse-the-rollback" not in draft


def test_read_draft_content_renders_direct_content_piece_md(brain_repo: Path) -> None:
    """A direct-content brain draft (no draft.html) becomes readable HTML from its piece.md."""
    _add_direct_content_draft(brain_repo, "web-search-brief")
    content = GitContentStore(str(brain_repo))
    html = read_draft_content(content, "web-search-brief")
    assert html is not None
    assert "<h2>The playsheet</h2>" in html
    assert "Ask these questions." in html
    # The metadata-adjacent pre-divider section is NOT part of a metadata-block file's content —
    # here the file has no metadata block, so the whole file renders, divider become <hr>.
    assert "<hr>" in html


def test_read_draft_content_metadata_only_folder_stays_none(brain_repo: Path) -> None:
    """rehearse-the-rollback has a draft.html, so mint a metadata-only folder WITHOUT one to prove the
    honest 'no revision yet' state survives the fallback (no divider → no content section)."""
    folder = brain_repo / "drafts" / "scope-only"
    folder.mkdir()
    (folder / "piece.md").write_text("# Piece: scope-only\n\n## Metadata\n- Slug: scope-only\n", encoding="utf-8")
    content = GitContentStore(str(brain_repo))
    assert read_draft_content(content, "scope-only") is None


# --- REST surface ----------------------------------------------------------------------------------


class _StateGuard:
    """Save/restore the app.state attrs these route tests touch (they leak across a test session
    otherwise — see the sibling route suites' shared-app caveat)."""

    def __enter__(self) -> None:
        self._saved = {
            k: getattr(app.state, k, None) for k in ("work_state", "git_content")
        }

    def __exit__(self, *exc: object) -> None:
        for key, value in self._saved.items():
            if value is None:
                try:
                    delattr(app.state, key)
                except (AttributeError, KeyError):  # Starlette State raises KeyError when absent
                    pass
            else:
                setattr(app.state, key, value)


async def test_sync_route_503_without_mongo() -> None:
    with _StateGuard():
        try:
            delattr(app.state, "work_state")
        except (AttributeError, KeyError):
            pass
        async with _client() as client:
            resp = await client.post("/api/brain/sync")
    assert resp.status_code == 503
    assert "MONGO_URL" in resp.json()["detail"]


async def test_sync_route_503_without_brain(store: WorkStateStore) -> None:
    with _StateGuard():
        app.state.work_state = store
        try:
            delattr(app.state, "git_content")
        except (AttributeError, KeyError):
            pass
        async with _client() as client:
            resp = await client.post("/api/brain/sync")
    assert resp.status_code == 503
    assert "brain" in resp.json()["detail"]


async def test_sync_route_registers_and_reports(
    store: WorkStateStore, brain_repo: Path
) -> None:
    _add_direct_content_draft(brain_repo, "iceberg-brief")
    with _StateGuard():
        app.state.work_state = store
        app.state.git_content = GitContentStore(str(brain_repo))
        async with _client() as client:
            resp = await client.post("/api/brain/sync")
            assert resp.status_code == 200
            body = resp.json()
            assert "iceberg-brief" in body["created"]
            assert body["drafts"] == 4

            # The synced piece is immediately readable through the standard piece-detail route —
            # the acceptance shape: brain content visible AND readable alongside pipeline pieces.
            pieces = {p.slug: p for p in await store.pieces.find({})}
            detail = await client.get(f"/api/pieces/{pieces['iceberg-brief'].id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["brain_synced"] is True
    assert payload["stage"] == "review"
    assert "<h2>The playsheet</h2>" in payload["draft_html"]
