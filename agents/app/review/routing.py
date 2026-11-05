"""ROUTE + CLOSE: fan out every non-editorial-fix item, no silent drops (feedback-intake.md §4/§5).

    information gap → route to Step 2 (a targeted interview) and ask JUST that question.
    clearance       → route to the named owner.
    out-of-scope    → park in the Vault; note why it's not being applied.

Editorial-fix items never reach this module — they are the :mod:`app.review.rewrite` call's own
input and are persisted as ``applied`` by :mod:`app.review.step` once the rewrite actually lands a
new revision. Every item routed here is persisted as a :class:`~app.models.FeedbackItem` (Mongo
system-of-record, §5-Q3) with a terminal ``status`` and a human-readable ``notes`` explaining the
disposition — never silently dropped. A one-line routing-log entry per item is returned for
:class:`~app.models.ReviewRound.routing_log` (the auditable "which items were applied, which
routed... which were vaulted" Item 7 calls for), and — for items anchored to a real Doc comment — a
close-the-loop reply line for :meth:`~app.review.docs_client.ReviewDocsClient.reply_to_comment`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models import (
    FeedbackItem,
    FeedbackStatus,
    FeedbackType,
    Interview,
    Piece,
    Spike,
    SpikeOrigin,
    SpikeOriginKind,
    SpikeStatus,
)
from app.repositories import WorkStateStore
from app.review.classify import ClassifiedFeedback

_ASK_PREVIEW = 80


@dataclass(frozen=True)
class RoutingOutcome:
    persisted: list[FeedbackItem] = field(default_factory=list)
    routing_log: list[str] = field(default_factory=list)
    # (comment_id, reply text) pairs — only for items anchored to a real Doc comment.
    replies: list[tuple[str, str]] = field(default_factory=list)


async def route_non_fix_items(
    store: WorkStateStore,
    piece: Piece,
    review_round_id: str,
    classified: list[ClassifiedFeedback],
) -> RoutingOutcome:
    """Route every item whose type isn't ``editorial-fix``. Assumes ``classified`` is pre-filtered
    (:mod:`app.review.step` splits the batch before calling in)."""
    assert piece.id is not None
    persisted: list[FeedbackItem] = []
    log: list[str] = []
    replies: list[tuple[str, str]] = []

    for c in classified:
        raw, ftype = c.raw, c.type
        preview = raw.ask.strip()[:_ASK_PREVIEW]

        if ftype == FeedbackType.info_gap:
            interview = await store.interviews.insert(
                Interview(piece_id=piece.id, about=raw.ask, is_gap_interview=True)
            )
            notes = f"routed to targeted interview {interview.id}"
            status = FeedbackStatus.routed
            log.append(f"info-gap routed to targeted interview {interview.id}: {preview!r}")
            reply = "Thanks — that needs the author's input, so I opened a targeted follow-up interview for it."
        elif ftype == FeedbackType.clearance:
            owner = piece.owner or "unassigned"
            notes = f"routed to owner {owner} for sign-off"
            status = FeedbackStatus.routed
            log.append(f"clearance routed to owner {owner}: {preview!r}")
            reply = f"Flagged to {owner} for clearance sign-off."
        else:  # FeedbackType.out_of_scope
            spike = await store.spikes.insert(
                Spike(
                    headline=preview or "out-of-scope review feedback",
                    status=SpikeStatus.vaulted,
                    creator=piece.owner or "unknown",
                    origin=SpikeOrigin(kind=SpikeOriginKind.feedback),
                )
            )
            notes = f"parked in the Vault (spike {spike.id}) — out of scope for this piece"
            status = FeedbackStatus.rejected
            log.append(f"out-of-scope parked to Vault as spike {spike.id}: {preview!r}")
            reply = "Noted, but out of scope for this piece — parked in the Vault for later."

        item = await store.feedback.insert(
            FeedbackItem(
                piece_id=piece.id,
                review_round_id=review_round_id,
                reviewer=raw.reviewer,
                channel=raw.channel,
                location=raw.location,
                ask=raw.ask,
                type=ftype,
                status=status,
                notes=notes,
            )
        )
        persisted.append(item)
        if raw.comment_id:
            replies.append((raw.comment_id, reply))

    return RoutingOutcome(persisted=persisted, routing_log=log, replies=replies)
