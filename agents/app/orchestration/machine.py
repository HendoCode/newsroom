"""The deterministic per-piece state machine (D5; open-decisions Item 2; domain model §1.9).

The settled 9-state machine, hosted here as the orchestration core the FastAPI service exposes. It
reads/writes a piece's ``stage`` through the data-layer :class:`~app.repositories.PieceRepository`
(which already rejects illegal edges against the settled ``ALLOWED_TRANSITIONS`` table — this
module never re-implements that table) and drives batch stages through the
:class:`~app.orchestration.jobs.JobRunner`.

Responsibilities, and only these:

- **The three human triggers** (the only manual advances, D16a/D4/use-case-J):
  :meth:`enough_input` (interviewing→drafting), :meth:`reviews_done` (review→incorporating),
  :meth:`finalize` (review→finalizing). Plus the lessons gate (:meth:`capture_lessons` /
  :meth:`finish_lessons`), the info-gap re-interview edge (:meth:`route_to_interview`), and the
  D6 pause/resume meta-command.
- **Batch chaining.** Entering a batch stage dispatches its job; on success the piece auto-advances
  (drafting→council→review; incorporating→council→review; finalizing→finalized) and any newly-
  entered batch stage runs next, until the chain reaches an interactive stage. One shared
  :class:`~app.llm.budget.RunBudget` bounds the whole triggered run (the per-run ceiling, D14).
- **Flag, don't roll back** (Item 4). A failed/stuck job leaves the piece in its **last stable
  stage** with the failed :class:`~app.models.Job` as the flag — never a dead-end, never a rolled-
  back revision (D4/D16b). See :func:`_failure_stage` for the per-step target.

Illegal transitions are rejected two ways: a human trigger fired from the wrong stage raises
:class:`IllegalTrigger`, and the underlying stage write is guarded by the repository's
``can_transition`` check.

**Staleness triage** (cmw-staleness-timestamps): every one of the 10 human-facing methods below
(the three batch triggers via :meth:`_trigger`, :meth:`retry_finalize`, plus
:meth:`capture_lessons`/:meth:`finish_lessons`/:meth:`publish`/:meth:`resume` via :meth:`_advance`,
plus :meth:`route_to_interview`/:meth:`pause` directly) stamps ``Piece.last_human_touch_at`` on
success — these are, by this module's own design
(see the docstrings: "HUMAN ..."), exactly the set of calls a person makes, regardless of whether
``actor`` identifies who. Deliberately NOT stamped by :meth:`_run_batch_chain` or
:meth:`sweep_stuck`: a batch job succeeding or a stuck-job sweep flipping a stage are both
machine-driven, and stamping them would make the field lie about a human having looked at the
piece. :meth:`_set_stage` itself is shared by both human and machine callers, so it cannot stamp —
each human-only call site does it explicitly instead.
"""

from __future__ import annotations

from collections.abc import Callable

from app.llm.budget import RunBudget
from app.models import Job, JobStatus, JobType, Piece, PieceStage, can_transition, is_released_stage, utcnow
from app.orchestration.jobs import JobNotClaimable, JobRunner
from app.orchestration.steps import StepNotRegistered
from app.repositories import WorkStateStore

# A batch stage → the job type its entry dispatches.
_BATCH_STAGE_JOB: dict[PieceStage, JobType] = {
    PieceStage.drafting: JobType.draft,
    PieceStage.council: JobType.council,
    PieceStage.incorporating: JobType.incorporate,
    PieceStage.finalizing: JobType.finalize,
}

# On job success, the stage the piece advances to (the settled auto edges, §1.9). Landing on a
# batch stage chains into the next job; landing on an interactive stage ends the run.
_ON_SUCCESS: dict[JobType, PieceStage] = {
    JobType.draft: PieceStage.council,
    JobType.council: PieceStage.review,
    JobType.incorporate: PieceStage.council,
    JobType.finalize: PieceStage.finalized,
}

