"""HTTP-surface tests for POST /api/pieces/{id}/publish.

Drives the route end-to-end over ASGI with the work-state store, Git content/brain, a real
``PieceMachine``, and fake storage/Docs clients attached directly to ``app.state`` — the same
``app.state.<seam>`` override convention ``test_review_routes.py`` establishes. No Mongo server,
no network, no credentials.
"""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.git import GitBrain, GitContentStore
from app.main import app
from app.models import Piece, PieceStage
from app.orchestration import JobRunner, PieceMachine, StepRegistry
from app.render.docs_export import DocRef
from app.repositories import WorkStateStore

SLUG = "the-board-on-the-wall"


class _FakeStorage:
    def __init__(self) -> None:
        self.puts: list[tuple[str, bytes, str]] = []

    async def put(self, key: str, body: bytes, *, content_type: str) -> str:
        self.puts.append((key, body, content_type))
        return f"https://fake-published-assets.example/{key}"


class _FakeDocsClient:
    def __init__(self) -> None:
        self.created: list[tuple[str, str, str]] = []
        self.shared: list[tuple[str, list[str] | None, str]] = []

    async def create_doc_from_html(
        self, title: str, html: str, *, description: str = "", parent_id: str | None = None
    ) -> DocRef:
        doc_id = f"doc-{len(self.created) + 1}"
        self.created.append((title, html, description))
        return DocRef(doc_id=doc_id, url=f"https://docs.google.com/document/d/{doc_id}/edit")

    async def share_file(self, doc_id: str, *, emails=None, role: str = "commenter") -> None:
        self.shared.append((doc_id, emails, role))


def _attach(
    store: WorkStateStore | None,
    content: GitContentStore | None,
    brain: GitBrain | None,
    *,
    docs_client=None,
    storage=None,
) -> None:
    app.state.work_state = store
    app.state.git_content = content
    app.state.git_brain = brain
    app.state.piece_machine = PieceMachine(store, JobRunner(store, StepRegistry())) if store else None
    app.state.publish_docs_client = docs_client
    app.state.publish_storage = storage


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_publish_over_http(content_store: GitContentStore, git_brain: GitBrain) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["publish_http"])
    sha = content_store.revision_history(SLUG, max_count=1)[0].sha
    piece = await store.pieces.insert(
        Piece(slug=SLUG, voice="demo-mira", stage=PieceStage.finalized, latest_revision=sha)
    )
    _attach(store, content_store, git_brain, docs_client=_FakeDocsClient(), storage=_FakeStorage())

    async with _client() as client:
        resp = await client.post(f"/api/pieces/{piece.id}/publish")

    assert resp.status_code == 200
    body = resp.json()
    assert body["stage"] == "released"
    assert body["published_release"] == 1
    assert body["published_html_url"]
    assert body["published_doc_url"]

    updated = await store.pieces.get(piece.id)
    assert PieceStage(updated.stage) == PieceStage.released


async def test_publish_404_unknown_piece(content_store: GitContentStore, git_brain: GitBrain) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["publish_404"])
    _attach(store, content_store, git_brain, docs_client=_FakeDocsClient(), storage=_FakeStorage())
    async with _client() as client:
        resp = await client.post("/api/pieces/nonexistent/publish")
    assert resp.status_code == 404


async def test_publish_409_wrong_stage(content_store: GitContentStore, git_brain: GitBrain) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["publish_409"])
    piece = await store.pieces.insert(Piece(slug=SLUG, voice="demo-mira", stage=PieceStage.review))
    _attach(store, content_store, git_brain, docs_client=_FakeDocsClient(), storage=_FakeStorage())
    async with _client() as client:
        resp = await client.post(f"/api/pieces/{piece.id}/publish")
    assert resp.status_code == 409


async def test_publish_400_no_revision(content_store: GitContentStore, git_brain: GitBrain) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["publish_400"])
    piece = await store.pieces.insert(Piece(slug=SLUG, voice="demo-mira", stage=PieceStage.finalized))
    _attach(store, content_store, git_brain, docs_client=_FakeDocsClient(), storage=_FakeStorage())
    async with _client() as client:
        resp = await client.post(f"/api/pieces/{piece.id}/publish")
    assert resp.status_code == 400


async def test_publish_503_when_bucket_unconfigured(content_store: GitContentStore, git_brain: GitBrain) -> None:
    """No fake storage attached, and no PUBLISHED_ASSETS_BUCKET in this test environment — proves
    the route degrades cleanly rather than attempting (and failing) a real, uncredentialed AWS
    call. This is the exact "click Publish against an unconfigured deploy" path a live UI check
    against a local stack with no real bucket/credentials also exercises."""
    store = WorkStateStore(AsyncMongoMockClient()["publish_503_bucket"])
    sha = content_store.revision_history(SLUG, max_count=1)[0].sha
    piece = await store.pieces.insert(
        Piece(slug=SLUG, voice="demo-mira", stage=PieceStage.finalized, latest_revision=sha)
    )
    _attach(store, content_store, git_brain, docs_client=_FakeDocsClient(), storage=None)
    async with _client() as client:
        resp = await client.post(f"/api/pieces/{piece.id}/publish")
    assert resp.status_code == 503


async def test_publish_503_when_docs_client_unconfigured(content_store: GitContentStore, git_brain: GitBrain) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["publish_503_docs"])
    sha = content_store.revision_history(SLUG, max_count=1)[0].sha
    piece = await store.pieces.insert(
        Piece(slug=SLUG, voice="demo-mira", stage=PieceStage.finalized, latest_revision=sha)
    )
    _attach(store, content_store, git_brain, docs_client=None, storage=_FakeStorage())
    async with _client() as client:
        resp = await client.post(f"/api/pieces/{piece.id}/publish")
    assert resp.status_code == 503


async def test_publish_503_when_unconfigured() -> None:
    _attach(None, None, None)
    async with _client() as client:
        resp = await client.post("/api/pieces/anything/publish")
    assert resp.status_code == 503


async def test_publish_derivative_409_gate_blocked(content_store: GitContentStore, git_brain: GitBrain) -> None:
    """Derivative quality bar: a native derivative that has not cleared its OWN council at 9/10
    is refused at publish time (409), before any external side effect."""
    from app.models import PieceRole

    store = WorkStateStore(AsyncMongoMockClient()["publish_derivative_gate"])
    sha = content_store.revision_history(SLUG, max_count=1)[0].sha
    piece = await store.pieces.insert(
        Piece(
            slug=SLUG,
            voice="demo-mira",
            stage=PieceStage.finalized,
            latest_revision=sha,
            role=PieceRole.derivative,
            target="linkedin-post",
        )
    )
    storage = _FakeStorage()
    _attach(store, content_store, git_brain, docs_client=_FakeDocsClient(), storage=storage)
    async with _client() as client:
        resp = await client.post(f"/api/pieces/{piece.id}/publish")
    assert resp.status_code == 409
    assert "no council on record" in resp.json()["detail"]
    assert storage.puts == []  # nothing shipped
