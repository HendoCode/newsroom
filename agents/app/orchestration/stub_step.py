"""A trivial stub batch step that proves the orchestration loop end-to-end.

This is the ONE stub the ticket asks for: it exercises dispatch → run → status-flip → advance (and,
when told to fail, the flag-not-rollback path) through the real :class:`~app.orchestration.machine.PieceMachine`
and :class:`~app.orchestration.jobs.JobRunner` — **without implementing any real pipeline step**
(Oracle, draft, council, incorporate, finalize are all downstream tickets).

It also demonstrates the seams a real step will use: if a :class:`~app.llm.provider.LLMProvider`
is present on the context it makes one trivial ``complete`` call so ``usage``/cost capture and the
per-run ceiling (D14) flow through the exact code path a real step will hit; otherwise it is a pure
no-op success. A configured ``fail`` exception lets a test drive the failure/flagging path.
"""

from __future__ import annotations

from app.llm.pricing import Usage
from app.llm.tiering import PipelineStep
from app.models import JobType
from app.orchestration.steps import BatchStep, StepContext, StepRegistry, StepResult

# Map each batch job to a plausible LLM step, so the stub's demo call routes/telemeters sensibly.
_STEP_FOR_JOB: dict[JobType, PipelineStep] = {
    JobType.oracle: PipelineStep.ORACLE,
    JobType.draft: PipelineStep.DRAFT,
    JobType.council: PipelineStep.COUNCIL,
    JobType.incorporate: PipelineStep.REWRITE,
    JobType.finalize: PipelineStep.DRAFT,  # finalize is a render; DRAFT is only a telemetry label
}


class StubStep(BatchStep):
    """A no-op step for one job type. Succeeds by default; raises ``fail`` if configured.

    ``llm_calls`` trivial provider calls are made when a provider is on the context, so the budget
    charging / ceiling pre-flight / ``usage`` capture are all exercised through the real seam.
    """

    def __init__(
        self,
        job_type: JobType,
        *,
        fail: Exception | None = None,
        llm_calls: int = 0,
        max_tokens: int = 256,
    ) -> None:
        self.job_type = JobType(job_type)
        self._fail = fail
        self._llm_calls = llm_calls
        self._max_tokens = max_tokens

    async def run(self, ctx: StepContext) -> StepResult:
        await ctx.beat()  # a real long step would beat periodically; prove the seam is wired
        if self._fail is not None:
            raise self._fail
        usage = Usage()
        if ctx.provider is not None and self._llm_calls > 0:
            step = _STEP_FOR_JOB.get(self.job_type, PipelineStep.DRAFT)
            for i in range(self._llm_calls):
                result = await ctx.provider.complete(
                    step=step,
                    model="claude-opus-4-8",
                    system=["stub-step stable prefix"],
                    messages=[{"role": "user", "content": f"stub call {i}"}],
                    max_tokens=self._max_tokens,
                    budget=ctx.budget,
                )
                usage = usage + result.usage
        return StepResult(usage=usage, notes=[f"stub {self.job_type.value} ok"])


def build_stub_registry(*, llm_calls: int = 0) -> StepRegistry:
    """A registry with a no-op :class:`StubStep` for every batch job type — enough for the machine
    to run the whole batch chain end-to-end. Downstream tickets replace these one at a time with the
    real Oracle/draft/council/incorporate/finalize steps."""
    registry = StepRegistry()
    for job_type in JobType:
        registry.register(StubStep(job_type, llm_calls=llm_calls))
    return registry
