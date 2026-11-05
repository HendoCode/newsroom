"""Background-job runner (open-decisions Item 4; domain model §1.16).

The runner owns a job's **lifecycle only** — ``queued → running → succeeded | failed | stuck`` —
over the settled :class:`~app.models.Job` record. It does **not** touch piece stages; the
:class:`~app.orchestration.machine.PieceMachine` layers stage transitions on top of the outcome.
That split keeps this module a small, testable engine: dispatch a step, capture ``usage``/cost,
apply the settled retry policy, and flag on failure.

What it guarantees (Item 4):

- **Atomic execution claims.** :meth:`run` starts only ``queued`` jobs; terminal/active jobs are
  rejected without replay. Explicit failed/stuck recovery goes through :meth:`retry`, whose own
  compare-and-set starts exactly one replacement execution.
- **Bounded retries keyed to the error taxonomy.** Transient errors (429/5xx/529/network) are
  retried up to ``max_attempts`` total; deterministic ones (400/refusal/ceiling) fail immediately
  — retrying unchanged would only fail again (:mod:`app.orchestration.retry`).
- **The per-run cost ceiling is the one hard stop** (D14). The shared :class:`RunBudget` pre-flights
  every provider call; a :class:`RunBudgetExceeded` becomes ``failed: ceiling`` and is never retried.
- **Heartbeat + stuck detection.** A running job stamps ``heartbeat_at``; :meth:`sweep_stuck` flips
  a running job whose heartbeat has gone stale to ``stuck`` (a crashed worker — plausible with the
  §6 parallel-instances requirement).
- **``usage``/cost capture.** Each run records the budget's spend delta onto ``Job.cost``.

Failure **flags, never rolls back** (D4/D16b): the runner records the error on the job and leaves
Git untouched — a step writes its new revision only on success, so a failed job leaves nothing
half-written to reconcile on retry.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from app.llm.budget import RunBudget
from app.llm.provider import LLMProvider
from app.models import Job, JobError, JobStatus, JobType, OracleRunParams, utcnow
from app.orchestration.retry import classify_exception
from app.orchestration.steps import StepContext, StepRegistry, StepResult
from app.repositories import WorkStateStore

# A step's failure is transient; wait between outer attempts. Injectable so tests don't really sleep
# (the ``anthropic`` SDK already applies the real per-request backoff underneath).
Sleeper = Callable[[float], Awaitable[None]]


class JobNotClaimable(RuntimeError):
    """Raised when execution is requested for a job that is no longer queued."""

    def __init__(self, job: Job) -> None:
        super().__init__(f"job {job.id!r} is not claimable from {JobStatus(job.status).value}")
        self.job = job


class JobRunner:
    """Runs one batch job to a terminal state. Construct once; share across the service.

    ``max_attempts`` is the *total* number of tries for a job (default 2 → one bounded outer retry
    on a transient error). ``provider`` / ``brain`` / ``content`` are handed to each step through
    its :class:`StepContext`; leaving ``provider`` ``None`` is fine for steps (like the stub) that
    don't call the LLM.
    """

    def __init__(
        self,
        store: WorkStateStore,
        registry: StepRegistry,
        *,
        max_attempts: int = 2,
        provider: LLMProvider | None = None,
        brain: object | None = None,
        content: object | None = None,
        lake: object | None = None,
        backoff_base_seconds: float = 0.5,
        sleep: Sleeper = asyncio.sleep,
        budget_factory: Callable[[], RunBudget] | None = None,
    ) -> None:
        self.store = store
        self.registry = registry
        self.max_attempts = max(1, max_attempts)
        self.provider = provider
        self.brain = brain
        self.content = content
        self.lake = lake
        self.backoff_base_seconds = backoff_base_seconds
        self._sleep = sleep
        # Each triggered run gets a fresh per-run ceiling. Default is unbounded; production
        # wires a real cost/token ceiling here — the one sanctioned hard block (D14).
        self._budget_factory = budget_factory or RunBudget

    async def enqueue(
        self,
        type: JobType,
        *,
        piece_id: str | None = None,
        triggered_by: str | None = None,
        oracle_params: OracleRunParams | None = None,
        formats: list[str] | None = None,
    ) -> Job:
        """Persist a fresh ``queued`` job. Oracle jobs run pieceless, so ``piece_id`` is optional;
        ``oracle_params`` carries the OracleRun's entry mode/lookback/narrative (§1.8) and is only
        meaningful for ``type=oracle``; ``formats`` is only meaningful for ``type=finalize`` (use
        case J "selectable at finalize")."""
        job = Job(
            type=type,
            piece_id=piece_id,
            triggered_by=triggered_by,
            oracle_params=oracle_params,
            formats=formats,
            status=JobStatus.queued,
        )
        return await self.store.jobs.insert(job)

    async def run(self, job_id: str, *, budget: RunBudget | None = None) -> Job:
        """Drive ``job_id`` to a terminal state and return the final :class:`Job` record.

        Marks the job ``running`` (stamping ``started_at``/``heartbeat_at``), dispatches the step
        with bounded retries, captures ``usage``/cost, and finishes ``succeeded`` or ``failed``.
        A shared ``budget`` enforces the per-run ceiling; one is created if not supplied so every
        run is bounded by construction.
        """
        job = await self.store.jobs.get(job_id)
        if job is None:
            raise KeyError(f"no job {job_id!r}")
        self.registry.get(JobType(job.type))
        claimed = await self.store.jobs.claim(job.id)
        if claimed is None:
            current = await self.store.jobs.get(job.id)
            if current is None:
                raise KeyError(f"no job {job_id!r}")
            raise JobNotClaimable(current)
        return await self._run_claimed(claimed, budget)

    async def retry(self, job_id: str, *, budget: RunBudget | None = None) -> Job:
        """Explicitly reclaim one failed/stuck job and run one new bounded execution."""
        job = await self.store.jobs.get(job_id)
        if job is None:
            raise KeyError(f"no job {job_id!r}")
        self.registry.get(JobType(job.type))
        claimed = await self.store.jobs.reclaim(job.id)
        if claimed is None:
            current = await self.store.jobs.get(job.id)
            if current is None:
                raise KeyError(f"no job {job_id!r}")
            raise JobNotClaimable(current)
        return await self._run_claimed(claimed, budget)

    async def _run_claimed(self, job: Job, budget: RunBudget | None) -> Job:
        """Run the bounded attempt loop after a repository claim has succeeded."""
        budget = budget or self._budget_factory()
        step = self.registry.get(JobType(job.type))

        cost_before = budget.cost
        last_error: JobError | None = None
        for attempt in range(1, self.max_attempts + 1):
            job = await self._save(job.id, attempts=attempt, heartbeat_at=utcnow())
            piece = (
                await self.store.pieces.get(job.piece_id) if job.piece_id is not None else None
            )
            ctx = StepContext(
                job=job,
                store=self.store,
                budget=budget,
                piece=piece,
                provider=self.provider,
                brain=self.brain,  # type: ignore[arg-type]
                content=self.content,  # type: ignore[arg-type]
                lake=self.lake,  # type: ignore[arg-type]
                heartbeat=lambda jid=job.id: self._touch_heartbeat(jid),
                budget_factory=self._budget_factory,
            )
            try:
                result = await step.run(ctx)
            except Exception as exc:  # noqa: BLE001 — classify every failure, never crash the runner
                last_error = classify_exception(exc)
                if last_error.retryable and attempt < self.max_attempts:
                    await self._sleep(self.backoff_base_seconds * attempt)
                    continue
                return await self._finish_failed(job, last_error, budget, cost_before)
            return await self._finish_succeeded(job, result, budget, cost_before)

        # Loop only exits via return above; this is defensive and unreachable in practice.
        return await self._finish_failed(
            job, last_error or JobError(code="unknown", message="no attempt ran"), budget, cost_before
        )

    async def sweep_stuck(
        self, *, timeout_seconds: float, now: datetime | None = None
    ) -> list[Job]:
        """Flag every ``running`` job whose heartbeat has gone stale as ``stuck`` (crashed worker).

        Returns the jobs it flipped so a caller (the machine) can flag/recover their pieces. A
        ``stuck`` error is marked retryable — a reclaimed job can be re-run — but this method only
        touches the job record; the piece is the machine's concern.
        """
        now = now or utcnow()
        cutoff = now - timedelta(seconds=timeout_seconds)
        flipped: list[Job] = []
        for job in await self.store.jobs.by_status(JobStatus.running):
            last_beat = job.heartbeat_at or job.started_at
            if last_beat is not None and last_beat < cutoff:
                error = JobError(
                    code="stuck",
                    message=f"no heartbeat since {last_beat.isoformat()}",
                    retryable=True,
                )
                flipped.append(await self._save(job.id, status=JobStatus.stuck, error=error))
        return flipped

    # --- internals ------------------------------------------------------------------------

    async def _touch_heartbeat(self, job_id: str) -> None:
        await self.store.jobs.update(job_id, {"heartbeat_at": utcnow()})

    async def _finish_succeeded(
        self, job: Job, result: StepResult, budget: RunBudget, cost_before: float
    ) -> Job:
        return await self._save(
            job.id,
            status=JobStatus.succeeded,
            error=None,
            cost=round(budget.cost - cost_before, 6),
        )

    async def _finish_failed(
        self, job: Job, error: JobError, budget: RunBudget, cost_before: float
    ) -> Job:
        # Failure flags the job; it never rolls back committed Git content (D4/D16b). The piece
        # rollback (to its last stable stage) is applied by the machine on top of this outcome.
        return await self._save(
            job.id,
            status=JobStatus.failed,
            error=error,
            cost=round(budget.cost - cost_before, 6),
        )

    async def _save(self, job_id: str, **changes: object) -> Job:
        updated = await self.store.jobs.update(job_id, changes)
        assert updated is not None, f"job {job_id!r} vanished mid-run"
        return updated
