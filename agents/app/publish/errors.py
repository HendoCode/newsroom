"""Domain errors for the publish / AuthorizeRelease flow."""

from __future__ import annotations


class PublishError(RuntimeError):
    """Base class for every publish-flow domain error."""


class NotReleasableStage(PublishError):
    """AuthorizeRelease was attempted on a piece that is neither finalized nor already released."""


# Backward-compat alias: the pre-release-semantics error name.
NotInFinalizedStage = NotReleasableStage


class NoRevisionToPublish(PublishError):
    """The piece has no committed revision to publish."""


class ApprovalInvalidated(PublishError):
    """AuthorizeRelease was attempted against a piece whose accepted revision no longer matches
    the current canonical content, and no trivial-edit waiver covers the change."""


class DerivativeGateBlocked(PublishError):
    """AuthorizeRelease was attempted on a derivative piece that has not cleared its own
    destination-specific council at the derivative quality bar (9/10), or a universal hard gate
    (facts, safety) is tripped — see ``app.derivatives.quality.derivative_publish_gate``."""
