"""HTTP-surface tests for the read-only Git-brain persona listing (§1.2).

Uses the ``git_brain`` fixture (a copy of the fixture brain in a temp git
repo, from ``conftest.py``) so the listing is exercised against the true on-disk layout. No Mongo
needed — this route only reads ``app.state.git_brain``. Voice listing is covered separately by
``test_voices_routes.py`` (``agents/app/voices.py``'s full view/edit/rollback CRUD).
"""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from app.git import GitBrain
from app.main import app


def _attach(brain: GitBrain | None) -> None:
    app.state.git_brain = brain


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_list_interviewer_personas(git_brain: GitBrain) -> None:
    _attach(git_brain)
    async with _client() as client:
        resp = await client.get("/api/personas")
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "interviewer"
    assert "ferriss" in body["personas"]
    assert "skeptic" in body["personas"]


async def test_list_editor_personas(git_brain: GitBrain) -> None:
    _attach(git_brain)
    async with _client() as client:
        resp = await client.get("/api/personas", params={"kind": "editor"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "editor"
    assert "slop-allergist" in body["personas"]


async def test_personas_400_for_unknown_kind(git_brain: GitBrain) -> None:
    _attach(git_brain)
    async with _client() as client:
        resp = await client.get("/api/personas", params={"kind": "bogus"})
    assert resp.status_code == 400


async def test_personas_503_when_unconfigured() -> None:
    _attach(None)
    async with _client() as client:
        resp = await client.get("/api/personas")
    assert resp.status_code == 503
