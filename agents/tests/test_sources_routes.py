"""HTTP-surface tests for the source registry CRUD (Item 6 / D8).

Drives ``GET/POST/PATCH/DELETE /api/sources`` over ASGI with an in-memory store attached to
``app.state``, proving the store-vs-seed fallback, the add/edit/enable-disable/retire lifecycle,
the credential-free-config + linkedin-is-read-as-needed invariants surfacing as 400s (not silently
dropped), and the 503-when-unconfigured guard. No Mongo server, no network, no credentials.
"""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.main import app
from app.models.source import Source, SourceClassification, SourceKind
from app.repositories import WorkStateStore
from app.sources import seed_sources


def _attach(store: WorkStateStore | None) -> None:
    app.state.work_state = store


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_list_falls_back_to_seed_when_store_empty() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["s1"])
    _attach(store)

    async with _client() as client:
        resp = await client.get("/api/sources")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "seed"
    assert len(body["items"]) == len(seed_sources())
    kinds = {item["kind"] for item in body["items"]}
    assert kinds == {"gdrive", "slack", "web-rss", "linkedin-x-clip"}
    # No credential-looking keys ever leave the registry (D14).
    for item in body["items"]:
        assert "owner" in item and "config" in item
        assert not any("token" in k or "secret" in k for k in item["config"])


async def test_list_reads_real_store_once_populated() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["s2"])
    await store.sources.insert(
        Source(
            display_name="rss",
            kind=SourceKind.web_rss,
            classification=SourceClassification.scraped_periodically,
        )
    )
    _attach(store)

    async with _client() as client:
        resp = await client.get("/api/sources")
    body = resp.json()
    assert body["source"] == "store"
    assert len(body["items"]) == 1
    assert body["items"][0]["display_name"] == "rss"


async def test_create_update_retire_lifecycle() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["s3"])
    _attach(store)

    async with _client() as client:
        created = await client.post(
            "/api/sources",
            json={
                "display_name": "Q3 call transcripts",
                "kind": "gdrive",
                "classification": "scraped-periodically",
                "config": {"folder_ids": ["abc123"]},
            },
        )
        assert created.status_code == 201
        source_id = created.json()["id"]
        assert created.json()["enabled"] is True

        # Toggle disabled.
        toggled = await client.patch(f"/api/sources/{source_id}", json={"enabled": False})
        assert toggled.status_code == 200
        assert toggled.json()["enabled"] is False

        # Edit config + lookback, unrelated fields untouched.
        edited = await client.patch(
            f"/api/sources/{source_id}",
            json={"config": {"folder_ids": ["abc123", "def456"]}, "lookback_default_days": 14},
        )
        assert edited.status_code == 200
        assert edited.json()["config"]["folder_ids"] == ["abc123", "def456"]
        assert edited.json()["lookback_default_days"] == 14
        assert edited.json()["display_name"] == "Q3 call transcripts"  # untouched by the edit

        # Retire.
        retired = await client.delete(f"/api/sources/{source_id}")
        assert retired.status_code == 200
        assert retired.json() == {"id": source_id, "deleted": True}

        gone = await client.get("/api/sources")
        assert gone.json()["source"] == "seed"  # store is empty again → falls back


async def test_create_rejects_credential_looking_config() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["s4"])
    _attach(store)

    async with _client() as client:
        resp = await client.post(
            "/api/sources",
            json={
                "display_name": "sneaky",
                "kind": "slack",
                "classification": "scraped-periodically",
                "config": {"bot_token": "xoxb-should-never-be-here"},
            },
        )
    assert resp.status_code == 400


async def test_create_rejects_linkedin_as_scraped_periodically() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["s5"])
    _attach(store)

    async with _client() as client:
        resp = await client.post(
            "/api/sources",
            json={
                "display_name": "bad",
                "kind": "linkedin-x-clip",
                "classification": "scraped-periodically",
            },
        )
    assert resp.status_code == 400


async def test_edit_cannot_smuggle_a_credential_into_an_existing_source() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["s6"])
    source = await store.sources.insert(
        Source(
            display_name="rss",
            kind=SourceKind.web_rss,
            classification=SourceClassification.scraped_periodically,
        )
    )
    _attach(store)

    async with _client() as client:
        resp = await client.patch(
            f"/api/sources/{source.id}", json={"config": {"api_key": "leaked"}}
        )
    assert resp.status_code == 400


async def test_update_and_retire_404_for_unknown_source() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["s7"])
    _attach(store)

    async with _client() as client:
        patch_resp = await client.patch("/api/sources/does-not-exist", json={"enabled": False})
        delete_resp = await client.delete("/api/sources/does-not-exist")
    assert patch_resp.status_code == 404
    assert delete_resp.status_code == 404


async def test_sources_503_when_unconfigured() -> None:
    _attach(None)
    async with _client() as client:
        create = await client.post(
            "/api/sources",
            json={"display_name": "x", "kind": "web-rss", "classification": "scraped-periodically"},
        )
        update = await client.patch("/api/sources/x", json={"enabled": False})
        delete = await client.delete("/api/sources/x")
    assert create.status_code == 503
    assert update.status_code == 503
    assert delete.status_code == 503
    # GET never 503s — it always has the seed fallback.
    async with _client() as client:
        listed = await client.get("/api/sources")
    assert listed.status_code == 200
    assert listed.json()["source"] == "seed"
