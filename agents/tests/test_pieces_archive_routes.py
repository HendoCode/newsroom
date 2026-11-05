"""HTTP-surface tests for archive/unarchive — triage at scale, orthogonal to the stage machine.

Drives ``POST /api/pieces/{id}/{archive,unarchive}`` over ASGI with an in-memory store attached to
``app.state`` (same convention as ``test_spikes_routes.py``), proving: it works regardless of the
piece's stage (including the terminal ``published`` stage), it changes nothing else about the
piece, it is reversible, an archived piece stays fully reachable at its direct
``GET /api/pieces/{id}`` URL, and ``GET /api/dashboard`` is the one place it disappears. No Mongo
server, no network.
"""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.models.piece import Piece, PieceStage
from app.main import app
from app.repositories import WorkStateStore


def _attach(store: WorkStateStore | None) -> None:
    app.state.work_state = store


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_archive_works_regardless_of_stage_and_changes_nothing_else() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["arch1"])
    piece = await store.pieces.insert(
        Piece(
            slug="p",
            voice="demo-mira",
            stage=PieceStage.released,
            owner="a@example.com",
            open_gaps=3,
        )
    )
    _attach(store)

    async with _client() as client:
        resp = await client.post(f"/api/pieces/{piece.id}/archive")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == piece.id
    assert body["slug"] == "p"
    assert body["archived_at"] is not None

    reloaded = await store.pieces.get(piece.id)
    assert reloaded is not None
    assert reloaded.archived_at is not None
    # Otherwise unchanged: stage, owner, open_gaps all untouched.
    assert reloaded.stage == PieceStage.released
    assert reloaded.owner == "a@example.com"
    assert reloaded.open_gaps == 3


async def test_unarchive_restores_dashboard_visibility() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["arch2"])
    piece = await store.pieces.insert(Piece(slug="p", voice="demo-mira", stage=PieceStage.review))
    _attach(store)

    async with _client() as client:
        archive_resp = await client.post(f"/api/pieces/{piece.id}/archive")
        assert archive_resp.status_code == 200
        hidden = await client.get("/api/dashboard")
        assert piece.id not in {i["id"] for i in hidden.json()["items"]}

        unarchive_resp = await client.post(f"/api/pieces/{piece.id}/unarchive")
        assert unarchive_resp.status_code == 200
        assert unarchive_resp.json()["archived_at"] is None
        restored = await client.get("/api/dashboard")
    assert piece.id in {i["id"] for i in restored.json()["items"]}


async def test_archived_piece_stays_reachable_by_direct_url() -> None:
    """Hidden from the dashboard list, never made inaccessible (a direct link/bookmark still
    resolves) — the explicit design decision this endpoint pair implements."""
    store = WorkStateStore(AsyncMongoMockClient()["arch3"])
    piece = await store.pieces.insert(Piece(slug="p", voice="demo-mira", stage=PieceStage.finalized))
    _attach(store)

    async with _client() as client:
        await client.post(f"/api/pieces/{piece.id}/archive")
        dashboard = await client.get("/api/dashboard")
        detail = await client.get(f"/api/pieces/{piece.id}")

    assert piece.id not in {i["id"] for i in dashboard.json()["items"]}
    assert detail.status_code == 200
    assert detail.json()["archived_at"] is not None


async def test_archive_404_for_unknown_piece() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["arch4"])
    _attach(store)
    async with _client() as client:
        resp = await client.post("/api/pieces/does-not-exist/archive")
    assert resp.status_code == 404


async def test_unarchive_404_for_unknown_piece() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["arch5"])
    _attach(store)
    async with _client() as client:
        resp = await client.post("/api/pieces/does-not-exist/unarchive")
    assert resp.status_code == 404


async def test_archive_503_when_unconfigured() -> None:
    _attach(None)
    async with _client() as client:
        archive_resp = await client.post("/api/pieces/x/archive")
        unarchive_resp = await client.post("/api/pieces/x/unarchive")
    assert archive_resp.status_code == 503
    assert unarchive_resp.status_code == 503
