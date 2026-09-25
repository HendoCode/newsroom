"""HTTP-surface tests for the review round-trip routes (open-decisions Item 7).

Drives ``/api/pieces/{id}/review/...`` end-to-end over ASGI with the work-state store, Git content
store, and a fake Docs client attached directly to ``app.state`` (mirroring
``test_lessons_routes.py``'s ``app.state.llm_provider`` pattern via the new
``app.state.review_docs_client`` override point). No Mongo server, no network, no credentials.
"""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.git import GitContentStore
from app.main import app
from app.models import DocRef, Piece, PieceStage, ReviewRound, ReviewRoundStatus, ShareMode
from app.repositories import WorkStateStore
from app.review.docs_client import DocRef as GoogleDocRef

SLUG = "token-vs-storage"


class _FakeDocsClient:
    """``document_html`` defaults to empty — irrelevant for the mint-only tests below, which never
    reach the diff half at all; ``test_preview_over_http`` overrides it with a real "no changes"
    fixture."""

    def __init__(self, document_html: str = "") -> None:
        self.created: list[tuple[str, str, str]] = []
        self.shared: list[tuple[str, list[str] | None, str]] = []
        self._document_html = document_html

    async def create_doc_from_html(
        self, title: str, html: str, *, description: str = "", parent_id: str | None = None
    ) -> GoogleDocRef:
        doc_id = f"doc-{len(self.created) + 1}"
        self.created.append((title, html, description))
        return GoogleDocRef(doc_id=doc_id, url=f"https://docs.google.com/document/d/{doc_id}/edit")

    async def share_file(self, doc_id: str, *, emails=None, role: str = "commenter") -> None:
        self.shared.append((doc_id, emails, role))

    async def list_comments(self, doc_id: str):
        return []

    async def get_document_html(self, doc_id: str) -> str:
        return self._document_html


def _attach(
    store: WorkStateStore | None,
    content: GitContentStore | None,
    docs_client: _FakeDocsClient | None = None,
) -> None:
    app.state.work_state = store
    app.state.git_content = content
    app.state.review_docs_client = docs_client


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_mint_over_http(content_store: GitContentStore) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["review_mint"])
    sha = content_store.revision_history(SLUG, max_count=1)[0].sha
    piece = await store.pieces.insert(
        Piece(slug=SLUG, voice="demo-mira", stage=PieceStage.review, latest_revision=sha)
    )
    _attach(store, content_store, _FakeDocsClient())

    async with _client() as client:
        resp = await client.post(
            f"/api/pieces/{piece.id}/review/mint",
            json={"share_mode": "internal"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["round_number"] == 1
    assert body["share_mode"] == "internal"
    assert body["doc_url"]
    assert body["warnings"] == []

    updated = await store.pieces.get(piece.id)
    assert updated.current_review_round_id


async def test_mint_external_returns_warnings(content_store: GitContentStore) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["review_mint_ext"])
    sha = content_store.revision_history(SLUG, max_count=1)[0].sha
    piece = await store.pieces.insert(
        Piece(
            slug=SLUG, voice="demo-mira", stage=PieceStage.review, latest_revision=sha,
            open_gaps=2, open_clearances=0,
        )
    )
    _attach(store, content_store, _FakeDocsClient())

    async with _client() as client:
        resp = await client.post(
            f"/api/pieces/{piece.id}/review/mint",
            json={"share_mode": "external", "reviewer_emails": ["a@x.com"]},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["share_mode"] == "external"
    assert len(body["warnings"]) == 1
    assert "2 open GAP" in body["warnings"][0]


async def test_mint_404_unknown_piece(content_store: GitContentStore) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["review_mint_404"])
    _attach(store, content_store, _FakeDocsClient())
    async with _client() as client:
        resp = await client.post("/api/pieces/nonexistent/review/mint", json={})
    assert resp.status_code == 404


async def test_mint_409_wrong_stage(content_store: GitContentStore) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["review_mint_409"])
    piece = await store.pieces.insert(Piece(slug=SLUG, voice="demo-mira", stage=PieceStage.council))
    _attach(store, content_store, _FakeDocsClient())
    async with _client() as client:
        resp = await client.post(f"/api/pieces/{piece.id}/review/mint", json={})
    assert resp.status_code == 409


