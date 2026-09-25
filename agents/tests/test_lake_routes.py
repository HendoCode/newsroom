"""HTTP-surface tests for the content-lake ingest/query API (D9).

Drives the REST endpoints end-to-end with an in-memory lake attached to ``app.state``, proving the
router wiring, request/response contracts, and the 503-when-unconfigured behavior. The lifespan is
not triggered (no ``with`` block), so these tests need no Mongo server.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.lake import build_content_lake
from app.main import app


@pytest.fixture
def client_with_lake() -> TestClient:
    client = TestClient(app)
    app.state.content_lake = build_content_lake(AsyncMongoMockClient()["cmw_routes"])
    return client


def test_ingest_then_query_over_http(client_with_lake: TestClient) -> None:
    ingest = client_with_lake.post(
        "/api/lake/ingest",
        json={
            "raw_content": "AWS S3 storage pricing for cold data",
            "source_id": "src-slack",
            "classification": "read-as-needed",
            "metadata": {"author": "alex", "tags": ["aws"]},
        },
    )
    assert ingest.status_code == 200
    body = ingest.json()
    assert body["indexed"] is True and body["id"]

    query = client_with_lake.post(
        "/api/lake/query",
        json={"text": "storage pricing", "top_k": 5},
    )
    assert query.status_code == 200
    hits = query.json()
    assert len(hits) == 1
    assert hits[0]["item"]["source_id"] == "src-slack"
    assert hits[0]["item"]["metadata"]["author"] == "alex"
    assert hits[0]["score"] > 0.0


def test_query_503_when_lake_unconfigured() -> None:
    client = TestClient(app)
    app.state.content_lake = None
    resp = client.post("/api/lake/query", json={"text": "anything"})
    assert resp.status_code == 503
