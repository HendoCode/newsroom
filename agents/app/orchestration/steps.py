"""The batch-step plug-in seam (D5; open-decisions Item 2; context report §1/§11).

This is the one interface every batch pipeline step — Oracle, draft, council, incorporate,
finalize — implements. The deterministic state machine (``machine.PieceMachine``) owns *sequencing*
and the job runner (``jobs.JobRunner``) owns the *job lifecycle*; a step owns only the actual work
for its one stage. The steps themselves are **downstream tickets** — this module defines the seam
and the value types they exchange, plus the stub that proves the full loop lives in
:mod:`app.orchestration.stub_step`.

The contract, deliberately narrow so the framework stays in control:

- A step is handed a :class:`StepContext` — the piece's durable context: the work-state store, the
  swappable :class:`~app.llm.provider.LLMProvider` seam, the per-run :class:`~app.llm.budget.RunBudget`
  (the one hard ceiling, D14), the Git brain/content read handles, and a ``heartbeat`` it must call
  during long work so stuck-detection can tell a live worker from a crashed one.
- On success it returns a :class:`StepResult` (captured ``usage`` + any editorial-block counts it
  discovered). The runner flips the job to ``succeeded`` and the machine advances the piece.
- On failure it **raises**. The runner classifies the exception against the Anthropic error
  taxonomy (:mod:`app.orchestration.retry`), applies bounded retries for transient errors, and on
  final failure flags the piece — never rolling back committed Git content (D4/D16b).

Context assembly (which brain files, the tier split, the cache plan) is a **per-step** concern the
step implements against the provider seam (context report §1/§11) — this core does not assemble
prompts; it just hands the step the seams it needs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.llm.budget import RunBudget
from app.llm.pricing import Usage
from app.llm.provider import LLMProvider
from app.models import Job, JobType, Piece

if TYPE_CHECKING:  # avoid import cycles / optional Git deps at runtime
    from app.git import GitBrain, GitContentStore
    from app.lake import ContentLake
    from app.repositories import WorkStateStore


@dataclass

class StepContext:
    """Everything a batch step is given to do its one stage of work.

    The framework builds this per job run and hands it to :meth:`BatchStep.run`. A step reads the
    piece + its durable context (Git brain/content, work-state), assembles its own prompt, and
    drives the LLM through :attr:`provider`, charging :attr:`budget` (the per-run ceiling).
    Oracle jobs run before a piece exists, so :attr:`piece` may be ``None``.
    """

    job: Job
    store: WorkStateStore
    budget: RunBudget
    piece: Piece | None = None
    provider: LLMProvider | None = None
    brain: GitBrain | None = None
    content: GitContentStore | None = None
    # The content lake's query seam (D9) — the Oracle (and, later, research/drafting) retrieve
    # through this handle rather than reimplementing retrieval. ``None`` for steps that never
    # query the lake.
    lake: ContentLake | None = None
    # Called by the step during long work; the runner refreshes the job heartbeat so a live worker
    # is never mistaken for a crashed one (stuck-detection, Item 4).
    heartbeat: Callable[[], Awaitable[None]] | None = None
    # Factory to create a fresh RunBudget when no explicit budget is supplied. Used by steps
    # that create sub-services (e.g., LessonsService) that need their own budget fallback.
    budget_factory: Callable[[], RunBudget] | None = None

    async def beat(self) -> None:
        """Convenience: touch the heartbeat if the runner supplied one (a no-op otherwise)."""
        if self.heartbeat is not None:
            await self.heartbeat()


@dataclass
class StepResult:
    """What a step returns on success — only what the **framework** needs.

    The runner reads ``usage`` (the shared budget already tracks cost; this is captured for
    completeness/telemetry) and records ``notes`` (e.g. a completed-with-gap note from a partial
    failure — no silent drops, §1.16). A step persists its own work-state — the new revision
    pointer, council id, open GAP/clearance counts (§1.11), etc. — directly via ``ctx.store`` /
    ``ctx.content`` before returning; those are the step's concern, not the machine's, which owns
    only the stage transition.
    """

    usage: Usage = field(default_factory=Usage)
    notes: list[str] = field(default_factory=list)


class BatchStep(ABC):
    """The plug-in seam. Each downstream batch step subclasses this, sets :attr:`job_type`, and
    implements :meth:`run`. The framework never imports a concrete step — it resolves them through
    the :class:`StepRegistry`, so steps are added without touching the machine or the runner."""

    #: The job type this step handles (exactly one).
    job_type: JobType

    @abstractmethod
    async def run(self, ctx: StepContext) -> StepResult:
        """Do this stage's work. Return a :class:`StepResult` on success; **raise** on failure
        (the runner classifies the exception for retry/flagging). Must not mutate the sacred
        transcript or overwrite a committed Git revision (D4/D16b) — a new revision is written
        only on success, by the step, before it returns."""


class StepNotRegistered(LookupError):
    """No :class:`BatchStep` is registered for a job type yet (its step is a downstream ticket)."""


class StepRegistry:
    """Maps a :class:`~app.models.JobType` to the :class:`BatchStep` that handles it.

    The single lookup table the runner consults to dispatch a job. Downstream tickets register
    their step here; the framework depends only on this indirection, never on a concrete step.
    """

    def __init__(self) -> None:
        self._by_type: dict[JobType, BatchStep] = {}

    def register(self, step: BatchStep) -> None:
        self._by_type[JobType(step.job_type)] = step

    def get(self, job_type: JobType) -> BatchStep:
        try:
            return self._by_type[JobType(job_type)]
        except KeyError as exc:
            raise StepNotRegistered(
                f"no batch step registered for job type {job_type!r} (downstream ticket)"
            ) from exc

    def has(self, job_type: JobType) -> bool:
        return JobType(job_type) in self._by_type
