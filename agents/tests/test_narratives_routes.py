"""HTTP-surface tests for the Narrative REST surface (§1.5) — Oracle Entry B's seed.

Drives ``POST/GET /api/narratives...`` over ASGI with an in-memory store, proving creation
persists the audience/angle intent, the create -> get round-trip, and the 503-when-unconfigured
guard. No Mongo server, no network.
"""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.main import app
from app.repositories import WorkStateStore


def _attach(store: WorkStateStore | None) -> None:
    app.state.work_state = store


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_create_and_get_round_trip() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["n1"])
    _attach(store)

    async with _client() as client:
        created = await client.post(
            "/api/narratives",
            json={
                "author": "demo-mira@example.com",
                "seed_text": "S3 is maligned as the most expensive storage on earth...",
                "audience": "technical leaders on AWS",
                "angle": "reframe where the money leaks",
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert body["author"] == "demo-mira@example.com"
        assert body["intent"] == {
            "audience": "technical leaders on AWS",
            "angle": "reframe where the money leaks",
        }
        assert body["oracle_run_id"] is None

        fetched = await client.get(f"/api/narratives/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body


async def test_create_defaults_author_when_unattributed() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["n2"])
    _attach(store)

    async with _client() as client:
        resp = await client.post("/api/narratives", json={"seed_text": "open scan seed"})
    assert resp.status_code == 201
    assert resp.json()["author"] == "unknown"


async def test_get_404_for_unknown_narrative() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["n3"])
    _attach(store)

    async with _client() as client:
        resp = await client.get("/api/narratives/does-not-exist")
    assert resp.status_code == 404


async def test_narratives_503_when_unconfigured() -> None:
    _attach(None)
    async with _client() as client:
        create = await client.post("/api/narratives", json={"seed_text": "x"})
        get = await client.get("/api/narratives/x")
    assert create.status_code == 503
    assert get.status_code == 503
