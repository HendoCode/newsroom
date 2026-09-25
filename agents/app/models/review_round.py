"""ReviewRound + transient Doc metadata (domain model §1.14, §1.15).

One iteration of the Google-Doc review loop: a **frozen Revision** (Git, canonical) is minted into
a **transient Doc** (Google, authoritative only during the round's open window), humans mark it up,
and on the human "reviews done" trigger the round closes → incorporate → re-council → next round.

Only the round *metadata* and the Doc *link* live in Mongo (D3); the Doc *content* is transient in
Google Docs. FeedbackItems collected in the round are their own Mongo documents (see
``app.models.feedback``), referenced by ``review_round_id``.

Invariants (§1.14): round boundaries are explicit — a Doc is authoritative only during its open
window (D4). External share **warns, does not block** (D11). "reviews done" (→ another round) is
never conflated with "finalize" (→ branded render).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.models.common import MongoModel


class ShareMode(str, Enum):
    internal = "internal"
    external = "external"  # warns (strip editorial block + banner), never hard-blocks (D11)


class ReviewRoundStatus(str, Enum):
    open = "open"
    closed = "closed"
    archived = "archived"


class DocRef(BaseModel):
    """Link/metadata for the transient Google Doc minted for this round (content lives in Google)."""

    doc_id: str | None = None
    url: str | None = None
    share_mode: ShareMode = ShareMode.internal


class ReviewRound(MongoModel):
    piece_id: str
    round_number: int
    minted_from_revision: str  # Git ref/label of the frozen source Revision
    doc: DocRef = DocRef()
    opened_at: datetime | None = None
    status: ReviewRoundStatus = ReviewRoundStatus.open
    council_id: str | None = None  # the round's re-council record
    routing_log: list[str] = Field(default_factory=list)  # auditable record of what happened
