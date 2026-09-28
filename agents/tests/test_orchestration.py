"""Orchestration core tests (D5; open-decisions Item 2 & 4; domain model §1.9/§1.16).

Covers, per the acceptance criteria:
- the settled 9-state machine: legal vs illegal transitions, and the three human triggers;
- the batch chain running end-to-end through the stub (dispatch → run → status flip → advance);
- job success / failure / stuck status flips;
- retry classification against the Anthropic error taxonomy (transient vs deterministic);
- the per-run cost ceiling as the single hard block;
- the flag-not-rollback invariant (a failed job flags the piece, never rolls back committed work).

Zero external deps: the work-state store is the in-memory ``store`` fixture; the LLM path runs on a
tiny fake provider that satisfies the seam (no ``anthropic`` package, no key, no network).
"""

from __future__ import annotations

import asyncio

import pytest

from app.llm.budget import RunBudget, RunBudgetExceeded
from app.llm.pricing import Usage, cost_usd
from app.llm.provider import LLMProvider, LLMResult
from app.models import Job, JobStatus, JobType, Piece, PieceStage
from app.orchestration import (
    BatchStep,
    IllegalTrigger,
    JobNotClaimable,
    JobRunner,
    PieceMachine,
    RefusalError,
    StepContext,
    StepResult,
    StubStep,
    build_stub_registry,
    classify_exception,
)
from app.repositories import WorkStateStore

# --- test doubles --------------------------------------------------------------------------


async def _noop_sleep(_seconds: float) -> None:
    """Injected into the runner so bounded retries don't really wait."""


class FakeAPIError(Exception):
    """Stand-in for an ``anthropic`` APIStatusError — carries an HTTP ``status_code``."""

    def __init__(self, status_code: int, message: str = "") -> None:
        super().__init__(message or f"HTTP {status_code}")
        self.status_code = status_code


class FakeConnectionError(Exception):
    """Stand-in for a network error (class name drives the network classification)."""


class FakeProvider(LLMProvider):
    """Minimal swappable provider: honors the budget exactly as a real one would (pre-flight
    ``check`` then ``charge``) so ceiling enforcement and ``usage`` capture flow through the seam."""

    def __init__(self, usage: Usage | None = None) -> None:
        self.usage = usage or Usage(input_tokens=100, output_tokens=50)
        self.calls = 0

    async def complete(self, *, step, model, system, messages, max_tokens, effort=None, cache=False, budget=None):
        if budget is not None:
            budget.check()
        self.calls += 1
        if budget is not None:
            budget.charge(model, self.usage)
        return LLMResult(
            text="ok",
            model=model,
            stop_reason="end_turn",
            usage=self.usage,
            cost_usd=cost_usd(model, self.usage),
        )

    def stream(self, *, step, model, system, messages, max_tokens, effort=None, budget=None):
        raise NotImplementedError("stub steps use complete()")

    async def count_tokens(self, *, model, system, messages):
        return 0


class FlakyStep(BatchStep):
    """A step that raises a queued list of errors on successive attempts, then succeeds. Lets the
    tests drive the retry policy deterministically."""

    def __init__(self, job_type: JobType, errors: list[Exception]) -> None:
        self.job_type = JobType(job_type)
        self._errors = list(errors)
        self.attempts = 0

    async def run(self, ctx: StepContext) -> StepResult:
        self.attempts += 1
        if self._errors:
            raise self._errors.pop(0)
        return StepResult(notes=["flaky ok"])


def _machine(
    store: WorkStateStore,
    *,
    registry=None,
    provider: LLMProvider | None = None,
    budget_factory=None,
    max_attempts: int = 2,
) -> PieceMachine:
    registry = registry if registry is not None else build_stub_registry()
    runner = JobRunner(
        store, registry, provider=provider, max_attempts=max_attempts, sleep=_noop_sleep
    )
    return PieceMachine(store, runner, budget_factory=budget_factory)


async def _piece(store: WorkStateStore, stage: PieceStage, **extra) -> Piece:
    piece = Piece(slug=extra.pop("slug", "the-board-on-the-wall"), voice="demo-mira", stage=stage, **extra)
    return await store.pieces.insert(piece)


# --- the three human triggers + batch chaining (dispatch → run → flip → advance) -----------


