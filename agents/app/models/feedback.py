"""FeedbackItem (domain model §1.15).

One transcribed review input in a piece's feedback inbox. Per §5-Q3 Mongo is the **system-of-
record** for status tracking; the agent's ``feedback.md`` is kept in Git as an audit mirror
(committed by ``app.git``).

Invariant: **no silent drops** — every item is classified by ``type`` and routed, its ``status``
tracked to a terminal state. Routing fan-out (§2.2): editorial-fix → next Revision; info-gap →
targeted Interview; clearance → named owner; out-of-scope → parked in the Vault.
"""

from __future__ import annotations

from enum import Enum

from app.models.common import MongoModel


class FeedbackType(str, Enum):
    editorial_fix = "editorial-fix"
    info_gap = "info-gap"
    clearance = "clearance"
    out_of_scope = "out-of-scope"


class FeedbackStatus(str, Enum):
    open = "open"
    applied = "applied"
    routed = "routed"
    rejected = "rejected"


class FeedbackItem(MongoModel):
    piece_id: str
    review_round_id: str | None = None
    reviewer: str | None = None  # User (email/id) or name
    channel: str | None = None
    location: str | None = None  # section / question the ask targets
    ask: str
    type: FeedbackType
    status: FeedbackStatus = FeedbackStatus.open
    notes: str | None = None
