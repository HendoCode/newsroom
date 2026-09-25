"""Derivative quality bar: destination-specific councils + universal hard gates.

The registry half is pure; the publish-gate half runs against mongomock work-state with real
Council/Piece documents — no LLM, no Git.
"""

from __future__ import annotations

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.derivatives.quality import (
    DEFAULT_DESTINATION_EDITORS,
    DERIVATIVE_QUALITY_BAR,
    UNIVERSAL_GATE_NAMES,
    canonical_destination,
    derivative_council_editors,
    derivative_publish_gate,
    destination_fit_editors,
)
from app.models import Council, EditorScore, Piece, PieceRole, PieceStage
from app.models.council import MANDATORY_EDITORS
from app.repositories import WorkStateStore


async def _store() -> WorkStateStore:
    return WorkStateStore(AsyncMongoMockClient()["derivative-quality"])


# --- Registry --------------------------------------------------------------------------------


def test_canonical_destination_folds_whitespace_and_aliases() -> None:
    assert canonical_destination("LinkedIn Post") == "linkedin-post"
    assert canonical_destination("linkedin-post") == "linkedin-post"
    assert canonical_destination("whitepaper") == "executive-brief"
    assert canonical_destination("white-paper") == "executive-brief"
    assert canonical_destination("twitter") == "x-thread"
    assert canonical_destination("blog") == "blog"
    assert canonical_destination("  ") is None
    assert canonical_destination("podcast") is None


def test_linkedin_and_whitepaper_get_different_judgment() -> None:
    # The ticket's core claim: a LinkedIn post and a whitepaper need different editors.
    linkedin = destination_fit_editors("linkedin-post")
    whitepaper = destination_fit_editors("whitepaper")
    assert linkedin != whitepaper
    assert "puri" in linkedin  # the hook/scroll-stop judge fits a feed native
    assert "housel" in whitepaper  # durability/claims-under-weight fits a decision-maker native


def test_unknown_destination_gets_generic_judgment_not_exemption() -> None:
    assert destination_fit_editors("carrier-pigeon") == DEFAULT_DESTINATION_EDITORS


def test_full_lineup_mandatory_and_universal_first() -> None:
    lineup = derivative_council_editors("newsletter")
    assert MANDATORY_EDITORS <= set(lineup)
    assert lineup[0:2] == ("slop-allergist", "voice-guardian")
    assert "technical-reviewer" in lineup  # facts gate editor, universal
    # universal gates always appear before destination nuance
    assert max(lineup.index(e) for e in ("slop-allergist", "technical-reviewer")) < lineup.index(
        "perell"
    )
    assert len(lineup) == len(set(lineup))  # deduped


# --- Publish gate ------------------------------------------------------------------------------


async def _derivative_piece(
    store: WorkStateStore,
    *,
    latest_revision: str = "rev-current",
    open_clearances: int = 0,
) -> Piece:
    return await store.pieces.insert(
        Piece(
            slug="anchor-linkedin-post",
            voice="demo-dana",
            role=PieceRole.derivative,
            target="linkedin-post",
            stage=PieceStage.finalized,
            latest_revision=latest_revision,
            open_clearances=open_clearances,
        )
    )


async def _council(
    store: WorkStateStore,
    piece: Piece,
    *,
    revision: str = "rev-current",
    aggregate: float = 9.2,
    hard_caps: tuple[str, ...] = (),
) -> Council:
    editors = list(derivative_council_editors(piece.target or ""))
    council = Council(
        piece_id=piece.id or "",
        revision=revision,
        editor_scores=[
            EditorScore(editor=e, score=9.5, hard_cap_applied=e in hard_caps) for e in editors
        ],
        aggregate=aggregate,
    )
    return await store.councils.insert(council)


@pytest.mark.asyncio
async def test_gate_passes_through_non_derivatives() -> None:
    store = await _store()
    anchor = await store.pieces.insert(
        Piece(slug="anchor", voice="demo-dana", role=PieceRole.anchor, stage=PieceStage.finalized)
    )
    legacy = await store.pieces.insert(Piece(slug="legacy", voice="demo-dana"))

    for piece in (anchor, legacy):
        result = await derivative_publish_gate(store, piece)
        assert result.required is False
        assert result.cleared is True
        assert result.reasons == []