@pytest.mark.asyncio
async def test_enough_input_runs_draft_chain_to_review(store: WorkStateStore) -> None:
    machine = _machine(store)
    piece = await _piece(store, PieceStage.interviewing)

    piece = await machine.enough_input(piece.id, actor="demo-mira@x")

    # interviewing → drafting → (draft ok) council → (council ok) review, and stops at review.
    assert piece.stage == PieceStage.review
    jobs = await store.jobs.by_piece(piece.id)
    assert {JobType(j.type) for j in jobs} == {JobType.draft, JobType.council}
    assert all(JobStatus(j.status) == JobStatus.succeeded for j in jobs)


@pytest.mark.asyncio
async def test_reviews_done_re_councils_back_to_review(store: WorkStateStore) -> None:
    machine = _machine(store)
    piece = await _piece(store, PieceStage.review, current_review_round_id="round-1")

    piece = await machine.reviews_done(piece.id, actor="demo-mira@x")

    # review → incorporating → (ok) council → (ok) review.
    assert piece.stage == PieceStage.review
    jobs = await store.jobs.by_piece(piece.id)
    assert {JobType(j.type) for j in jobs} == {JobType.incorporate, JobType.council}


@pytest.mark.asyncio
async def test_finalize_advances_to_finalized(store: WorkStateStore) -> None:
    machine = _machine(store)
    piece = await _piece(store, PieceStage.review)

    piece = await machine.finalize(piece.id, actor="demo-mira@x")

    assert piece.stage == PieceStage.finalized
    jobs = await store.jobs.by_piece(piece.id)
    assert [JobType(j.type) for j in jobs] == [JobType.finalize]
    assert JobStatus(jobs[0].status) == JobStatus.succeeded


@pytest.mark.asyncio
async def test_finalize_formats_pass_through_to_the_job(store: WorkStateStore) -> None:
    """Use case J "outputs are selectable at finalize" — `formats` reaches the persisted Job
    (`Job.formats`), which the finalize step reads (`ctx.job.formats`); this only covers the
    trigger→enqueue wiring, not the step's own rendering."""
    machine = _machine(store)
    piece = await _piece(store, PieceStage.review)

    piece = await machine.finalize(piece.id, actor="demo-mira@x", formats=["html", "pdf"])

    assert piece.stage == PieceStage.finalized
    [job] = await store.jobs.by_piece(piece.id)
    assert job.formats == ["html", "pdf"]


@pytest.mark.asyncio
async def test_finalize_without_formats_leaves_job_formats_unset(store: WorkStateStore) -> None:
    machine = _machine(store)
    piece = await _piece(store, PieceStage.review)

    piece = await machine.finalize(piece.id, actor="demo-mira@x")

    [job] = await store.jobs.by_piece(piece.id)
    assert job.formats is None


@pytest.mark.asyncio
async def test_human_triggers_rejected_from_wrong_stage(store: WorkStateStore) -> None:
    machine = _machine(store)
    interviewing = await _piece(store, PieceStage.interviewing, slug="a")
    review = await _piece(store, PieceStage.review, slug="b")

    with pytest.raises(IllegalTrigger):
        await machine.finalize(interviewing.id)  # finalize only from review
    with pytest.raises(IllegalTrigger):
        await machine.reviews_done(interviewing.id)  # reviews-done only from review
    with pytest.raises(IllegalTrigger):
        await machine.enough_input(review.id)  # enough-input only from interviewing

    # nothing moved, nothing dispatched.
    assert (await store.pieces.get(interviewing.id)).stage == PieceStage.interviewing
    assert await store.jobs.by_piece(interviewing.id) == []


# --- interactive gates / edges -------------------------------------------------------------


@pytest.mark.asyncio
async def test_lessons_gate_open_and_close(store: WorkStateStore) -> None:
    machine = _machine(store)
    piece = await _piece(store, PieceStage.finalized)

    piece = await machine.capture_lessons(piece.id)
    assert piece.stage == PieceStage.lessons
    piece = await machine.finish_lessons(piece.id)
    assert piece.stage == PieceStage.finalized
    # lessons is a batch+gate but NOT a JobType — the proposal step is downstream; no job dispatched.
    assert await store.jobs.by_piece(piece.id) == []


