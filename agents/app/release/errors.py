"""Domain errors for AuthorizeRelease / approval validity.

Re-exported from ``app.publish.errors`` so both the HITL mint path and the content-workflow
command share one exception set.
"""

from __future__ import annotations

from app.publish.errors import (
    ApprovalInvalidated,
    NotInFinalizedStage,
    NotReleasableStage,
    NoRevisionToPublish,
    PublishError,
)

__all__ = [
    "ApprovalInvalidated",
    "NotInFinalizedStage",
    "NotReleasableStage",
    "NoRevisionToPublish",
    "PublishError",
]
