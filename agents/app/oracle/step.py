"""The Oracle batch step — plugs into the orchestration core's ``BatchStep`` seam (D5).

Oracle jobs are pieceless (``ctx.piece`` is ``None`` — the domain model's OracleRun runs before any
Piece exists, §1.8) and are dispatched directly through the shared ``JobRunner`` (see
``app.oracle.routes``) rather than through ``PieceMachine``'s batch chain, which is piece-stage-
shaped (there is no "oracle" ``PieceStage``). This step only adapts the framework seam
(``StepContext``/``StepResult``) onto :class:`~app.oracle.service.OracleService`, which does the
actual retrieve → rank → persist work.
"""

from __future__ import annotations

from app.models import JobType, OracleRunResultRecord
from app.oracle.service import OracleService
from app.orchestration.retry import PermanentStepError
from app.orchestration.steps import BatchStep, StepContext, StepResult


class OracleStep(BatchStep):
    job_type = JobType.oracle

    async def run(self, ctx: StepContext) -> StepResult:
        if ctx.lake is None:
            raise PermanentStepError("oracle step requires a content lake (ctx.lake)")
        if ctx.provider is None:
            raise PermanentStepError("oracle step requires an LLM provider (ctx.provider)")
        if ctx.brain is None:
            raise PermanentStepError("oracle step requires the Git brain (ctx.brain)")
        if ctx.job.oracle_params is None:
            raise PermanentStepError("oracle job is missing its run parameters (oracle_params)")

        await ctx.beat()
        service = OracleService(
            store=ctx.store, lake=ctx.lake, provider=ctx.provider, brain=ctx.brain
        )
        outcome = await service.run(job=ctx.job, params=ctx.job.oracle_params, budget=ctx.budget)
        assert ctx.job.id is not None
        record = OracleRunResultRecord(
            spike_ids=[s.id for s in outcome.spikes if s.id],
            notes=list(outcome.notes),
            candidates_considered=outcome.candidates_considered,
        )
        await ctx.store.jobs.update(ctx.job.id, {"oracle_result": record.model_dump()})
        await ctx.beat()
        return StepResult(usage=outcome.usage, notes=outcome.notes)