# Interactive stages a batch chain stops at (they wait on a human, or are terminal for the run).
_INTERACTIVE_STAGES = frozenset(
    {
        PieceStage.interviewing,
        PieceStage.review,
        PieceStage.finalized,
        PieceStage.lessons,
        PieceStage.paused,
        PieceStage.released,
    }
)


class IllegalTrigger(ValueError):
    """A human trigger (or gate move) fired from a stage where it is not legal."""


def _failure_stage(job_type: JobType, piece: Piece) -> PieceStage | None:
    """The last stable stage a failed batch job rolls the piece back to (flag, don't roll back).

    Uses only edges present in the settled ``ALLOWED_TRANSITIONS`` table:

    - **draft** → ``interviewing`` (the "batch fail" edge drawn in §1.9).
    - **council** → ``review`` for a re-council (a review round already exists), else
      ``interviewing`` for the first pass — both legal backward edges.
    - **incorporate** → ``review`` (the round is unchanged; the Doc stays authoritative).
    - **finalize** → ``None``: the settled graph gives ``finalizing`` only the ``→ finalized`` edge,
      so a finalize failure is not rolled back. The piece stays flagged in ``finalizing`` and the
      run is retried in place — never wedged (a retry can always advance it), and the table is
      honored exactly (no synthetic edge added).
    """
    job_type = JobType(job_type)
    if job_type == JobType.draft:
        return PieceStage.interviewing
    if job_type == JobType.council:
        return PieceStage.review if piece.current_review_round_id else PieceStage.interviewing
    if job_type == JobType.incorporate:
        return PieceStage.review
    return None  # finalize (and oracle, which is pieceless and never reaches here)


