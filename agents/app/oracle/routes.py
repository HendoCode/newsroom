"""HTTP surface for the Oracle (domain model §1.8) — the on-demand run entrypoint.

Oracle runs are pieceless batch jobs (§1.8: an OracleRun *is* a ``Job(type=oracle)`` that runs
before any Piece exists), so they are dispatched directly through the shared ``JobRunner`` rather
than through ``PieceMachine``'s batch chain, which is piece-stage-shaped
(``app.orchestration.routes`` has no "oracle" trigger — there is no "oracle" ``PieceStage``). This
is the one new REST surface this ticket adds; everything else is built on the merged
lake/state-machine/LLM-provider/data-layer seams.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.models import Job, JobStatus, JobType, OracleEntryMode, OracleRunParams
from app.orchestration.jobs import JobRunner
from app.orchestration.steps import StepNotRegistered
from app.schemas import SpikeOut
from app.spikes import spike_to_out

router = APIRouter(prefix="/api/oracle", tags=["oracle"])


class OracleRunRequest(BaseModel):
    """Trigger one on-demand Oracle run (D7 — no scheduler, ever)."""

    entry_mode: OracleEntryMode = OracleEntryMode.open_scan
    voice: str
    lookback_days: int = 7
    narrative_id: str | None = None  # required when entry_mode == narrative (Entry B)
    top_k: int | None = None  # override the entry-mode default cap
    triggered_by: str | None = None  # attribution — becomes the produced spikes' creator


class OracleRunResponse(BaseModel):
    """This run's outcome — spikes produced by *this* job only, never the Vault.

    ``job_id`` is the durable run identity (an OracleRun is a ``Job(type=oracle)``).
    ``GET /api/oracle/runs/{job_id}`` re-reads the same payload after the POST returns.
    """

    job_id: str
    status: str
    cost_usd: float = 0.0
    error: str | None = None
    notes: list[str] = []
    candidates_considered: int = 0
    spike_ids: list[str] = []
    spikes: list[SpikeOut] = []


def get_runner(request: Request) -> JobRunner:
    runner = getattr(request.app.state, "job_runner", None)
    if runner is None:
        raise HTTPException(
            status_code=503, detail="oracle unavailable (MONGO_URL not configured)"
        )
    return runner


RunnerDep = Annotated[JobRunner, Depends(get_runner)]


@router.post("/run", response_model=OracleRunResponse)
async def run_oracle(req: OracleRunRequest, runner: RunnerDep) -> OracleRunResponse:
    """Enqueue + run one Oracle job to completion and report its outcome.

    Validation of the Entry-B/narrative_id pairing lives on ``OracleRunParams`` itself (raises
    ``ValueError`` → 400 here, before a job is even created). A batch step not yet registered
    (a fresh service with no Oracle step wired) reports 501, matching the orchestration routes.
    """
    try:
        params = OracleRunParams(
            entry_mode=req.entry_mode,
            voice=req.voice,
            lookback_days=req.lookback_days,
            narrative_id=req.narrative_id,
            top_k=req.top_k,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = await runner.enqueue(
        JobType.oracle, triggered_by=req.triggered_by, oracle_params=params
    )
    assert job.id is not None  # always set by the repository on insert
    job_id = job.id
    try:
        job = await runner.run(job_id)
    except StepNotRegistered as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    return await _response_from_job(job, runner)


@router.get("/runs/{job_id}", response_model=OracleRunResponse)
async def get_oracle_run(job_id: str, runner: RunnerDep) -> OracleRunResponse:
    """Re-read one Oracle run by ``Job.id``. Empty ``spikes`` is an honest empty result, never
    the Vault — same body as ``POST /run``."""
    job = await runner.store.jobs.get(job_id)
    if job is None or JobType(job.type) != JobType.oracle:
        raise HTTPException(status_code=404, detail=f"no oracle run {job_id!r}")
    return await _response_from_job(job, runner)


async def _response_from_job(job: Job, runner: JobRunner) -> OracleRunResponse:
    assert job.id is not None
    result = job.oracle_result
    spike_ids = list(result.spike_ids) if result is not None else []
    spikes: list[SpikeOut] = []
    for spike_id in spike_ids:
        spike = await runner.store.spikes.get(spike_id)
        if spike is not None:
            spikes.append(spike_to_out(spike))
    return OracleRunResponse(
        job_id=job.id,
        status=JobStatus(job.status).value,
        cost_usd=job.cost,
        error=job.error.message if job.error else None,
        notes=list(result.notes) if result is not None else [],
        candidates_considered=result.candidates_considered if result is not None else 0,
        spike_ids=spike_ids,
        spikes=spikes,
    )
