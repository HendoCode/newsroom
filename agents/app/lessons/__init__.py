"""The lessons loop (domain model §1.18; D12; cmw-context-assembly report §9).

Runs in a piece's ``lessons`` stage: diff the machine's final draft against the author's
actually-published/edited version (structurally, via Git), propose generalizable per-voice lessons
(Opus tier) deduped against the voice's existing ``content-lessons.md``, persist them to Mongo as
pending, and expose an accept/edit/reject action that only commits to Git — the voice's
``content-lessons.md`` — on explicit human acceptance. The machine never self-commits.

Builds on the merged orchestration core, LLM provider, and Git/Mongo data layer; touches none of
them beyond the small additive seams noted in their own modules.
"""

from __future__ import annotations

from app.lessons.diff import DiffError, compute_diff
from app.lessons.errors import LessonNotPending, LessonsError, LessonsParseError, NotInLessonsStage
from app.lessons.service import LessonsService

__all__ = [
    "DiffError",
    "LessonNotPending",
    "LessonsError",
    "LessonsParseError",
    "LessonsService",
    "NotInLessonsStage",
    "compute_diff",
]
