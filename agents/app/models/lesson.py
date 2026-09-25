"""Proposed Lesson (domain model §1.18, §5-Q4).

A generalizable, per-voice writing rule captured by diffing a piece's final draft against its
edited version. The D12 human gate is the **store boundary**:

- a **proposed** (pending) Lesson → **Mongo work-state** (this model);
- an **accepted** Lesson → **Git brain** (appended to ``voice/<voice>/content-lessons.md`` by
  ``app.git`` — the machine never self-commits to the brain).

Invariants (§1.18): the machine never self-commits (status starts ``proposed``); lessons are
**per-voice** (Demo-mira's edits teach Demo-mira's file, never Demo-dana's); only generalizable keepers.
"""

from __future__ import annotations

from enum import Enum

from app.models.common import MongoModel


class LessonStatus(str, Enum):
    proposed = "proposed"
    accepted = "accepted"  # terminal in Mongo; the rule is committed to Git on acceptance
    rejected = "rejected"


class Lesson(MongoModel):
    voice: str  # home Voice slug — per-voice, never crosses voices
    source_piece_id: str | None = None
    observed_change: str  # what changed between the machine draft and the edited version
    generalizable_rule: str  # the rule that will (on acceptance) land in content-lessons.md
    status: LessonStatus = LessonStatus.proposed
