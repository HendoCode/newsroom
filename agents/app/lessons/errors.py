"""Lessons-loop errors (domain model §1.18; D12 human-gate invariants)."""

from __future__ import annotations


class LessonsError(Exception):
    """Base for every error this module raises."""


class NotInLessonsStage(LessonsError):
    """``propose()`` was called on a piece whose stage is not ``lessons`` (§1.9)."""


class LessonNotPending(LessonsError):
    """``accept()``/``reject()`` was called on a Lesson that is not ``proposed`` (D12 gate)."""


class LessonsParseError(LessonsError):
    """The Opus lessons call did not return a parseable candidate list."""