@pytest.mark.asyncio
async def test_pause_resume(store: WorkStateStore) -> None:
    machine = _machine(store)
    piece = await _piece(store, PieceStage.review)

    piece = await machine.pause(piece.id)
    assert piece.stage == PieceStage.paused
    piece = await machine.resume(piece.id)
    assert piece.stage == PieceStage.interviewing

    with pytest.raises(IllegalTrigger):
        await machine.pause((await _piece(store, PieceStage.drafting, slug="d")).id)


@pytest.mark.asyncio
async def test_route_information_gap_to_interview(store: WorkStateStore) -> None:
    machine = _machine(store)
    council = await _piece(store, PieceStage.council, slug="c")
    review = await _piece(store, PieceStage.review, slug="r")

    assert (await machine.route_to_interview(council.id)).stage == PieceStage.interviewing
    assert (await machine.route_to_interview(review.id)).stage == PieceStage.interviewing

    with pytest.raises(IllegalTrigger):
        await machine.route_to_interview((await _piece(store, PieceStage.finalized, slug="f")).id)


# --- staleness triage (cmw-staleness-timestamps): last_human_touch_at ----------------------


@pytest.mark.asyncio
async def test_every_human_trigger_stamps_last_human_touch_at(store: WorkStateStore) -> None:
    """All 10 human-facing methods stamp the field, regardless of which internal path they take
    (``_trigger``, ``_advance``, or a direct ``_set_stage`` call after custom validation)."""
    machine = _machine(store)

    p = await _piece(store, PieceStage.interviewing, slug="a")
    assert p.last_human_touch_at is None
    assert (await machine.enough_input(p.id, actor="x")).last_human_touch_at is not None

    p = await _piece(store, PieceStage.review, slug="b", current_review_round_id="r1")
    assert (await machine.reviews_done(p.id, actor="x")).last_human_touch_at is not None

    p = await _piece(store, PieceStage.review, slug="c")
    assert (await machine.finalize(p.id, actor="x")).last_human_touch_at is not None

    p = await _piece(store, PieceStage.finalized, slug="d")
    assert (await machine.capture_lessons(p.id, actor="x")).last_human_touch_at is not None
    assert (await machine.finish_lessons(p.id, actor="x")).last_human_touch_at is not None

    p = await _piece(store, PieceStage.finalized, slug="e")
    assert (await machine.publish(p.id, actor="x")).last_human_touch_at is not None

    p = await _piece(store, PieceStage.paused, slug="f")
    assert (await machine.resume(p.id, actor="x")).last_human_touch_at is not None

    p = await _piece(store, PieceStage.council, slug="g")
    assert (await machine.route_to_interview(p.id, actor="x")).last_human_touch_at is not None

    p = await _piece(store, PieceStage.interviewing, slug="h")
    assert (await machine.pause(p.id, actor="x")).last_human_touch_at is not None

    p = await _piece(store, PieceStage.finalizing, slug="i")
    await store.jobs.insert(
        Job(type=JobType.finalize, piece_id=p.id, status=JobStatus.failed)
    )
    assert (await machine.retry_finalize(p.id, actor="x")).last_human_touch_at is not None


@pytest.mark.asyncio
async def test_batch_chain_stamps_human_touch_exactly_once_at_trigger_time(
    store: WorkStateStore,
) -> None:
    """The draft→council auto-chain a single ``enough_input`` call runs must not re-stamp
    ``last_human_touch_at`` on either job's own completion — only the initial human trigger does,
    or the field would misreport a machine-only job completion as a fresh human touch."""
    machine = _machine(store)
    piece = await _piece(store, PieceStage.interviewing)

    calls: list[str] = []
    original = store.pieces.mark_human_touch

    async def spy(piece_id: str, **kwargs: object) -> Piece:
        calls.append(piece_id)
        return await original(piece_id, **kwargs)

    store.pieces.mark_human_touch = spy  # type: ignore[method-assign]

    piece = await machine.enough_input(piece.id, actor="demo-mira@x")

    assert piece.stage == PieceStage.review  # the draft+council chain ran to completion
    assert calls == [piece.id]  # stamped exactly once, not once per chained job


