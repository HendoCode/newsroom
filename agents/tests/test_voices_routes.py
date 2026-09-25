"""HTTP-surface tests for the voice kit routes (screen 11 / D12; domain model §1.1).

Drives ``/api/voices/...`` end-to-end over ASGI with the Git brain attached directly to
``app.state`` (mirroring ``test_lessons_routes.py``), proving the wiring, the request/response
contracts, the 503-when-unconfigured guard, and the commit/history/rollback round trip. No Mongo,
no network.
"""

from __future__ import annotations

from app.git import GitBrain
from app.main import app


def _attach(brain: GitBrain | None) -> None:
    app.state.git_brain = brain


def _client():
    from httpx import ASGITransport, AsyncClient

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_list_voices(git_brain: GitBrain) -> None:
    _attach(git_brain)
    async with _client() as client:
        resp = await client.get("/api/voices")
    assert resp.status_code == 200
    voices = resp.json()["voices"]
    assert {"demo-mira", "demo-dana", "demo-dana"}.issubset(set(voices))


async def test_get_voice_pack(git_brain: GitBrain) -> None:
    _attach(git_brain)
    async with _client() as client:
        mira = await client.get("/api/voices/demo-mira")
        team = await client.get("/api/voices/demo-dana")
    assert mira.status_code == 200
    body = mira.json()
    assert body["voice_guide"] and body["style_guide"] and body["content_lessons"]
    assert body["visual_identity"] is None
    assert team.json()["visual_identity"] is not None


async def test_get_unknown_voice_404s(git_brain: GitBrain) -> None:
    _attach(git_brain)
    async with _client() as client:
        resp = await client.get("/api/voices/nonexistent")
    assert resp.status_code == 404


async def test_update_then_history_then_rollback(git_brain: GitBrain) -> None:
    _attach(git_brain)
    async with _client() as client:
        original = (await client.get("/api/voices/demo-mira")).json()["voice_guide"]

        put_resp = await client.put(
            "/api/voices/demo-mira/files/voice_guide",
            json={
                "content": original + "\n- say 'field extraction' not 'extraction'\n",
                "message": "tighten register",
                "actor": "alex@example.com",
                "actor_name": "Alex",
            },
        )
        assert put_resp.status_code == 200
        commit = put_resp.json()
        assert commit["author_email"] == "alex@example.com"
        first_sha = commit["sha"]

        history_resp = await client.get("/api/voices/demo-mira/files/voice_guide/history")
        assert history_resp.status_code == 200
        commits = history_resp.json()["commits"]
        assert commits[0]["sha"] == first_sha

        at_resp = await client.get(f"/api/voices/demo-mira/files/voice_guide/at/{first_sha}")
        assert at_resp.status_code == 200
        assert "field extraction" in at_resp.json()["content"]

        # a second edit, then roll back to the first commit
        await client.put(
            "/api/voices/demo-mira/files/voice_guide",
            json={"content": original + "\n- something else entirely\n", "message": "second edit"},
        )
        rollback_resp = await client.post(
            "/api/voices/demo-mira/files/voice_guide/rollback",
            json={"sha": first_sha, "actor": "sam@example.com"},
        )
        assert rollback_resp.status_code == 200
        assert rollback_resp.json()["author_email"] == "sam@example.com"

        current = (await client.get("/api/voices/demo-mira")).json()["voice_guide"]
        assert "field extraction" in current
        assert "something else entirely" not in current


async def test_unknown_file_key_422s(git_brain: GitBrain) -> None:
    _attach(git_brain)
    async with _client() as client:
        resp = await client.get("/api/voices/demo-mira/files/nonsense/history")
    assert resp.status_code == 422


async def test_voices_503_when_unconfigured() -> None:
    _attach(None)
    async with _client() as client:
        resp = await client.get("/api/voices")
    assert resp.status_code == 503
