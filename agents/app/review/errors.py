"""Review round-trip errors (domain model §1.14/§1.15; open-decisions Item 7)."""

from __future__ import annotations


class ReviewError(Exception):
    """Base for every error this package raises."""


class NotInReviewStage(ReviewError):
    """``mint()`` was called on a piece whose stage is not ``review`` (§1.9)."""


class NoRevisionToMint(ReviewError):
    """A piece has no committed revision yet — nothing to mint a Doc from."""


class NoOpenReviewRound(ReviewError):
    """"reviews done" fired with no open :class:`~app.models.ReviewRound` to incorporate."""


class FeedbackClassificationError(ReviewError):
    """The Sonnet classification call did not return a parseable per-item type array."""


class RewriteParseError(ReviewError):
    """The Opus rewrite call returned no usable ``draft.html``."""


class UnsafeExternalShareError(ReviewError):
    """External sharing is blocked because the piece still has open clearance(s) or
    disclosure-sensitive material that must be resolved first — a hard block, not a warning
    (engine/feedback-intake.md: "Never share externally while `piece.md` lists open clearances.
    When in doubt, ask."). The caller receives a 409 with the clearance count and a message
    telling them what to resolve before re-trying."""