@pytest.mark.asyncio
async def test_sweep_stuck_does_not_stamp_human_touch(store: WorkStateStore) -> None:
    """A crashed-worker sweep rolls a piece back to its last stable stage on its own — that is a
    machine action, so it must leave ``last_human_touch_at`` exactly as it was (``None`` here)."""
    from datetime import timedelta

    from app.models import utcnow

    machine = _machine(store)
    piece = await _piece(store, PieceStage.drafting)
    stale = utcnow() - timedelta(seconds=120)
    await store.jobs.insert(
        Job(
            type=JobType.draft,
            piece_id=piece.id,
            status=JobStatus.running,
            started_at=stale,
            heartbeat_at=stale,
        )
    )

    affected = await machine.sweep_stuck(timeout_seconds=30)

    assert len(affected) == 1
    assert affected[0].last_human_touch_at is None


# --- job success / failure / stuck flips ---------------------------------------------------


@pytest.mark.asyncio
async def test_job_runner_success_flip_and_cost_capture(store: WorkStateStore) -> None:
    provider = FakeProvider()
    registry = build_stub_registry(llm_calls=2)  # stub makes 2 provider calls → real usage capture
    runner = JobRunner(store, registry, provider=provider, sleep=_noop_sleep)
    piece = await _piece(store, PieceStage.drafting)

    job = await runner.enqueue(JobType.draft, piece_id=piece.id, triggered_by="demo-mira@x")
    assert JobStatus(job.status) == JobStatus.queued
    job = await runner.run(job.id)

    assert JobStatus(job.status) == JobStatus.succeeded
    assert job.attempts == 1
    assert job.started_at is not None and job.heartbeat_at is not None
    assert job.cost > 0  # usage captured through the provider seam
    assert provider.calls == 2


@pytest.mark.parametrize(
    "status",
    [JobStatus.running, JobStatus.succeeded, JobStatus.failed, JobStatus.stuck],
)
@pytest.mark.asyncio
async def test_job_runner_rejects_every_non_queued_job_without_replaying_step(
    store: WorkStateStore, status: JobStatus
) -> None:
    step = FlakyStep(JobType.draft, errors=[])
    registry = build_stub_registry()
    registry.register(step)
    runner = JobRunner(store, registry, sleep=_noop_sleep)
    job = await store.jobs.insert(Job(type=JobType.draft, status=status))

    with pytest.raises(RuntimeError, match=f"job {job.id!r} is not claimable from {status.value}"):
        await runner.run(job.id)

    assert step.attempts == 0
    assert (await store.jobs.get(job.id)).status == status


@pytest.mark.asyncio
async def test_concurrent_job_runner_calls_execute_the_step_once(store: WorkStateStore) -> None:
    step = FlakyStep(JobType.draft, errors=[])
    registry = build_stub_registry()
    registry.register(step)
    runner = JobRunner(store, registry, sleep=_noop_sleep)
    job = await runner.enqueue(JobType.draft)

    results = await asyncio.gather(
        runner.run(job.id), runner.run(job.id), return_exceptions=True
    )

    assert step.attempts == 1
    assert sum(isinstance(result, JobNotClaimable) for result in results) == 1
    completed = [result for result in results if isinstance(result, Job)]
    assert len(completed) == 1
    assert completed[0].status == JobStatus.succeeded


@pytest.mark.asyncio
async def test_failure_flags_piece_and_does_not_roll_back_content(store: WorkStateStore) -> None:
    registry = build_stub_registry()
    registry.register(StubStep(JobType.draft, fail=RefusalError("model refused")))
    machine = _machine(store, registry=registry)
    piece = await _piece(store, PieceStage.interviewing, latest_revision="rev-3")

    piece = await machine.enough_input(piece.id, actor="demo-mira@x")

    # flag-not-rollback: piece is back at its last stable stage, the committed revision is untouched.
    assert piece.stage == PieceStage.interviewing
    assert piece.latest_revision == "rev-3"
    failures = await machine.open_failures(piece.id)
    assert len(failures) == 1
    assert JobStatus(failures[0].status) == JobStatus.failed
    assert failures[0].error is not None and failures[0].error.code == "refusal"


