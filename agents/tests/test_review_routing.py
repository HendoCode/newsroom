"""ROUTE + CLOSE tests (feedback-intake.md §4/§5) — no silent drops for any non-fix item."""

from __future__ import annotations

from app.models import (
    FeedbackStatus,
    FeedbackType,
    InterviewStatus,
    Piece,
    SpikeOriginKind,
    SpikeStatus,
)
from app.review.classify import ClassifiedFeedback
from app.review.collect import RawFeedbackItem
from app.review.routing import route_non_fix_items


async def _piece(store, **overrides) -> Piece:
    piece = Piece(slug="token-vs-storage", voice="demo-mira", **overrides)
    return await store.pieces.insert(piece)


async def test_info_gap_opens_a_targeted_interview(store):
    piece = await _piece(store)
    item = ClassifiedFeedback(
        raw=RawFeedbackItem(ask="what was the real dollar figure?", reviewer="Alice", comment_id="c1"),
        type=FeedbackType.info_gap,
    )

    outcome = await route_non_fix_items(store, piece, "round-1", [item])

    assert len(outcome.persisted) == 1
    persisted = outcome.persisted[0]
    assert persisted.status == FeedbackStatus.routed
    assert persisted.type == FeedbackType.info_gap

    interviews = await store.interviews.by_piece(piece.id)
    assert len(interviews) == 1
    assert interviews[0].is_gap_interview is True
    assert interviews[0].status == InterviewStatus.open
    assert interviews[0].about == "what was the real dollar figure?"
    assert str(interviews[0].id) in persisted.notes

    assert outcome.replies == [("c1", outcome.replies[0][1])]
    assert any("info-gap routed to targeted interview" in line for line in outcome.routing_log)


async def test_clearance_routes_to_the_piece_owner(store):
    piece = await _piece(store, owner="demo-mira@x.com")
    item = ClassifiedFeedback(
        raw=RawFeedbackItem(ask="can we name Dairyland Power publicly?", comment_id="c2"),
        type=FeedbackType.clearance,
    )

    outcome = await route_non_fix_items(store, piece, "round-1", [item])

    persisted = outcome.persisted[0]
    assert persisted.status == FeedbackStatus.routed
    assert "demo-mira@x.com" in persisted.notes
    assert any("clearance routed to owner demo-mira@x.com" in line for line in outcome.routing_log)


async def test_clearance_with_no_owner_routes_to_unassigned(store):
    piece = await _piece(store)  # no owner set
    item = ClassifiedFeedback(raw=RawFeedbackItem(ask="clear this figure?"), type=FeedbackType.clearance)

    outcome = await route_non_fix_items(store, piece, "round-1", [item])

    assert "unassigned" in outcome.persisted[0].notes


async def test_out_of_scope_parks_a_vault_spike_never_discarded(store):
    piece = await _piece(store)
    item = ClassifiedFeedback(
        raw=RawFeedbackItem(ask="totally unrelated request about a different piece"),
        type=FeedbackType.out_of_scope,
    )

    outcome = await route_non_fix_items(store, piece, "round-1", [item])

    persisted = outcome.persisted[0]
    assert persisted.status == FeedbackStatus.rejected
    assert "Vault" in persisted.notes

    vault = await store.spikes.vault()
    assert len(vault) == 1
    assert vault[0].origin.kind == SpikeOriginKind.feedback
    assert vault[0].status == SpikeStatus.vaulted
    assert vault[0].convergence_score is None


async def test_only_doc_anchored_items_get_a_reply(store):
    piece = await _piece(store)
    items = [
        ClassifiedFeedback(raw=RawFeedbackItem(ask="from a comment", comment_id="c1"), type=FeedbackType.clearance),
        ClassifiedFeedback(raw=RawFeedbackItem(ask="from a diff-detected edit", comment_id=None), type=FeedbackType.out_of_scope),
    ]

    outcome = await route_non_fix_items(store, piece, "round-1", items)

    assert len(outcome.replies) == 1
    assert outcome.replies[0][0] == "c1"


async def test_no_silent_drops_every_item_gets_a_terminal_status_and_log_line(store):
    piece = await _piece(store, owner="owner@x.com")
    items = [
        ClassifiedFeedback(raw=RawFeedbackItem(ask="a"), type=FeedbackType.info_gap),
        ClassifiedFeedback(raw=RawFeedbackItem(ask="b"), type=FeedbackType.clearance),
        ClassifiedFeedback(raw=RawFeedbackItem(ask="c"), type=FeedbackType.out_of_scope),
    ]

    outcome = await route_non_fix_items(store, piece, "round-1", items)

    assert len(outcome.persisted) == 3
    assert len(outcome.routing_log) == 3
    assert all(FeedbackStatus(p.status) in (FeedbackStatus.routed, FeedbackStatus.rejected) for p in outcome.persisted)
