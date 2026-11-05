"""HTTP-surface tests for the connector routes (D8).

Drives ``POST /api/connectors/refresh`` and ``/clip`` end-to-end over ASGI with an in-memory store
+ lake attached to ``app.state`` (fake connectors injected for refresh), proving the wiring,
request/response contracts, the clip-in read-as-needed write, and the 503-when-unconfigured guard.
No Mongo server, no network, no credentials.
"""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.connectors import RawItem, SourceConnector
from app.lake import build_content_lake
from app.main import app
from app.models.source import Source, SourceClassification, SourceKind
from app.repositories import WorkStateStore


class _FakeConnector(SourceConnector):
    def __init__(self, kind: SourceKind, items: list[RawItem]) -> None:
        self.kind = kind
        self._items = items

    async def fetch(self, source: Source, *, lookback_days: int) -> list[RawItem]:
        return list(self._items)


def _attach(store: WorkStateStore | None, lake, connectors=None) -> None:
    app.state.work_state = store
    app.state.content_lake = lake
    app.state.connectors = connectors


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_refresh_over_http() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["r"])
    lake = build_content_lake(AsyncMongoMockClient()["rl"])
    await store.sources.insert(
        Source(
            display_name="rss",
            kind=SourceKind.web_rss,
            classification=SourceClassification.scraped_periodically,
        )
    )
    connectors = {
        SourceKind.web_rss: _FakeConnector(
            SourceKind.web_rss, [RawItem(raw_content="hi", external_id="1")]
        )
    }
    _attach(store, lake, connectors)

    async with _client() as client:
        resp = await client.post("/api/connectors/refresh", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["refreshed"]) == 1
    assert body["refreshed"][0]["ingested"] == 1
    assert body["refreshed"][0]["error"] is None
    assert await lake.count() == 1


async def test_clip_in_over_http() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["c"])
    lake = build_content_lake(AsyncMongoMockClient()["cl"])
    source = await store.sources.insert(
        Source(
            display_name="LinkedIn clips",
            kind=SourceKind.linkedin_x_clip,
            classification=SourceClassification.read_as_needed,
        )
    )
    _attach(store, lake)

    async with _client() as client:
        resp = await client.post(
            "/api/connectors/clip",
            json={
                "source_id": source.id,
                "content": "A sharp take on storage economics.",
                "author": "Jane Expert",
                "tags": ["storage"],
                "url": "https://x.com/jane/status/1",
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["indexed"] is True
    assert body["classification"] == "read-as-needed"
    assert body["id"]
    assert await lake.count() == 1


async def test_clip_in_rejects_non_clip_source_over_http() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["c2"])
    lake = build_content_lake(AsyncMongoMockClient()["cl2"])
    slack = await store.sources.insert(
        Source(
            display_name="slack",
            kind=SourceKind.slack,
            classification=SourceClassification.scraped_periodically,
        )
    )
    _attach(store, lake)

    async with _client() as client:
        resp = await client.post(
            "/api/connectors/clip", json={"source_id": slack.id, "content": "x"}
        )
    assert resp.status_code == 400


async def test_connectors_503_when_unconfigured() -> None:
    _attach(None, None)
    async with _client() as client:
        refresh = await client.post("/api/connectors/refresh", json={})
        clip = await client.post("/api/connectors/clip", json={"source_id": "x", "content": "y"})
    assert refresh.status_code == 503
    assert clip.status_code == 503