@pytest.mark.asyncio
async def test_finalize_failure_stays_in_finalizing_flagged(store: WorkStateStore) -> None:
    # The settled graph gives finalizing only the → finalized edge, so a finalize failure is not
    # rolled back: the piece stays flagged in finalizing and is retried in place (never wedged).
    registry = build_stub_registry()
    registry.register(StubStep(JobType.finalize, fail=RefusalError("nope")))
    machine = _machine(store, registry=registry)
    piece = await _piece(store, PieceStage.review)

    piece = await machine.finalize(piece.id)

    assert piece.stage == PieceStage.finalizing
    assert len(await machine.open_failures(piece.id)) == 1


@pytest.mark.asyncio
async def test_stuck_detection_flags_piece(store: WorkStateStore) -> None:
    from datetime import timedelta

    from app.models import utcnow

    machine = _machine(store)
    piece = await _piece(store, PieceStage.drafting)
    stale = utcnow() - timedelta(seconds=120)
    await store.jobs.insert(
        Job(
            type=JobType.draft,
            piece_id=piece.id,
            status=JobStatus.running,
            started_at=stale,
            heartbeat_at=stale,
        )
    )

    affected = await machine.sweep_stuck(timeout_seconds=30)

    assert len(affected) == 1
    assert affected[0].stage == PieceStage.interviewing  # rolled back to last stable stage
    stuck_jobs = [j for j in await store.jobs.by_piece(piece.id)]
    assert JobStatus(stuck_jobs[0].status) == JobStatus.stuck


# --- retry policy: transient auto-retried, deterministic not -------------------------------


@pytest.mark.asyncio
async def test_transient_error_is_retried_then_succeeds(store: WorkStateStore) -> None:
    registry = build_stub_registry()
    step = FlakyStep(JobType.draft, errors=[FakeAPIError(429)])  # one transient failure, then ok
    registry.register(step)
    runner = JobRunner(store, registry, max_attempts=2, sleep=_noop_sleep)
    piece = await _piece(store, PieceStage.drafting)

    job = await runner.run((await runner.enqueue(JobType.draft, piece_id=piece.id)).id)

    assert JobStatus(job.status) == JobStatus.succeeded
    assert job.attempts == 2  # first attempt failed transiently, retry succeeded
    assert step.attempts == 2


@pytest.mark.asyncio
async def test_deterministic_error_is_not_retried(store: WorkStateStore) -> None:
    registry = build_stub_registry()
    step = FlakyStep(JobType.draft, errors=[FakeAPIError(400), FakeAPIError(400)])
    registry.register(step)
    runner = JobRunner(store, registry, max_attempts=3, sleep=_noop_sleep)
    piece = await _piece(store, PieceStage.drafting)

    job = await runner.run((await runner.enqueue(JobType.draft, piece_id=piece.id)).id)

    assert JobStatus(job.status) == JobStatus.failed
    assert job.attempts == 1  # 400 is deterministic — retrying unchanged would only fail again
    assert step.attempts == 1
    assert job.error is not None and job.error.code == "invalid_request"


@pytest.mark.asyncio
async def test_transient_error_exhausts_bounded_retries(store: WorkStateStore) -> None:
    registry = build_stub_registry()
    step = FlakyStep(JobType.draft, errors=[FakeAPIError(529), FakeAPIError(529), FakeAPIError(529)])
    registry.register(step)
    runner = JobRunner(store, registry, max_attempts=2, sleep=_noop_sleep)
    piece = await _piece(store, PieceStage.drafting)

    job = await runner.run((await runner.enqueue(JobType.draft, piece_id=piece.id)).id)

    assert JobStatus(job.status) == JobStatus.failed
    assert job.attempts == 2  # bounded: retried once, then gave up
    assert job.error is not None and job.error.code == "overloaded" and job.error.retryable


def test_classify_exception_taxonomy() -> None:
    assert classify_exception(RunBudgetExceeded("ceiling")).code == "ceiling"
    assert classify_exception(RunBudgetExceeded("ceiling")).retryable is False

    assert classify_exception(FakeAPIError(429)).retryable is True
    assert classify_exception(FakeAPIError(529)).code == "overloaded"
    assert classify_exception(FakeAPIError(503)).retryable is True
    assert classify_exception(FakeAPIError(500)).code == "server_error"

    assert classify_exception(FakeAPIError(400)).retryable is False
    assert classify_exception(FakeAPIError(400)).code == "invalid_request"
    assert classify_exception(FakeAPIError(422)).retryable is False

    assert classify_exception(FakeConnectionError("reset")).code == "network"
    assert classify_exception(FakeConnectionError("reset")).retryable is True

    assert classify_exception(RefusalError("refused")).code == "refusal"
    assert classify_exception(RefusalError("refused")).retryable is False

    assert classify_exception(ValueError("mystery")).retryable is False  # fail closed


