"""The review round-trip (open-decisions Item 7; domain model §1.14/§1.15; feedback-intake.md).

Mint a Google Doc from a piece's frozen revision for one review round (internal keeps the editorial
block; external strips it, adds the DRAFT banner, and warns-not-blocks on open GAPs/clearances,
D11), collect the humans' comments + inline edits, classify each (Sonnet 5, D14) into the bounded
``editorial-fix | info-gap | clearance | out-of-scope`` set, apply fixes via an Opus rewrite (D14)
that produces the next Revision, route everything else with no silent drops, and archive the round.
``IncorporateStep`` plugs this onto ``JobType.incorporate``; the human "reviews done" trigger
(already merged, ``app.orchestration.machine.PieceMachine.reviews_done``) dispatches it.

Builds on the merged orchestration core, LLM provider, Git/Mongo data layer, and the finalize
render's Google Docs push (:mod:`app.render.docs_export`) — touches none of them beyond the small
additive seams noted in their own modules.
"""

from __future__ import annotations

from app.review.classify import ClassifiedFeedback, ClassifyResult, classify_feedback
from app.review.collect import RawFeedbackItem, collect_comments, diff_edits, gather_raw_items
from app.review.docs_client import CommentThread, HttpReviewDocsClient, ReviewDocsClient
from app.review.errors import (
    FeedbackClassificationError,
    NoOpenReviewRound,
    NoRevisionToMint,
    NotInReviewStage,
    ReviewError,
    RewriteParseError,
)
from app.review.mint import MintResult, ReviewMintService, render_for_share_mode
from app.review.preview import ReviewPreview, preview_round
from app.review.rewrite import RewriteResult, count_open_gaps, rewrite_revision
from app.review.routing import RoutingOutcome, route_non_fix_items
from app.review.step import IncorporateStep

__all__ = [
    "ClassifiedFeedback",
    "ClassifyResult",
    "CommentThread",
    "FeedbackClassificationError",
    "HttpReviewDocsClient",
    "IncorporateStep",
    "MintResult",
    "NoOpenReviewRound",
    "NoRevisionToMint",
    "NotInReviewStage",
    "RawFeedbackItem",
    "ReviewDocsClient",
    "ReviewError",
    "ReviewMintService",
    "ReviewPreview",
    "RewriteParseError",
    "RewriteResult",
    "RoutingOutcome",
    "classify_feedback",
    "collect_comments",
    "count_open_gaps",
    "diff_edits",
    "gather_raw_items",
    "preview_round",
    "render_for_share_mode",
    "rewrite_revision",
    "route_non_fix_items",
]