@pytest.mark.asyncio
async def test_gate_blocks_derivative_with_no_council_on_record() -> None:
    store = await _store()
    piece = await _derivative_piece(store)

    result = await derivative_publish_gate(store, piece)
    assert result.required is True
    assert result.cleared is False
    assert any("no council on record" in r for r in result.reasons)


@pytest.mark.asyncio
async def test_gate_blocks_below_the_bar() -> None:
    store = await _store()
    piece = await _derivative_piece(store)
    council = await _council(store, piece, aggregate=8.4)
    await store.pieces.update(piece.id, {"latest_council_id": council.id})
    piece = await store.pieces.get(piece.id)

    result = await derivative_publish_gate(store, piece)
    assert result.cleared is False
    assert result.aggregate == 8.4
    assert any("below the 9 derivative bar" in r for r in result.reasons)


@pytest.mark.asyncio
async def test_gate_blocks_universal_hard_cap_even_above_the_bar() -> None:
    store = await _store()
    piece = await _derivative_piece(store)
    # Facts gate tripped: technical-reviewer hard-capped, yet the mean is above 9.
    council = await _council(store, piece, aggregate=9.4, hard_caps=("technical-reviewer",))
    await store.pieces.update(piece.id, {"latest_council_id": council.id})
    piece = await store.pieces.get(piece.id)

    result = await derivative_publish_gate(store, piece)
    assert result.cleared is False
    assert any("universal hard gate failed: facts" in r for r in result.reasons)


@pytest.mark.asyncio
async def test_gate_blocks_safety_hard_cap() -> None:
    store = await _store()
    piece = await _derivative_piece(store)
    council = await _council(store, piece, aggregate=9.6, hard_caps=("slop-allergist",))
    await store.pieces.update(piece.id, {"latest_council_id": council.id})
    piece = await store.pieces.get(piece.id)

    result = await derivative_publish_gate(store, piece)
    assert result.cleared is False
    assert any("universal hard gate failed: safety" in r for r in result.reasons)


@pytest.mark.asyncio
async def test_gate_blocks_council_scored_an_older_revision() -> None:
    store = await _store()
    piece = await _derivative_piece(store, latest_revision="rev-new")
    council = await _council(store, piece, revision="rev-old", aggregate=9.8)
    await store.pieces.update(piece.id, {"latest_council_id": council.id})
    piece = await store.pieces.get(piece.id)

    result = await derivative_publish_gate(store, piece)
    assert result.cleared is False
    assert any("does not certify what would ship" in r for r in result.reasons)


@pytest.mark.asyncio
async def test_gate_blocks_open_clearances_as_safety() -> None:
    store = await _store()
    piece = await _derivative_piece(store, open_clearances=2)
    council = await _council(store, piece, aggregate=9.9)
    await store.pieces.update(piece.id, {"latest_council_id": council.id})
    piece = await store.pieces.get(piece.id)

    result = await derivative_publish_gate(store, piece)
    assert result.cleared is False
    assert any("safety hard gate blocks external publication" in r for r in result.reasons)


@pytest.mark.asyncio
async def test_gate_clears_a_derivative_that_cleared_its_own_council() -> None:
    store = await _store()
    piece = await _derivative_piece(store)
    council = await _council(store, piece, aggregate=DERIVATIVE_QUALITY_BAR)  # exactly 9.0 passes
    await store.pieces.update(piece.id, {"latest_council_id": council.id})
    piece = await store.pieces.get(piece.id)

    result = await derivative_publish_gate(store, piece)
    assert result.required is True
    assert result.cleared is True
    assert result.reasons == []
    assert result.aggregate == DERIVATIVE_QUALITY_BAR
    assert result.council_revision == "rev-current"


@pytest.mark.asyncio
async def test_universal_gate_names_are_facts_and_safety() -> None:
    assert UNIVERSAL_GATE_NAMES == ("facts", "safety")