# --- the one hard block: the per-run cost ceiling ------------------------------------------


@pytest.mark.asyncio
async def test_cost_ceiling_is_the_single_hard_block(store: WorkStateStore) -> None:
    provider = FakeProvider()
    registry = build_stub_registry(llm_calls=1)  # the draft stub will make one provider call
    # A budget already at its call ceiling: the pre-flight check fails before the call fires.
    machine = _machine(
        store, registry=registry, provider=provider, budget_factory=lambda: RunBudget(max_calls=0)
    )
    piece = await _piece(store, PieceStage.interviewing)

    piece = await machine.enough_input(piece.id, actor="demo-mira@x")

    # Ceiling → deterministic failure, not retried; piece flagged back at its last stable stage.
    assert piece.stage == PieceStage.interviewing
    assert provider.calls == 0  # blocked before the request even fired
    failures = await machine.open_failures(piece.id)
    assert len(failures) == 1
    assert failures[0].error is not None and failures[0].error.code == "ceiling"
    assert failures[0].attempts == 1  # a ceiling is never retried


# --- the step plug-in seam -----------------------------------------------------------------


def test_stub_registry_covers_every_job_type() -> None:
    registry = build_stub_registry()
    for job_type in JobType:
        assert registry.has(job_type)
        assert registry.get(job_type).job_type == job_type


@pytest.mark.asyncio
async def test_unregistered_job_type_is_a_clear_error(store: WorkStateStore) -> None:
    from app.orchestration import StepRegistry

    runner = JobRunner(store, StepRegistry(), sleep=_noop_sleep)
    job = await runner.enqueue(JobType.draft)
    with pytest.raises(LookupError):
        await runner.run(job.id)


@pytest.mark.asyncio
async def test_batch_trigger_without_registered_step_does_not_wedge(store: WorkStateStore) -> None:
    from app.orchestration import StepNotRegistered, StepRegistry

    # Empty registry → a batch trigger must fail BEFORE moving the piece, so it never lands in a
    # batch stage no worker can service (no wedge).
    machine = _machine(store, registry=StepRegistry())
    piece = await _piece(store, PieceStage.interviewing)

    with pytest.raises(StepNotRegistered):
        await machine.enough_input(piece.id)

    assert (await store.pieces.get(piece.id)).stage == PieceStage.interviewing
    assert await store.jobs.by_piece(piece.id) == []


@pytest.mark.asyncio
async def test_chain_stops_cleanly_when_a_later_stage_step_is_unregistered(
    store: WorkStateStore,
) -> None:
    """The empty-registry test above only proves the *first* stage a trigger enters is guarded.
    A partial rollout — one real step registered, its chained successor still a stub-free downstream
    ticket — used to reach ``self.runner.run`` for the successor and raise ``StepNotRegistered``
    AFTER the prior job's success (and its side effects) were already committed: the piece landed
    wedged in the successor's stage with an orphaned ``queued`` job for it, while the trigger's own
    exception looked identical to "nothing happened." The chain must instead stop in place, exactly
    like reaching a genuine interactive stage."""
    from app.orchestration import StepRegistry

    registry = StepRegistry()
    registry.register(StubStep(JobType.incorporate))  # council deliberately left unregistered
    machine = _machine(store, registry=registry)
    piece = await _piece(store, PieceStage.review, current_review_round_id="round-1")

    piece = await machine.reviews_done(piece.id, actor="demo-mira@x")

    assert piece.stage == PieceStage.council  # advanced past incorporate, parked before council
    jobs = await store.jobs.by_piece(piece.id)
    assert [JobType(j.type) for j in jobs] == [JobType.incorporate]  # no orphaned council job
    assert JobStatus(jobs[0].status) == JobStatus.succeeded


# --- the REST surface (the machine is FastAPI-hosted) --------------------------------------