class PieceMachine:
    """Drives a piece through the settled 9-state machine. Composes a :class:`JobRunner` for the
    batch stages; owns every stage transition."""

    def __init__(
        self,
        store: WorkStateStore,
        runner: JobRunner,
        *,
        budget_factory: Callable[[], RunBudget] | None = None,
    ) -> None:
        self.store = store
        self.runner = runner
        # Each triggered run gets a fresh per-run ceiling. Default is unbounded; production wires a
        # real cost/token ceiling here — the one sanctioned hard block (D14).
        self._budget_factory = budget_factory or RunBudget

    # --- the three human triggers ---------------------------------------------------------

    async def enough_input(self, piece_id: str, *, actor: str | None = None) -> Piece:
        """HUMAN "enough input" (D16a): interviewing → drafting, then run the draft chain.

        An interview being marked complete is only a *signal*; this authority-driven trigger is the
        one that advances to drafting. Rejected from any stage other than ``interviewing``.

        Drafting with no accepted transcript turns is an impossible operation (not a flexibility
        warning): the draft step has no source material and will fail the same way every time.
        When the Git content store is wired on the runner, refuse here — before a job is
        enqueued. Tests that construct a runner without ``content=`` skip the check.
        """
        piece = await self._get(piece_id)
        accepted = self._accepted_turn_count(piece)
        if accepted == 0:
            raise IllegalTrigger(
                f"piece {piece.slug!r} has no accepted interview turns — Enough input "
                "would fail the same way every time. Record at least one answer first."
            )
        return await self._trigger(piece_id, PieceStage.interviewing, PieceStage.drafting, actor)

    async def reviews_done(self, piece_id: str, *, actor: str | None = None) -> Piece:
        """HUMAN "reviews done" (D4): review → incorporating, then re-council back to review."""
        return await self._trigger(piece_id, PieceStage.review, PieceStage.incorporating, actor)

    async def finalize(
        self, piece_id: str, *, actor: str | None = None, formats: list[str] | None = None
    ) -> Piece:
        """HUMAN "finalize" (use case J): review → finalizing → finalized.

        ``formats`` narrows the finalize run to a subset of branded HTML/PDF/clean Doc (use case J
        "outputs are selectable at finalize"); ``None`` takes the step's own default (all three).
        """
        return await self._trigger(
            piece_id, PieceStage.review, PieceStage.finalizing, actor, formats=formats
        )

    async def retry_finalize(self, piece_id: str, *, actor: str | None = None) -> Piece:
        """HUMAN retry/reclaim for a finalize job while its Piece remains ``finalizing``.

        Failed/stuck work is atomically reclaimed into one bounded execution. Queued/running work
        is never duplicated, and a succeeded job is reconciled by advancing the still-wedged Piece
        without replaying its external effects.
        """
        piece = await self._get(piece_id)
        if PieceStage(piece.stage) != PieceStage.finalizing:
            raise IllegalTrigger(
                "retry_finalize requires stage finalizing, "
                f"piece is {PieceStage(piece.stage).value}"
            )
        if not self.runner.registry.has(JobType.finalize):
            raise StepNotRegistered("no batch step registered for finalize")

        jobs = await self.store.jobs.by_piece_and_type(piece_id, JobType.finalize)
        if not jobs:
            raise IllegalTrigger("piece has no finalize job to retry")

        active = [
            job
            for job in jobs
            if JobStatus(job.status) in (JobStatus.queued, JobStatus.running)
        ]
        if len(active) > 1:
            raise IllegalTrigger("piece has multiple active finalize jobs; refusing duplicate work")
        if active:
            raise IllegalTrigger(
                f"a finalize job is already {JobStatus(active[0].status).value}"
            )

        job = jobs[0]
        status = JobStatus(job.status)
        if status == JobStatus.succeeded:
            piece = await self._set_stage(
                piece_id, PieceStage.finalized, expected=PieceStage.finalizing
            )
            return await self.store.pieces.mark_human_touch(piece.id)
        if status not in (JobStatus.failed, JobStatus.stuck):
            raise IllegalTrigger(f"finalize job cannot be retried from {status.value}")

        try:
            job = await self.runner.retry(job.id, budget=self._budget_factory())
        except JobNotClaimable as exc:
            raise IllegalTrigger(str(exc)) from exc
        piece = await self.store.pieces.mark_human_touch(piece_id)
        if JobStatus(job.status) == JobStatus.succeeded:
            piece = await self._set_stage(
                piece.id, PieceStage.finalized, expected=PieceStage.finalizing
            )
        return piece

    # --- interactive gates / edges (no batch job) -----------------------------------------

    async def capture_lessons(self, piece_id: str, *, actor: str | None = None) -> Piece:
        """HUMAN "capture lessons" (use case H): finalized → lessons. The lessons *proposal* step
        is a downstream ticket (and is not a :class:`~app.models.JobType`), so this only opens the
        gate; :meth:`finish_lessons` closes it after the human accepts/edits/rejects (D12)."""
        return await self._advance(piece_id, PieceStage.finalized, PieceStage.lessons)

    async def finish_lessons(self, piece_id: str, *, actor: str | None = None) -> Piece:
        """Close the D12 lessons gate: lessons → finalized (accept/edit/reject done)."""
        return await self._advance(piece_id, PieceStage.lessons, PieceStage.finalized)

    async def publish(self, piece_id: str, *, actor: str | None = None) -> Piece:
        """HUMAN AuthorizeRelease stage gate: finalized → released on the first authorization;
        already-released pieces stay released (repeatable numbered Publication Releases are not a
        stage transition). Only a stage-validity gate — :class:`~app.publish.service.PublishService`
        does the actual render/upload/share work and calls this only after every one of those
        external side effects has already succeeded."""
        piece = await self._get(piece_id)
        if is_released_stage(piece.stage):
            return await self.store.pieces.mark_human_touch(piece_id)
        return await self._advance(piece_id, PieceStage.finalized, PieceStage.released)

    async def route_to_interview(self, piece_id: str, *, actor: str | None = None) -> Piece:
        """Route an information gap back to a targeted interview (D16a): council → interviewing or
        review → interviewing. Legal only from those two stages."""
        piece = await self._get(piece_id)
        stage = PieceStage(piece.stage)
        if stage not in (PieceStage.council, PieceStage.review):
            raise IllegalTrigger(
                f"route_to_interview is only legal from council/review, not {stage.value}"
            )
        await self._set_stage(piece_id, PieceStage.interviewing, expected=stage)
        return await self.store.pieces.mark_human_touch(piece_id)

    async def pause(self, piece_id: str, *, actor: str | None = None) -> Piece:
        """D6 "stop for the day": interviewing/review → paused (resumable)."""
        piece = await self._get(piece_id)
        stage = PieceStage(piece.stage)
        if stage not in (PieceStage.interviewing, PieceStage.review):
            raise IllegalTrigger(f"pause is only legal from interviewing/review, not {stage.value}")
        await self._set_stage(piece_id, PieceStage.paused, expected=stage)
        return await self.store.pieces.mark_human_touch(piece_id)

    async def resume(self, piece_id: str, *, actor: str | None = None) -> Piece:
        """Resume a paused piece: paused → interviewing."""
        return await self._advance(piece_id, PieceStage.paused, PieceStage.interviewing)

    async def open_failures(self, piece_id: str) -> list[Job]:
        """The failed/stuck jobs currently flagging a piece (powers the "needs my action" ⚠)."""
        jobs = await self.store.jobs.by_piece(piece_id)
        return [j for j in jobs if JobStatus(j.status) in (JobStatus.failed, JobStatus.stuck)]

    async def sweep_stuck(self, *, timeout_seconds: float) -> list[Piece]:
        """Detect crashed-worker jobs and flag their pieces (Item 4 stuck detection).

        Flips stale ``running`` jobs to ``stuck`` (via the runner) and rolls each affected piece
        back to its last stable stage — the same flag-don't-roll-back treatment a synchronous
        failure gets, applied to jobs whose worker died mid-run. Returns the affected pieces.
        """
        stuck_jobs = await self.runner.sweep_stuck(timeout_seconds=timeout_seconds)
        affected: list[Piece] = []
        for job in stuck_jobs:
            if job.piece_id is None:
                continue
            piece = await self.store.pieces.get(job.piece_id)
            if piece is None:
                continue
            target = _failure_stage(JobType(job.type), piece)
            if target is not None and PieceStage(piece.stage) != target:
                piece = await self._set_stage(
                    piece.id, target, expected=PieceStage(piece.stage)
                )
            affected.append(piece)
        return affected

    # --- internals ------------------------------------------------------------------------

    async def _trigger(
        self,
        piece_id: str,
        expected: PieceStage,
        batch_stage: PieceStage,
        actor: str | None,
        *,
        formats: list[str] | None = None,
    ) -> Piece:
        """A human trigger that enters a batch stage: assert the current stage, move into the batch
        stage, then run the batch chain under one shared per-run budget."""
        piece = await self._get(piece_id)
        if PieceStage(piece.stage) != expected:
            raise IllegalTrigger(
                f"trigger requires stage {expected.value}, piece is {PieceStage(piece.stage).value}"
            )
        # Fail before moving the piece if this batch's step isn't registered yet (a downstream
        # ticket): otherwise the piece would land in a batch stage no worker can service — a wedge.
        job_type = _BATCH_STAGE_JOB[batch_stage]
        if not self.runner.registry.has(job_type):
            raise StepNotRegistered(
                f"no batch step registered for {job_type.value} — cannot enter {batch_stage.value}"
            )
        piece = await self._set_stage(piece_id, batch_stage, expected=expected)
        piece = await self.store.pieces.mark_human_touch(piece_id)
        return await self._run_batch_chain(piece, actor, formats=formats)

    async def _run_batch_chain(
        self, piece: Piece, actor: str | None, *, formats: list[str] | None = None
    ) -> Piece:
        """Run consecutive batch jobs, auto-advancing on success until an interactive stage or a
        failure. Failure flags the piece (leaves it in / rolls it back to its last stable stage).
        ``formats`` only ever applies to the (at most one) ``finalize`` job in the chain — the other
        job types ignore it (:class:`~app.models.Job` documents it as finalize-only).

        A newly-entered batch stage whose step isn't registered yet (a downstream ticket, mid
        rollout) stops the chain in place rather than enqueueing a job nothing can service — the
        piece already legitimately advanced to ``stage`` on the prior job's success, so it stays
        there, unflagged, exactly like reaching a genuine interactive stage. ``_trigger``'s own
        pre-check only covers the *first* stage a human trigger enters; without this, a later
        unregistered stage would raise ``StepNotRegistered`` out of ``self.runner.run`` after the
        prior job's success (and its Git/Mongo side effects) were already committed, wedging the
        piece with an orphaned ``queued`` job while the HTTP caller sees only a 501 that looks like
        nothing happened."""
        budget = self._budget_factory()
        stage = PieceStage(piece.stage)
        while stage in _BATCH_STAGE_JOB:
            job_type = _BATCH_STAGE_JOB[stage]
            if not self.runner.registry.has(job_type):
                break
            job_formats = formats if job_type == JobType.finalize else None
            job = await self.runner.enqueue(
                job_type, piece_id=piece.id, triggered_by=actor, formats=job_formats
            )
            job = await self.runner.run(job.id, budget=budget)
            if JobStatus(job.status) == JobStatus.succeeded:
                piece = await self._set_stage(
                    piece.id, _ON_SUCCESS[JobType(job.type)], expected=stage
                )
                stage = PieceStage(piece.stage)
                if stage in _INTERACTIVE_STAGES:
                    break
            else:
                target = _failure_stage(JobType(job.type), piece)
                if target is not None and PieceStage(piece.stage) != target:
                    piece = await self._set_stage(
                        piece.id, target, expected=PieceStage(piece.stage)
                    )
                break  # stop chaining on failure — the piece is flagged, recoverable via retry
        return piece

    async def _advance(self, piece_id: str, expected: PieceStage, dst: PieceStage) -> Piece:
        """An interactive→interactive move with a required source stage (rejects otherwise).

        Only ever called from the human gates (:meth:`capture_lessons`/:meth:`finish_lessons`/
        :meth:`publish`/:meth:`resume`) — never from a machine-driven path — so it stamps
        ``last_human_touch_at`` unconditionally; see the module docstring's staleness-triage note.
        """
        piece = await self._get(piece_id)
        if PieceStage(piece.stage) != expected:
            raise IllegalTrigger(
                f"move requires stage {expected.value}, piece is {PieceStage(piece.stage).value}"
            )
        piece = await self._set_stage(piece_id, dst, expected=expected)
        return await self.store.pieces.mark_human_touch(piece_id)

    async def _set_stage(
        self, piece_id: str, dst: PieceStage, *, expected: PieceStage | None = None
    ) -> Piece:
        """Persist a stage change through the repository (which enforces ``can_transition``).

        We pre-check ``can_transition`` to raise a clear :class:`IllegalTrigger` for an internal
        bug; the repository is the authoritative guard against an illegal edge reaching Mongo.
        """
        if expected is None:
            piece = await self._get(piece_id)
            src = PieceStage(piece.stage)
        else:
            src = PieceStage(expected)
        if src != dst and not can_transition(src, dst):
            raise IllegalTrigger(f"illegal transition {src.value} → {dst.value} (§1.9)")
        try:
            piece = await self.store.pieces.transition(piece_id, dst, expected=src)
        except ValueError as exc:
            raise IllegalTrigger(str(exc)) from exc
        if dst == PieceStage.finalized and piece.latest_revision:
            stamped = await self.store.pieces.update(
                piece_id,
                {"approved_revision": piece.latest_revision, "approved_at": utcnow()},
            )
            if stamped is not None:
                return stamped
        return piece

    async def _get(self, piece_id: str) -> Piece:
        piece = await self.store.pieces.get(piece_id)
        if piece is None:
            raise KeyError(f"no piece {piece_id!r}")
        return piece

    def _accepted_turn_count(self, piece: Piece) -> int | None:
        """Accepted (non-empty answer) turns in the sacred transcript, or ``None`` when the
        runner has no Git content store to read. ``0`` is the impossible-operation signal."""
        content = getattr(self.runner, "content", None)
        if content is None or not hasattr(content, "read_piece_files"):
            return None
        from app.interview.transcript import parse_turns, read_transcript

        raw = read_transcript(content, piece.slug)
        return sum(1 for turn in parse_turns(raw) if turn.answer.strip())
