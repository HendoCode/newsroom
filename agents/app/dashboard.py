"""Dashboard read-model: the shared work queue (Item 3, cmw-open-decisions §Item-3).

Assembles denormalized :class:`~app.schemas.QueueItem` cards from the work-state entities so the
Next.js BFF can render the dashboard and compute the flat, attribution-only "needs my action"
predicate over them. This module owns the JOINS (a Piece ↔ its interviews / latest council / failed
jobs / proposed lessons / latest review round); the predicate itself is attribution-only and lives
in the web/ layer, where it is unit-tested.

The assembly (:func:`build_queue`) is pure over in-memory collections, so it runs identically
whether the collections come from the Mongo repositories (real work-state) or the built-in seed
(:func:`seed_work_state`, placeholder entities for the walking skeleton, before upstream
orchestration writes anything). Nothing here is a permission gate — every attribution field is
informational (§1.17): a hidden card is always reachable from the "All in flight" tab.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models import (
    Council,
    DocRef,
    EditorScore,
    Interview,
    InterviewStatus,
    Job,
    JobError,
    JobStatus,
    JobType,
    Lesson,
    LessonStatus,
    Piece,
    PieceStage,
    ReviewRound,
    ShareMode,
    Spike,
    SpikeOrigin,
    SpikeOriginKind,
    SpikeStatus,
    new_id,
    utcnow,
)
from app.repositories import WorkStateStore
from app.schemas import FailedJobRef, OpenInterviewRef, QueueItem

# The stages at which a failed batch job is still surfaced against the piece it belongs to.
# Failures flag but never roll back (Item 4); the piece sits at its last stable stage.
_FAILED_JOB_STATUSES = frozenset({JobStatus.failed.value, JobStatus.stuck.value})


@dataclass
class WorkStateCollections:
    """The raw work-state collections the dashboard read-model joins over."""

    pieces: list[Piece] = field(default_factory=list)
    spikes: list[Spike] = field(default_factory=list)
    interviews: list[Interview] = field(default_factory=list)
    jobs: list[Job] = field(default_factory=list)
    lessons: list[Lesson] = field(default_factory=list)
    councils: list[Council] = field(default_factory=list)
    review_rounds: list[ReviewRound] = field(default_factory=list)

    def is_empty(self) -> bool:
        """True when there is nothing to show (no pieces and no spikes) — trigger the seed."""
        return not self.pieces and not self.spikes


async def load_collections(store: WorkStateStore) -> WorkStateCollections:
    """Read every collection the dashboard joins over from the Mongo work-state store."""
    return WorkStateCollections(
        pieces=await store.pieces.find({}),
        spikes=await store.spikes.find({}),
        interviews=await store.interviews.find({}),
        jobs=await store.jobs.find({}),
        lessons=await store.lessons.find({}),
        councils=await store.councils.find({}),
        review_rounds=await store.review_rounds.find({}),
    )


def _latest_council_aggregate(councils: list[Council]) -> float | None:
    """The aggregate of the highest (round, iteration) council."""
    if not councils:
        return None
    latest = max(councils, key=lambda c: (c.round_number, c.iteration))
    return latest.aggregate


def _latest_round_number(rounds: list[ReviewRound]) -> int | None:
    return max((r.round_number for r in rounds), default=None)


def job_failure_ref(job: Job) -> FailedJobRef:
    """Convert one failed/stuck job into its wire shape (Item 4). Shared with ``app.piece_detail``,
    which lists every open failure rather than picking the single most-recent one."""
    err: JobError | None = job.error
    return FailedJobRef(
        type=job.type if isinstance(job.type, str) else job.type.value,
        code=err.code if err else "unknown",
        message=err.message if err else "job failed",
        triggered_by=job.triggered_by,
        retryable=err.retryable if err else False,
        cost=job.cost,
    )


def _failed_job(jobs: list[Job]) -> FailedJobRef | None:
    """The most recent failed/stuck job for a piece, if any (Item 4)."""
    failed = [j for j in jobs if j.status in _FAILED_JOB_STATUSES]
    if not failed:
        return None
    # Prefer the freshest by heartbeat/start; fall back to now for undated seed jobs.
    job = max(failed, key=lambda j: j.heartbeat_at or j.started_at or utcnow())
    return job_failure_ref(job)


def _piece_item(
    piece: Piece,
    collections: WorkStateCollections,
) -> QueueItem:
    pid = piece.id
    interviews = [i for i in collections.interviews if i.piece_id == pid]
    open_interviews = [
        OpenInterviewRef(interview_id=i.id or "", expert=i.assigned_expert)
        for i in interviews
        if i.status == InterviewStatus.open.value and i.id
    ]
    has_complete = any(i.status == InterviewStatus.complete.value for i in interviews)
    jobs = [j for j in collections.jobs if j.piece_id == pid]
    councils = [c for c in collections.councils if c.piece_id == pid]
    rounds = [r for r in collections.review_rounds if r.piece_id == pid]
    lessons_proposed = sum(
        1
        for lesson in collections.lessons
        if lesson.source_piece_id == pid and lesson.status == LessonStatus.proposed.value
    )
    return QueueItem(
        kind="piece",
        id=pid or "",
        title=piece.title or piece.slug,
        voice=piece.voice,
        stage=piece.stage,
        owner=piece.owner,
        assigned_experts=list(piece.assigned_experts),
        council_aggregate=_latest_council_aggregate(councils),
        open_gaps=piece.open_gaps,
        open_clearances=piece.open_clearances,

        review_round=_latest_round_number(rounds),
        open_interviews=open_interviews,
        has_complete_interview=has_complete,
        failed_job=_failed_job(jobs),
        lessons_proposed=lessons_proposed,
        updated_at=piece.updated_at,
        last_human_touch_at=piece.last_human_touch_at,
        brain_synced=piece.brain_synced,
    )


def _spike_item(spike: Spike) -> QueueItem:
    return QueueItem(
        kind="spike",
        id=spike.id or "",
        title=spike.headline,
        voice=None,
        spike_status=spike.status,
        creator=spike.creator,
        spike_assigned=spike.piece_id is not None,
        updated_at=spike.updated_at,
    )


def build_queue(collections: WorkStateCollections) -> list[QueueItem]:
    """Assemble the full shared queue: one card per Piece plus one per pooled Spike.

    Spikes already promoted into a Piece (``piece_id`` set) are represented by the Piece card, so
    only pool spikes (``proposed`` / ``picked`` / ``vaulted``) surface as spike cards here.

    An archived piece (``Piece.archived_at`` set — triage at scale, orthogonal to the stage
    machine) is excluded entirely, at this single choke point, so every downstream consumer (tab
    membership, per-tab counts, the "needs my action" predicate, the D15 filter bar) sees a queue
    that already never contained it — never a client-side filter that each of those would
    otherwise have to remember to apply. It stays fully intact and reachable at its own
    ``/api/pieces/{id}`` URL either way (§ visibility-only, never a permission/data change).
    """
    items = [_piece_item(p, collections) for p in collections.pieces if p.archived_at is None]
    items += [_spike_item(s) for s in collections.spikes]
    return items


# --- Seed --------------------------------------------------------------------------------------
#
# Placeholder-but-real work-state entities used until upstream orchestration writes to Mongo. The
# entities attributed to ``viewer`` cover every branch of the Item-3 predicate so the signed-in
# user's "Needs my action" tab is populated end-to-end; teammate-attributed entities give the "All
# in flight" / "My pieces" / "Spikes & Vault" tabs realistic contrast (and prove the predicate
# EXCLUDES work that isn't the viewer's, without ever hiding it from All in flight).

_TEAMMATE_A = "alex@example.com"
_TEAMMATE_B = "jordan@example.com"


def _spike_slug(headline: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", headline.lower()).strip("-")


def seed_work_state(viewer: str | None = None) -> WorkStateCollections:
    """Build the seed collections, attributing the "needs my action" cards to ``viewer``."""
    you = viewer or "you@company"
    now = utcnow()

    def piece(**kwargs) -> Piece:
        # Deterministic, slug-derived id (not `new_id()`): the seed is regenerated fresh on every
        # call (no Mongo backing it), so a piece-detail fetch for the id a dashboard card just
        # linked to must resolve against a *later, independent* seed call. A random id would only
        # ever match the collections instance that minted it.
        kwargs.setdefault("id", f"seed-{kwargs['slug']}")
        kwargs.setdefault("updated_at", now)
        return Piece(**kwargs)

    # 1 · review + owner=you  → predicate branch: owner of a piece in `review`.
    board = piece(
        slug="the-board-on-the-wall",
        title="The board on the wall",
        voice="demo-mira",
        stage=PieceStage.review,
        owner=you,
        open_gaps=2,

    )
    # 2 · interviewing + assigned expert=you  → branch: assigned expert on an open interview.
    rollback = piece(
        slug="rehearse-the-rollback",
        title="Rehearse the rollback",
        voice="demo-dana",
        stage=PieceStage.interviewing,
        owner=_TEAMMATE_A,
        assigned_experts=[you],

    )
    # 3 · interviewing + owner=you + an interview marked complete → branch: decide "enough input".
    latency = piece(
        slug="faq-latency",
        title="Latency budget FAQ",
        voice="demo-mira",
        stage=PieceStage.interviewing,
        owner=you,

    )
    # 4 · a failed draft job you triggered → branch: triggerer of a failed/stuck job. The piece
    #     stayed at its last stable stage (interviewing) — flag, don't roll back (Item 4).
    pricing = piece(
        slug="pricing-explainer",
        title="Pricing, explained: what you actually pay for",
        voice="demo-dana",
        stage=PieceStage.interviewing,
        owner=you,

    )
    # 5 · finalized + owner=you + unreviewed lessons → branch: finalized owner w/ lessons (D12).
    agentcore = piece(
        slug="agentcore-faq",
        title="AgentCore technical FAQ",
        voice="team",
        stage=PieceStage.finalized,
        owner=you,

    )
    # 6 · published + owner=you  → NOT in-flight, NOT needs-my-action: the terminal state a
    #     published piece reaches (Hendo's dashboard fix — this must never appear as in-flight).
    launch_recap = piece(
        slug="q3-launch-recap",
        title="Q3 launch recap",
        voice="team",
        stage=PieceStage.released,
        owner=you,

        published_release=1,
        published_html_url="https://example-published-assets.s3.us-east-1.amazonaws.com/published/q3-launch-recap/1/branded.html",
        published_pdf_url="https://example-published-assets.s3.us-east-1.amazonaws.com/published/q3-launch-recap/1/branded.pdf",
        published_doc=DocRef(
            doc_id="seed-published-doc",
            url="https://docs.google.com/document/d/seed-published-doc/edit",
            share_mode=ShareMode.external,
        ),
        published_at=now,
    )
    # 7 & 8 · teammate-owned pieces — NOT needs-my-action, but always visible in All in flight.
    vpc = piece(
        slug="vpc-egress-guide",
        title="VPC egress guide",
        voice="demo-mira",
        stage=PieceStage.review,
        owner=_TEAMMATE_A,
        open_gaps=1,

    )
    onboarding = piece(
        slug="onboarding-narrative",
        title="Onboarding narrative",
        voice="team",
        stage=PieceStage.drafting,
        owner=_TEAMMATE_B,

    )

    pieces = [board, rollback, latency, pricing, agentcore, launch_recap, vpc, onboarding]

    interviews = [
        # The open interview that puts `rollback` on your plate (assigned to you).
        Interview(
            id=new_id(),
            piece_id=rollback.id,
            assigned_expert=you,
            interviewer_personas=["tactician", "architect"],
            status=InterviewStatus.open,
            about="Rehearse the rollback",
            updated_at=now,
        ),
        # A second open interview on the same piece, assigned to a teammate (not yours).
        Interview(
            id=new_id(),
            piece_id=rollback.id,
            assigned_expert=_TEAMMATE_B,
            interviewer_personas=["operator"],
            status=InterviewStatus.open,
            about="Rollback drill cost angle",
            updated_at=now,
        ),
        # A COMPLETE interview on `latency` → you (the owner) decide "enough input".
        Interview(
            id=new_id(),
            piece_id=latency.id,
            assigned_expert=_TEAMMATE_B,
            interviewer_personas=["skeptic"],
            status=InterviewStatus.complete,
            about="Latency budget",
            updated_at=now,
        ),
    ]

    jobs = [
        # The sanctioned hard block (per-run cost ceiling, D14) stopped this draft; it FLAGGED
        # the piece and left it recoverable — the one place a block is correct (Item 4).
        Job(
            id=new_id(),
            piece_id=pricing.id,
            type=JobType.draft,
            status=JobStatus.failed,
            attempts=1,
            started_at=now,
            heartbeat_at=now,
            error=JobError(
                code="ceiling-exceeded",
                message="per-run cost ceiling reached before the draft completed",
                retryable=False,
            ),
            cost=0.12,
            triggered_by=you,
        ),
    ]

    councils = [
        # the-board-on-the-wall cleared the bar on round 2 — mandatory editors always present (§1.13).
        Council(
            id=new_id(),
            piece_id=board.id,
            revision="rev-7",
            round_number=2,
            editor_scores=[
                EditorScore(editor="slop-allergist", score=9.0),
                EditorScore(editor="voice-guardian", score=9.4),
            ],
            aggregate=9.2,
            cost=0.19,
        ),
    ]

    review_rounds = [
        ReviewRound(
            id=new_id(),
            piece_id=board.id,
            round_number=2,
            minted_from_revision="rev-7",
            opened_at=now,
            updated_at=now,
        ),
    ]

    lessons = [
        Lesson(
            id=new_id(),
            voice="team",
            source_piece_id=agentcore.id,
            observed_change=f"editor tightened claim #{n}",
            generalizable_rule=f"prefer concrete figures over hedged ranges (#{n})",
            status=LessonStatus.proposed,
        )
        for n in range(1, 6)  # 5 proposed, unreviewed
    ]

    def spike(*, headline: str, **kwargs) -> Spike:
        # Deterministic, headline-slug-derived id (not `new_id()`) — same reasoning as `piece()`
        # above: the Spikes & Vault browser and the spike-kickoff screen fetch a spike by id on a
        # LATER, independent request, which must resolve against a fresh `seed_work_state()` call.
        kwargs.setdefault("id", f"seed-spike-{_spike_slug(headline)}")
        kwargs.setdefault("updated_at", now)
        return Spike(headline=headline, **kwargs)

    spikes = [
        # Picked by you, not yet assigned → coordinator branch of the predicate (use case C).
        spike(
            headline="You're auditing the wrong line item",
            status=SpikeStatus.picked,
            convergence_score=0.71,
            creator=you,
            origin=SpikeOrigin(kind=SpikeOriginKind.oracle_run, ref="seed-run-1"),
        ),
        # Pool spikes for the Spikes & Vault tab (teammate + your own proposals, and a tangent).
        spike(
            headline="The GSI you added is quietly doubling your bill",
            status=SpikeStatus.proposed,
            convergence_score=0.64,
            creator=_TEAMMATE_A,
            origin=SpikeOrigin(kind=SpikeOriginKind.oracle_run, ref="seed-run-1"),
        ),
        spike(
            headline="Why 'serverless' still has a cold-start tax",
            status=SpikeStatus.proposed,
            convergence_score=0.52,
            creator=you,
            origin=SpikeOrigin(kind=SpikeOriginKind.narrative, ref="seed-narrative-1"),
        ),
        spike(
            headline="A tangent worth parking: multi-region write costs",
            status=SpikeStatus.vaulted,
            creator=_TEAMMATE_B,
            origin=SpikeOrigin(kind=SpikeOriginKind.tangent),
        ),
    ]

    return WorkStateCollections(
        pieces=pieces,
        spikes=spikes,
        interviews=interviews,
        jobs=jobs,
        lessons=lessons,
        councils=councils,
        review_rounds=review_rounds,
    )