def _wire_app(store: WorkStateStore, *, registry=None):
    """Attach a machine to the shared app's state (bypassing the lifespan, like the lake tests)."""
    from app.main import app

    registry = registry if registry is not None else build_stub_registry()
    app.state.piece_machine = PieceMachine(
        store, JobRunner(store, registry, sleep=_noop_sleep)
    )
    return app


async def _http(app):
    from httpx import ASGITransport, AsyncClient

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_http_human_trigger_runs_chain(store: WorkStateStore) -> None:
    app = _wire_app(store)
    piece = await _piece(store, PieceStage.interviewing)
    async with await _http(app) as client:
        resp = await client.post(f"/api/pieces/{piece.id}/enough-input", params={"actor": "s@x"})
    assert resp.status_code == 200
    assert resp.json()["stage"] == PieceStage.review.value


@pytest.mark.asyncio
async def test_http_finalize_accepts_formats_body(store: WorkStateStore) -> None:
    app = _wire_app(store)
    piece = await _piece(store, PieceStage.review)
    async with await _http(app) as client:
        resp = await client.post(
            f"/api/pieces/{piece.id}/finalize", json={"formats": ["html", "doc"]}
        )
    assert resp.status_code == 200
    assert resp.json()["stage"] == PieceStage.finalized.value
    [job] = await store.jobs.by_piece(piece.id)
    assert job.formats == ["html", "doc"]


@pytest.mark.asyncio
async def test_http_finalize_without_body_still_works(store: WorkStateStore) -> None:
    app = _wire_app(store)
    piece = await _piece(store, PieceStage.review)
    async with await _http(app) as client:
        resp = await client.post(f"/api/pieces/{piece.id}/finalize")
    assert resp.status_code == 200
    [job] = await store.jobs.by_piece(piece.id)
    assert job.formats is None


@pytest.mark.asyncio
async def test_http_retry_finalize_reclaims_failed_job_and_advances_piece(
    store: WorkStateStore,
) -> None:
    registry = build_stub_registry()
    registry.register(StubStep(JobType.finalize, fail=RefusalError("render unavailable")))
    app = _wire_app(store, registry=registry)
    piece = await _piece(store, PieceStage.review)

    async with await _http(app) as client:
        failed = await client.post(
            f"/api/pieces/{piece.id}/finalize", json={"formats": ["html"]}
        )
        assert failed.status_code == 200
        assert failed.json()["stage"] == PieceStage.finalizing.value

        registry.register(StubStep(JobType.finalize))
        retried = await client.post(f"/api/pieces/{piece.id}/finalize/retry")

    assert retried.status_code == 200
    assert retried.json()["stage"] == PieceStage.finalized.value
    [job] = await store.jobs.by_piece(piece.id)
    assert job.status == JobStatus.succeeded
    assert job.formats == ["html"]


@pytest.mark.asyncio
async def test_http_retry_finalize_reclaims_stuck_job(store: WorkStateStore) -> None:
    app = _wire_app(store)
    piece = await _piece(store, PieceStage.finalizing)
    job = await store.jobs.insert(
        Job(
            type=JobType.finalize,
            piece_id=piece.id,
            status=JobStatus.stuck,
            formats=["pdf"],
        )
    )

    async with await _http(app) as client:
        response = await client.post(f"/api/pieces/{piece.id}/finalize/retry")

    assert response.status_code == 200
    assert response.json()["stage"] == PieceStage.finalized.value
    assert (await store.jobs.get(job.id)).status == JobStatus.succeeded


