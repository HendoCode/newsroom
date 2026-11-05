"""Council — structured scoring result (domain model §1.13).

The Council is the selected set of Editors for a piece **and** the scoring event they produce
against **one Revision**. Per §5-Q3 the *structured* result (per-editor scores, aggregate, cost)
is the **Mongo system-of-record** that drives the dashboard/predicate/cost; a human-readable
summary is committed to ``sources.md`` in Git for lineage (handled by ``app.git``).

Invariants (§1.13):
- Mandatory editors — slop-allergist, voice-guardian — are always present and
  never skipped (enforced once the result is populated).
- Hard caps (slop-allergist / technical-reviewer) may cap a score regardless of merit.
- The quality bar is aggregate **≥ 9** (a threshold helper, not an invariant — a council may
  legitimately score below it and route back).
- One scoring pass per human round: a Council is scoped to ``(piece, revision, round)``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from app.models.common import MongoModel

# Mandatory editors that run on every piece and are never skipped (§1.13, engine/3-revision-loop).
MANDATORY_EDITORS: frozenset[str] = frozenset({"slop-allergist", "voice-guardian"})

# Alex's bar: the council drives toward an aggregate of at least this (engine/3-revision-loop.md).
QUALITY_BAR = 9.0


class EditorScore(BaseModel):
    editor: str  # persona name
    score: float = Field(ge=0, le=10)  # N/10
    editorial_fixes: list[str] = Field(default_factory=list)  # machine applies
    information_gaps: list[str] = Field(default_factory=list)  # route back to interview
    clearances: list[str] = Field(default_factory=list)  # human approval required
    hard_cap_applied: bool = False  # slop-allergist / technical-reviewer cap regardless of merit


class Council(MongoModel):
    piece_id: str
    revision: str  # the Git ref/label of the Revision that was scored
    round_number: int = 1
    iteration: int = 1  # autonomous sub-round within round_number
    editor_scores: list[EditorScore] = Field(default_factory=list)
    aggregate: float | None = None
    cost: float = 0.0
    stop_reason: str | None = None  # why the autonomous loop stopped
    stop_message: str | None = None  # human-readable stop detail

    @model_validator(mode="after")
    def _mandatory_editors_present(self) -> Council:
        if self.editor_scores:  # only once the result is populated
            present = {s.editor for s in self.editor_scores}
            missing = MANDATORY_EDITORS - present
            if missing:
                raise ValueError(
                    f"mandatory editors never skipped (§1.13): missing {sorted(missing)}"
                )
        return self

    def meets_bar(self) -> bool:
        """True if the aggregate clears the quality bar (≥ 9). Not an invariant — a threshold."""
        return self.aggregate is not None and self.aggregate >= QUALITY_BAR
