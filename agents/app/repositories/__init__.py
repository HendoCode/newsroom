"""Async Mongo repository layer for the work-state collections (domain model §3)."""

from __future__ import annotations

from app.repositories.base import BaseRepository, mongo_encode
from app.repositories.repositories import (
    CouncilRepository,
    DerivativeRepository,
    FeedbackRepository,
    InterviewRepository,
    JobRepository,
    LessonRepository,
    NarrativeRepository,
    PieceRepository,
    PublicationReleaseRepository,
    ReviewRoundRepository,
    SourceRepository,
    SpikeRepository,
    TrivialEditWaiverRepository,
    UserRepository,
    WorkStateStore,
)

__all__ = [
    "BaseRepository",
    "CouncilRepository",
    "DerivativeRepository",
    "FeedbackRepository",
    "InterviewRepository",
    "JobRepository",
    "LessonRepository",
    "NarrativeRepository",
    "PieceRepository",
    "PublicationReleaseRepository",
    "ReviewRoundRepository",
    "SourceRepository",
    "SpikeRepository",
    "TrivialEditWaiverRepository",
    "UserRepository",
    "WorkStateStore",
    "mongo_encode",
]