@pytest.mark.asyncio
async def test_http_retry_finalize_reconciles_succeeded_job_without_replaying(
    store: WorkStateStore,
) -> None:
    step = FlakyStep(JobType.finalize, errors=[])
    registry = build_stub_registry()
    registry.register(step)
    app = _wire_app(store, registry=registry)
    piece = await _piece(store, PieceStage.finalizing)
    job = await store.jobs.insert(
        Job(type=JobType.finalize, piece_id=piece.id, status=JobStatus.succeeded)
    )

    async with await _http(app) as client:
        response = await client.post(f"/api/pieces/{piece.id}/finalize/retry")

    assert response.status_code == 200
    assert response.json()["stage"] == PieceStage.finalized.value
    assert step.attempts == 0
    assert (await store.jobs.get(job.id)).status == JobStatus.succeeded


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [JobStatus.queued, JobStatus.running])
async def test_http_retry_finalize_rejects_active_work_without_duplicate_execution(
    store: WorkStateStore, status: JobStatus
) -> None:
    step = FlakyStep(JobType.finalize, errors=[])
    registry = build_stub_registry()
    registry.register(step)
    app = _wire_app(store, registry=registry)
    piece = await _piece(store, PieceStage.finalizing)
    job = await store.jobs.insert(
        Job(type=JobType.finalize, piece_id=piece.id, status=status)
    )

    async with await _http(app) as client:
        response = await client.post(f"/api/pieces/{piece.id}/finalize/retry")

    assert response.status_code == 409
    assert step.attempts == 0
    assert (await store.jobs.get(job.id)).status == status
    assert (await store.pieces.get(piece.id)).stage == PieceStage.finalizing


@pytest.mark.asyncio
async def test_http_concurrent_finalize_retries_execute_failed_job_once(
    store: WorkStateStore,
) -> None:
    step = FlakyStep(JobType.finalize, errors=[])
    registry = build_stub_registry()
    registry.register(step)
    app = _wire_app(store, registry=registry)
    piece = await _piece(store, PieceStage.finalizing)
    await store.jobs.insert(
        Job(type=JobType.finalize, piece_id=piece.id, status=JobStatus.failed)
    )

    async with await _http(app) as client:
        responses = await asyncio.gather(
            client.post(f"/api/pieces/{piece.id}/finalize/retry"),
            client.post(f"/api/pieces/{piece.id}/finalize/retry"),
        )

    assert sorted(response.status_code for response in responses) == [200, 409]
    assert step.attempts == 1
    [job] = await store.jobs.by_piece(piece.id)
    assert job.status == JobStatus.succeeded
    assert (await store.pieces.get(piece.id)).stage == PieceStage.finalized


@pytest.mark.asyncio
async def test_http_concurrent_finalize_triggers_dispatch_exactly_one_job(
    store: WorkStateStore,
) -> None:
    app = _wire_app(store)
    piece = await _piece(store, PieceStage.review)
    original_get = store.pieces.get
    both_started = asyncio.Event()
    reads = 0

    async def synchronized_get(id: str):
        nonlocal reads
        current = await original_get(id)
        if not both_started.is_set():
            reads += 1
            if reads == 2:
                both_started.set()
            await both_started.wait()
        return current

    # Both HTTP commands validate the same source snapshot before either may persist its move.
    store.pieces.get = synchronized_get  # type: ignore[method-assign]

    async with await _http(app) as client:
        responses = await asyncio.gather(
            client.post(f"/api/pieces/{piece.id}/finalize"),
            client.post(f"/api/pieces/{piece.id}/finalize"),
        )

    assert sorted(response.status_code for response in responses) == [200, 409]
    jobs = await store.jobs.by_piece(piece.id)
    assert len(jobs) == 1
    assert jobs[0].status == JobStatus.succeeded


@pytest.mark.asyncio
async def test_http_interactive_gate_and_illegal_and_404(store: WorkStateStore) -> None:
    app = _wire_app(store)
    review = await _piece(store, PieceStage.review, slug="r")
    async with await _http(app) as client:
        ok = await client.post(f"/api/pieces/{review.id}/pause")
        assert ok.status_code == 200 and ok.json()["stage"] == PieceStage.paused.value

        illegal = await client.post(f"/api/pieces/{review.id}/enough-input")  # not from paused
        assert illegal.status_code == 409

        missing = await client.post("/api/pieces/nope/finalize")
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_http_batch_trigger_501_when_step_unregistered(store: WorkStateStore) -> None:
    from app.orchestration import StepRegistry

    app = _wire_app(store, registry=StepRegistry())  # no batch steps registered
    piece = await _piece(store, PieceStage.interviewing)
    async with await _http(app) as client:
        resp = await client.post(f"/api/pieces/{piece.id}/enough-input")
    assert resp.status_code == 501
    assert (await store.pieces.get(piece.id)).stage == PieceStage.interviewing  # not wedged


def test_http_503_when_machine_unconfigured() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    app.state.piece_machine = None
    resp = TestClient(app).post("/api/pieces/x/pause")
    assert resp.status_code == 503
