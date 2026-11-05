"""HTTP-surface tests for ``GET /api/pieces/recent`` — the desk's recent-pieces projection.

Drives the route over ASGI with an in-memory store attached to ``app.state`` (same convention as
``test_pieces_archive_routes.py``), proving: it returns the ~N most recently active pieces newest
first, archived pieces never re-surface on the desk (same choke point as ``build_queue``), the
``limit`` param is validated (not silently re-clamped), and — the point of this endpoint — an
unconfigured or empty deploy returns an HONEST empty list, never a seed/hardcoded fallback.
No Mongo server, no network.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.main import app
from app.models.common import utcnow
from app.models.piece import Piece, PieceStage
from app.repositories import WorkStateStore


def _attach(store: WorkStateStore | None) -> None:
    app.state.work_state = store


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_pieces(store: WorkStateStore, count: int) -> list[Piece]:
    """Insert `count` pieces, then backdate `updated_at` so piece i was last touched (count - i)
    hours ago — insert alone cannot order them (every insert stamps ~the same instant), and
    `BaseRepository.update` always re-stamps `updated_at` with the current time, so the backdate
    goes straight to the collection (test-only seeding, not a write path under test)."""
    pieces = [
        await store.pieces.insert(
            Piece(
                slug=f"slug-{i}",
                voice="demo-dana",
                title=f"Piece {i}",
                stage=PieceStage.interviewing,
            )
        )
        for i in range(count)
    ]
    base = utcnow()
    for i, piece in enumerate(pieces):
        await store.pieces.collection.update_one(
            {"_id": piece.id}, {"$set": {"updated_at": base - timedelta(hours=count - i)}}
        )
    return pieces


async def test_returns_six_most_recent_newest_first() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["recent1"])
    seeded = await _seed_pieces(store, 8)
    _attach(store)

    async with _client() as client:
        resp = await client.get("/api/pieces/recent")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "store"
    items = body["items"]
    assert len(items) == 6
    # Newest activity first: the highest-indexed seeds were touched most recently.
    assert [item["slug"] for item in items] == [
        seeded[7].slug,
        seeded[6].slug,
        seeded[5].slug,
        seeded[4].slug,
        seeded[3].slug,
        seeded[2].slug,
    ]
    first = items[0]
    assert first["title"] == "Piece 7"
    assert first["stage"] == PieceStage.interviewing.value
    assert first["updated_at"] is not None
    assert first["created_at"] is not None


async def test_archived_pieces_are_excluded() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["recent2"])
    seeded = await _seed_pieces(store, 3)
    # The MOST recently touched piece is archived — it must not surface at all.
    assert seeded[2].id is not None
    await store.pieces.archive(seeded[2].id)
    _attach(store)

    async with _client() as client:
        resp = await client.get("/api/pieces/recent")
    items = resp.json()["items"]
    assert [item["slug"] for item in items] == [seeded[1].slug, seeded[0].slug]


async def test_limit_param_bounds() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["recent3"])
    await _seed_pieces(store, 5)
    _attach(store)

    async with _client() as client:
        two = await client.get("/api/pieces/recent?limit=2")
        twenty_five = await client.get("/api/pieces/recent?limit=25")
        zero = await client.get("/api/pieces/recent?limit=0")
    assert two.status_code == 200 and len(two.json()["items"]) == 2
    # Out-of-range limits are a 422 (FastAPI Query validation), never a silent re-clamp.
    assert twenty_five.status_code == 422
    assert zero.status_code == 422


async def test_empty_store_reports_honest_empty_list() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["recent4"])
    _attach(store)

    async with _client() as client:
        resp = await client.get("/api/pieces/recent")
    assert resp.status_code == 200
    assert resp.json() == {"source": "store", "items": []}


async def test_unconfigured_reports_empty_list_not_503() -> None:
    """The desk card degrades to its empty state; this is a read projection, not a write gate
    (contrast the archive routes, which 503 — see `test_pieces_archive_routes.py`)."""
    _attach(None)

    async with _client() as client:
        resp = await client.get("/api/pieces/recent")
    assert resp.status_code == 200
    assert resp.json() == {"source": "none", "items": []}


async def test_recent_never_shadows_piece_detail_route() -> None:
    """`/api/pieces/recent` (pieces router) is registered before `GET /api/pieces/{piece_id}`
    (main.py) — guard that ordering: 'recent' resolves to the projection, not a piece id lookup."""
    store = WorkStateStore(AsyncMongoMockClient()["recent5"])
    await _seed_pieces(store, 1)
    _attach(store)

    async with _client() as client:
        resp = await client.get("/api/pieces/recent")
    assert resp.status_code == 200
    assert "items" in resp.json()
