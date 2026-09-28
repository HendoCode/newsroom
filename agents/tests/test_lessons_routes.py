"""HTTP-surface tests for the lessons loop routes (D12; domain model §1.18).

Drives ``/api/lessons/...`` end-to-end over ASGI with the work-state store, Git brain/content, and
a fake LLM provider attached directly to ``app.state`` (mirroring ``test_connectors_routes.py`` /
``test_lake_routes.py``), proving the wiring, request/response contracts, the 503-when-unconfigured
guards, and the accept/reject → Git-commit gate. No Mongo server, no network, no credentials.
"""

from __future__ import annotations

import json

from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.git import GitBrain, GitContentStore
from app.llm.pricing import Usage, cost_usd
from app.llm.provider import LLMProvider, LLMResult
from app.main import app
from app.models import Lesson, LessonStatus, Piece, PieceStage
from app.repositories import WorkStateStore

SLUG = "the-board-on-the-wall"


class _FakeProvider(LLMProvider):
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text

    async def complete(self, *, step, model, system, messages, max_tokens, effort=None, cache=False, budget=None):
        usage = Usage(input_tokens=10, output_tokens=10)
        return LLMResult(
            text=self.response_text, model=model, stop_reason="end_turn",
            usage=usage, cost_usd=cost_usd(model, usage),
        )

    def stream(self, **kwargs):
        raise NotImplementedError

    async def count_tokens(self, *, model, system, messages):
        return 0


def _attach(
    store: WorkStateStore | None,
    brain: GitBrain | None,
    content: GitContentStore | None,
    provider: LLMProvider | None = None,
) -> None:
    app.state.work_state = store
    app.state.git_brain = brain
    app.state.git_content = content
    app.state.llm_provider = provider


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_propose_over_http(git_brain: GitBrain, content_store: GitContentStore) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["lessons_propose"])
    final_text = content_store.read_draft(SLUG)
    sha = content_store.commit_revision(SLUG, final_text + "\n<!-- final -->\n", message="final")
    piece = await store.pieces.insert(
        Piece(slug=SLUG, voice="demo-mira", stage=PieceStage.lessons, latest_revision=sha)
    )
    response_text = json.dumps(
        [{"observed_change": "cut the caveat", "generalizable_rule": "State the number, then move on."}]
    )
    _attach(store, git_brain, content_store, _FakeProvider(response_text))

    async with _client() as client:
        resp = await client.post(
            f"/api/lessons/{piece.id}/propose",
            json={"published_content": final_text + "\n<!-- final -->\n<!-- edited -->\n"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["proposed"]) == 1
    assert body["proposed"][0]["generalizable_rule"] == "State the number, then move on."
    assert body["proposed"][0]["status"] == "proposed"

    stored = await store.lessons.by_piece(piece.id)
    assert len(stored) == 1


async def test_propose_404_unknown_piece(git_brain: GitBrain, content_store: GitContentStore) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["lessons_404"])
    _attach(store, git_brain, content_store, _FakeProvider("[]"))
    async with _client() as client:
        resp = await client.post("/api/lessons/nonexistent/propose", json={"published_content": "x"})
    assert resp.status_code == 404


async def test_propose_409_wrong_stage(git_brain: GitBrain, content_store: GitContentStore) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["lessons_409"])
    piece = await store.pieces.insert(Piece(slug=SLUG, voice="demo-mira", stage=PieceStage.finalized))
    _attach(store, git_brain, content_store, _FakeProvider("[]"))
    async with _client() as client:
        resp = await client.post(f"/api/lessons/{piece.id}/propose", json={"published_content": "x"})
    assert resp.status_code == 409


async def test_lessons_503_when_unconfigured() -> None:
    _attach(None, None, None, None)
    async with _client() as client:
        resp = await client.post("/api/lessons/anything/propose", json={"published_content": "x"})
        pending = await client.get("/api/lessons/pending")
    assert resp.status_code == 503
    assert pending.status_code == 503


async def test_propose_503_when_llm_not_configured(git_brain: GitBrain, content_store: GitContentStore) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["lessons_no_llm"])
    piece = await store.pieces.insert(Piece(slug=SLUG, voice="demo-mira", stage=PieceStage.lessons))
    _attach(store, git_brain, content_store, provider=None)
    async with _client() as client:
        resp = await client.post(f"/api/lessons/{piece.id}/propose", json={"published_content": "x"})
    assert resp.status_code == 503