async def test_mint_external_with_open_clearances_returns_409(content_store: GitContentStore) -> None:
    """Open clearances → hard block (409). The brain's feedback-intake.md requires external
    sharing to be blocked when clearances remain unresolved."""
    store = WorkStateStore(AsyncMongoMockClient()["review_mint_clearance_409"])
    sha = content_store.revision_history(SLUG, max_count=1)[0].sha
    piece = await store.pieces.insert(
        Piece(
            slug=SLUG, voice="demo-mira", stage=PieceStage.review, latest_revision=sha,
            open_gaps=0, open_clearances=1,
        )
    )
    _attach(store, content_store, _FakeDocsClient())

    async with _client() as client:
        resp = await client.post(
            f"/api/pieces/{piece.id}/review/mint",
            json={"share_mode": "external"},
        )

    assert resp.status_code == 409
    body = resp.json()
    assert "1 open clearance" in body["detail"]


async def test_mint_external_with_both_gaps_and_clearances_returns_409(content_store: GitContentStore) -> None:
    """Both GAPs and clearances → hard block (clearances take priority)."""
    store = WorkStateStore(AsyncMongoMockClient()["review_mint_both_409"])
    sha = content_store.revision_history(SLUG, max_count=1)[0].sha
    piece = await store.pieces.insert(
        Piece(
            slug=SLUG, voice="demo-mira", stage=PieceStage.review, latest_revision=sha,
            open_gaps=2, open_clearances=1,
        )
    )
    _attach(store, content_store, _FakeDocsClient())

    async with _client() as client:
        resp = await client.post(
            f"/api/pieces/{piece.id}/review/mint",
            json={"share_mode": "external"},
        )

    assert resp.status_code == 409
    body = resp.json()
    assert "1 open clearance" in body["detail"]


async def test_mint_400_no_revision(content_store: GitContentStore) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["review_mint_400"])
    piece = await store.pieces.insert(Piece(slug=SLUG, voice="demo-mira", stage=PieceStage.review))
    _attach(store, content_store, _FakeDocsClient())
    async with _client() as client:
        resp = await client.post(f"/api/pieces/{piece.id}/review/mint", json={})
    assert resp.status_code == 400


async def test_mint_no_google_opens_round_without_doc(content_store: GitContentStore) -> None:
    """When Google Docs OAuth is unconfigured, mint still opens a ReviewRound locally so
    reviews-done has a round to work with; the response carries no doc_url and a warning."""
    store = WorkStateStore(AsyncMongoMockClient()["review_mint_no_google"])
    sha = content_store.revision_history(SLUG, max_count=1)[0].sha
    piece = await store.pieces.insert(
        Piece(slug=SLUG, voice="demo-mira", stage=PieceStage.review, latest_revision=sha)
    )
    _attach(store, content_store, docs_client=None)  # no fake, and no real creds in this env
    async with _client() as client:
        resp = await client.post(f"/api/pieces/{piece.id}/review/mint", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["round_number"] == 1
    assert body["doc_url"] is None
    assert any("Google Docs OAuth" in w for w in body["warnings"])

    updated = await store.pieces.get(piece.id)
    assert updated.current_review_round_id


async def test_review_503_when_unconfigured() -> None:
    _attach(None, None, None)
    async with _client() as client:
        mint_resp = await client.post("/api/pieces/anything/review/mint", json={})
        preview_resp = await client.get("/api/pieces/anything/review/preview")
    assert mint_resp.status_code == 503
    assert preview_resp.status_code == 503


async def test_preview_over_http(content_store: GitContentStore) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["review_preview"])
    sha = content_store.revision_history(SLUG, max_count=1)[0].sha
    piece = await store.pieces.insert(Piece(slug=SLUG, voice="demo-mira", stage=PieceStage.review, latest_revision=sha))
    await store.review_rounds.insert(
        ReviewRound(
            piece_id=piece.id,
            round_number=1,
            minted_from_revision=sha,
            doc=DocRef(doc_id="doc-1", url="https://docs.google.com/x", share_mode=ShareMode.internal),
            status=ReviewRoundStatus.open,
        )
    )
    unchanged_html = content_store.read_draft(SLUG)  # internal round keeps the block, unstripped
    _attach(store, content_store, _FakeDocsClient(document_html=unchanged_html))

    async with _client() as client:
        resp = await client.get(f"/api/pieces/{piece.id}/review/preview")

    assert resp.status_code == 200
    body = resp.json()
    assert body["round_number"] == 1
    assert body["no_changes"] is True  # no comments, and the Doc text matches the frozen revision


async def test_preview_404_when_no_open_round(content_store: GitContentStore) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["review_preview_404"])
    piece = await store.pieces.insert(Piece(slug=SLUG, voice="demo-mira", stage=PieceStage.review))
    _attach(store, content_store, _FakeDocsClient())
    async with _client() as client:
        resp = await client.get(f"/api/pieces/{piece.id}/review/preview")
    assert resp.status_code == 404
