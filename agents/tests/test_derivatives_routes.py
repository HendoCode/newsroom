"""HTTP surface for derivative lineage."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.main import app
from app.models import Piece, PieceStage
from app.repositories import WorkStateStore


def _attach(store: WorkStateStore | None) -> None:
    app.state.work_state = store


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_create_list_promote_over_http() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["deriv_routes"])
    piece = await store.pieces.insert(
        Piece(slug="the-board-on-the-wall", voice="demo-mira", title="Token vs storage", stage=PieceStage.released)
    )
    _attach(store)

    async with _client() as client:
        created = await client.post(
            f"/api/pieces/{piece.id}/derivatives",
            json={"destination": "newsletter", "title": "Token vs storage — Newsletter"},
        )
        assert created.status_code == 201
        body = created.json()
        assert body["lineage"] == "child"
        assert body["promoted_piece_id"] is None
        # Derivative quality bar: a child is never publishable on its own.
        assert body["quality"]["required"] is True
        assert body["quality"]["cleared"] is False
        assert body["quality"]["universal_gates"] == ["facts", "safety"]
        assert "slop-allergist" in body["quality"]["editors"]

        listed = await client.get(f"/api/pieces/{piece.id}/derivatives")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [body["id"]]
        assert listed.json()[0]["quality"]["cleared"] is False

        promoted = await client.post(
            f"/api/pieces/{piece.id}/derivatives/{body['id']}/promote",
            json={"owner": "alex@example.com"},
        )
        assert promoted.status_code == 200
        assert promoted.json()["lineage"] == "promoted"
        assert promoted.json()["promoted_piece_id"]
        # Promoted, but no council on record yet: the gate reports required+not-cleared honestly.
        assert promoted.json()["quality"]["required"] is True
        assert promoted.json()["quality"]["cleared"] is False
        assert any("no council on record" in r for r in promoted.json()["quality"]["reasons"])

        again = await client.post(
            f"/api/pieces/{piece.id}/derivatives/{body['id']}/promote",
            json={},
        )
        assert again.status_code == 409

        dup = await client.post(
            f"/api/pieces/{piece.id}/derivatives",
            json={"destination": "newsletter"},
        )
        assert dup.status_code == 409


async def test_derivatives_quality_reflects_a_cleared_council() -> None:
    """A promoted derivative whose own council cleared 9/10 on the current revision reports
    cleared — the Derivatives tab's publish-readiness signal."""
    from app.derivatives.quality import derivative_council_editors
    from app.models import Council, EditorScore, PieceRole

    store = WorkStateStore(AsyncMongoMockClient()["deriv_quality"])
    anchor = await store.pieces.insert(
        Piece(slug="the-board-on-the-wall", voice="demo-mira", title="T", stage=PieceStage.released)
    )
    derivative = await store.pieces.insert(
        Piece(
            slug="the-board-on-the-wall-linkedin-post",
            voice="demo-mira",
            stage=PieceStage.finalized,
            role=PieceRole.derivative,
            target="linkedin-post",
            latest_revision="rev-1",
        )
    )
    editors = list(derivative_council_editors("linkedin-post"))
    council = await store.councils.insert(
        Council(
            piece_id=derivative.id or "",
            revision="rev-1",
            editor_scores=[EditorScore(editor=e, score=9.5) for e in editors],
            aggregate=9.2,
        )
    )
    await store.pieces.update(derivative.id, {"latest_council_id": council.id})
    from app.models import DerivativeArtifact, DerivativeLineage

    artifact = await store.derivatives.insert(
        DerivativeArtifact(
            anchor_piece_id=anchor.id,
            destination="linkedin-post",
            title="T — LinkedIn",
            lineage=DerivativeLineage.promoted,
            promoted_piece_id=derivative.id,
        )
    )
    _attach(store)

    async with _client() as client:
        listed = await client.get(f"/api/pieces/{anchor.id}/derivatives")
    assert listed.status_code == 200
    items = listed.json()
    assert [i["id"] for i in items] == [artifact.id]
    assert items[0]["quality"]["cleared"] is True
    assert items[0]["quality"]["aggregate"] == 9.2


async def test_derivatives_503_when_unconfigured() -> None:
    _attach(None)
    async with _client() as client:
        resp = await client.get("/api/pieces/any/derivatives")
    assert resp.status_code == 503


async def test_derivatives_404_unknown_piece() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["deriv_404"])
    _attach(store)
    async with _client() as client:
        resp = await client.get("/api/pieces/missing/derivatives")
    assert resp.status_code == 404
