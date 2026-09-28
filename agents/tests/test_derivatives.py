"""Derivative lineage: child artifacts of the anchor, promoted to Pieces on demand."""

from __future__ import annotations

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.derivatives.errors import DerivativeAlreadyExists, DerivativeAlreadyPromoted, DerivativeNotFound
from app.derivatives.service import DerivativesService
from app.models import DerivativeLineage, Piece, PieceRole, PieceStage
from app.repositories import WorkStateStore


async def _store() -> WorkStateStore:
    return WorkStateStore(AsyncMongoMockClient()["derivatives"])


async def _anchor(store: WorkStateStore) -> Piece:
    return await store.pieces.insert(
        Piece(slug="the-board-on-the-wall", voice="demo-mira", title="Token vs storage", stage=PieceStage.released)
    )


@pytest.mark.asyncio
async def test_create_child_is_not_a_piece() -> None:
    store = await _store()
    anchor = await _anchor(store)
    service = DerivativesService(store)

    artifact = await service.create_child(anchor.id, destination="linkedin")
    assert artifact.lineage == DerivativeLineage.child
    assert artifact.promoted_piece_id is None
    assert artifact.anchor_piece_id == anchor.id
    assert artifact.title == "Token vs storage — linkedin"
    assert artifact.voice == "demo-mira"

    pieces = await store.pieces.find({})
    assert [p.id for p in pieces] == [anchor.id]


@pytest.mark.asyncio
async def test_duplicate_destination_is_conflict() -> None:
    store = await _store()
    anchor = await _anchor(store)
    service = DerivativesService(store)
    await service.create_child(anchor.id, destination="linkedin")
    with pytest.raises(DerivativeAlreadyExists):
        await service.create_child(anchor.id, destination="linkedin")


@pytest.mark.asyncio
async def test_promote_mints_a_top_level_piece_with_parent() -> None:
    store = await _store()
    anchor = await _anchor(store)
    service = DerivativesService(store)
    artifact = await service.create_child(
        anchor.id, destination="linkedin-post", title="Token vs storage — LinkedIn"
    )

    promoted, piece = await service.promote(anchor.id, artifact.id, owner="alex@example.com")
    assert promoted.lineage == DerivativeLineage.promoted
    assert promoted.promoted_piece_id == piece.id
    assert piece.role == PieceRole.derivative
    assert piece.parent_piece_id == anchor.id
    assert piece.owner == "alex@example.com"
    assert piece.stage == PieceStage.interviewing
    assert piece.target == "linkedin-post"
    assert piece.slug == "the-board-on-the-wall-linkedin-post"

    with pytest.raises(DerivativeAlreadyPromoted):
        await service.promote(anchor.id, artifact.id)


@pytest.mark.asyncio
async def test_promote_unknown_or_wrong_anchor_is_not_found() -> None:
    store = await _store()
    anchor = await _anchor(store)
    other = await store.pieces.insert(Piece(slug="other", voice="demo-dana", title="Other"))
    service = DerivativesService(store)
    artifact = await service.create_child(anchor.id, destination="x-thread")

    with pytest.raises(DerivativeNotFound):
        await service.promote(other.id, artifact.id)
    with pytest.raises(DerivativeNotFound):
        await service.promote(anchor.id, "missing")
