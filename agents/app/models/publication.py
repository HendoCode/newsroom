"""Publication Releases + trivial-edit waivers (cmw-release-semantics-impl).

A Piece reaching ``released`` is the terminal *stage*. What actually shipped is a separate,
repeatable, **immutable numbered Publication Release**. Re-authorizing never overwrites a prior
release (an already-circulating link keeps resolving); it appends release N+1.

The machine never creates one of these. The only writer is an explicit human
``AuthorizeRelease`` (the content-workflow command, or the piece-detail HITL button that runs
the same service). See ``app/release/README.md`` for the authority seam the queued
authority-model task will wrap.

Final-pass canonical edits after an approval are gated here too: a ``TrivialEditWaiver`` is the
explicit, recorded path that keeps an approval valid across a trivial revision change. Without
one, a differing ``latest_revision`` invalidates the approval and AuthorizeRelease refuses
until the revision is re-accepted.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.common import MongoModel
from app.models.review_round import DocRef


class ReleaseActor(BaseModel):
    """Who authorized a release or recorded a waiver. Attribution only — never a permission gate
    (flat auth, §1.17). The queued authority-model task will consult project assignments against
    this actor; this ticket only records them."""

    subject_id: str
    email: str | None = None
    display_name: str | None = None


class PublicationRelease(MongoModel):
    """One immutable, numbered publication of a piece.

    ``release_number`` is 1-indexed and unique per piece. Insert-only: there is no legitimate
    update of an existing release (see ``PublicationReleaseRepository.update``).
    """

    piece_id: str
    content_project_id: str | None = None
    release_number: int = Field(ge=1)
    revision: str
    authorized_by: ReleaseActor
    authorized_at: datetime
    html_url: str | None = None
    pdf_url: str | None = None
    doc: DocRef | None = None
    warnings: list[str] = Field(default_factory=list)


class TrivialEditWaiver(MongoModel):
    """A recorded assertion that the canonical edit from ``from_revision`` to ``to_revision``
    is trivial and does not need council re-approval. Actor + reason ARE the audit trail —
    a waiver is never silent (same doctrine as the research-v1 experiential waiver)."""

    piece_id: str
    content_project_id: str | None = None
    from_revision: str
    to_revision: str
    actor: ReleaseActor
    reason: str = Field(min_length=1)
    recorded_at: datetime