async def test_accept_over_http_commits_to_git(git_brain: GitBrain, content_store: GitContentStore) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["lessons_accept"])
    lesson = await store.lessons.insert(
        Lesson(voice="demo-mira", observed_change="x", generalizable_rule="Draft phrasing.")
    )
    _attach(store, git_brain, content_store)

    async with _client() as client:
        resp = await client.post(
            f"/api/lessons/{lesson.id}/accept",
            json={"rule_text": "The edited final phrasing.", "actor": "alex@example.com"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["generalizable_rule"] == "The edited final phrasing."

    mira_lessons = content_store.repo.read_text(
        content_store._p("voice", "demo-mira", "content-lessons.md")
    )
    assert "The edited final phrasing." in mira_lessons


async def test_accept_409_when_not_pending(git_brain: GitBrain, content_store: GitContentStore) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["lessons_accept_409"])
    lesson = await store.lessons.insert(
        Lesson(voice="demo-mira", observed_change="x", generalizable_rule="y", status=LessonStatus.accepted)
    )
    _attach(store, git_brain, content_store)
    async with _client() as client:
        resp = await client.post(f"/api/lessons/{lesson.id}/accept", json={})
    assert resp.status_code == 409


async def test_reject_over_http_leaves_git_untouched(git_brain: GitBrain, content_store: GitContentStore) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["lessons_reject"])
    before = content_store.repo.read_text(content_store._p("voice", "demo-mira", "content-lessons.md"))
    lesson = await store.lessons.insert(
        Lesson(voice="demo-mira", observed_change="x", generalizable_rule="a one-off edit")
    )
    _attach(store, git_brain, content_store)

    async with _client() as client:
        resp = await client.post(f"/api/lessons/{lesson.id}/reject", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"
    after = content_store.repo.read_text(content_store._p("voice", "demo-mira", "content-lessons.md"))
    assert before == after


async def test_list_pending_and_list_for_piece(git_brain: GitBrain, content_store: GitContentStore) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["lessons_list"])
    piece = await store.pieces.insert(Piece(slug=SLUG, voice="demo-mira", stage=PieceStage.lessons))
    proposed = await store.lessons.insert(
        Lesson(voice="demo-mira", source_piece_id=piece.id, observed_change="x", generalizable_rule="a")
    )
    await store.lessons.insert(
        Lesson(voice="demo-dana", source_piece_id=piece.id, observed_change="y", generalizable_rule="b")
    )
    _attach(store, git_brain, content_store)

    async with _client() as client:
        pending_all = await client.get("/api/lessons/pending")
        pending_mira = await client.get("/api/lessons/pending", params={"voice": "demo-mira"})
        for_piece = await client.get(f"/api/lessons/{piece.id}")

    assert len(pending_all.json()) == 2
    assert [item["id"] for item in pending_mira.json()] == [proposed.id]
    assert len(for_piece.json()) == 2


async def test_preview_over_http_does_not_write(
    git_brain: GitBrain, content_store: GitContentStore
) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["lessons_preview"])
    lesson = await store.lessons.insert(
        Lesson(voice="demo-mira", observed_change="x", generalizable_rule="Lead with the number.")
    )
    path = content_store._p("voice", "demo-mira", "content-lessons.md")
    before = content_store.repo.read_text(path)
    _attach(store, git_brain, content_store)

    async with _client() as client:
        resp = await client.get(f"/api/lessons/{lesson.id}/preview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rule_text"] == "Lead with the number."
    assert body["before"] == before
    assert "- Lead with the number." in body["after"]
    assert content_store.repo.read_text(path) == before


async def test_batch_accept_over_http(
    git_brain: GitBrain, content_store: GitContentStore
) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["lessons_batch"])
    a = await store.lessons.insert(
        Lesson(voice="demo-mira", observed_change="a", generalizable_rule="Rule A.")
    )
    b = await store.lessons.insert(
        Lesson(voice="demo-mira", observed_change="b", generalizable_rule="Rule B.")
    )
    _attach(store, git_brain, content_store)

    async with _client() as client:
        resp = await client.post(
            "/api/lessons/batch",
            json={"action": "accept", "lesson_ids": [a.id, b.id]},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["decided"]) == 2
    assert body["errors"] == []
    lessons_file = content_store.repo.read_text(
        content_store._p("voice", "demo-mira", "content-lessons.md")
    )
    assert "Rule A." in lessons_file
    assert "Rule B." in lessons_file
