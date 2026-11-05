"""Release semantics: approval validity + the AuthorizeRelease doctrine.

See ``README.md`` for the authority seam the queued authority-model task will wrap.
"""

from app.release.approval import ApprovalStatus, approval_status
from app.release.errors import ApprovalInvalidated, NotInFinalizedStage, NotReleasableStage

__all__ = [
    "ApprovalInvalidated",
    "ApprovalStatus",
    "NotInFinalizedStage",
    "NotReleasableStage",
    "approval_status",
]
