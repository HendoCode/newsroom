"""Pydantic models for the Mongo work-state entities (domain model §1, §3).

These are the persisted work-state documents — faithful to the domain model's identities,
attributes, and invariants. Git-owned entities (Voice packs, Personas, Revisions, Transcript,
accepted Lessons, BrandedTemplate) are NOT modeled here; they live in Git and are read/written by
``app.git``. The content-lake item + hybrid index is a separate downstream ticket (D9).
"""

from __future__ import annotations

from app.models.common import MongoModel, new_id, utcnow
from app.models.council import (
    MANDATORY_EDITORS,
    QUALITY_BAR,
    Council,
    EditorScore,
)
from app.models.drive import DriveFileRef
from app.models.feedback import FeedbackItem, FeedbackStatus, FeedbackType
from app.models.interview import Interview, InterviewStatus
from app.models.job import (
    Job,
    JobError,
    JobStatus,
    JobType,
    OracleEntryMode,
    OracleRunParams,
    OracleRunResultRecord,
)
from app.models.derivative import DerivativeArtifact, DerivativeLineage
from app.models.lesson import Lesson, LessonStatus
from app.models.narrative import DistributionIntent, Narrative
from app.models.piece import (
    ALLOWED_TRANSITIONS,
    Piece,
    PieceRole,
    PieceStage,
    can_transition,
    is_released_stage,
)
from app.models.publication import (
    PublicationRelease,
    ReleaseActor,
    TrivialEditWaiver,
)
from app.models.review_round import (
    DocRef,
    ReviewRound,
    ReviewRoundStatus,
    ShareMode,
)
from app.models.source import Source, SourceClassification, SourceKind
from app.models.spike import Spike, SpikeOrigin, SpikeOriginKind, SpikeStatus
from app.models.user import RoleLabel, User

__all__ = [
    "ALLOWED_TRANSITIONS",
    "MANDATORY_EDITORS",
    "QUALITY_BAR",
    "Council",
    "DerivativeArtifact",
    "DerivativeLineage",
    "DistributionIntent",
    "DocRef",
    "DriveFileRef",
    "EditorScore",
    "FeedbackItem",
    "FeedbackStatus",
    "FeedbackType",
    "Interview",
    "InterviewStatus",
    "Job",
    "JobError",
    "JobStatus",
    "JobType",
    "Lesson",
    "LessonStatus",
    "MongoModel",
    "Narrative",
    "OracleEntryMode",
    "OracleRunParams",
    "OracleRunResultRecord",
    "Piece",
    "PieceRole",
    "PieceStage",
    "PublicationRelease",
    "ReleaseActor",
    "TrivialEditWaiver",
    "ReviewRound",
    "ReviewRoundStatus",
    "RoleLabel",
    "ShareMode",
    "Source",
    "SourceClassification",
    "SourceKind",
    "Spike",
    "SpikeOrigin",
    "SpikeOriginKind",
    "SpikeStatus",
    "User",
    "can_transition",
    "is_released_stage",
    "new_id",
    "utcnow",
]
