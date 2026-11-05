"""HTTP surface for the orchestration core (D5) — the state machine over REST.

Thin wrappers over :class:`~app.orchestration.machine.PieceMachine` so the three human triggers and
the interactive gates are reachable at the service's REST boundary (the boundary the Next.js BFF
calls). The machine is the real API; these routes just expose it and map its errors to HTTP:

- unknown piece → 404,
- an illegal trigger from the current stage → 409,
- a batch step not yet implemented (its ticket is downstream) → 501,
- the machine not configured (no Mongo) → 503.

The machine is attached to ``app.state.piece_machine`` in the lifespan (``app.main``); the batch
step registry on ``app.state.step_registry`` starts empty — the seam downstream Oracle/draft/council/
incorporate/finalize tickets populate. The interactive gates (pause/resume, lessons, gap-interview)
work immediately; the batch triggers return 501 until their step is registered.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.models import JobStatus, JobType, Piece, PieceStage
from app.orchestration.machine import IllegalTrigger, PieceMachine
from app.orchestration.steps import StepNotRegistered
from app.schemas import FailedJobRef

router = APIRouter(tags=["orchestration"])


class FinalizeRequest(BaseModel):
    """Optional body for the finalize trigger (use case J: outputs are selectable at finalize).
    ``formats`` narrows the run to a subset of ``html``/``pdf``/``doc``; omitted/``null`` takes the
    finalize step's own default (all three) — validated there, not re-validated at this boundary."""

    formats: list[str] | None = None


class PieceStateResponse(BaseModel):
    """A piece's current state after a trigger: its stage, cost, and any failure flags."""

    id: str
    slug: str
    stage: str
    failures: list[FailedJobRef] = Field(default_factory=list)


def get_machine(request: Request) -> PieceMachine:
    machine = getattr(request.app.state, "piece_machine", None)
    if machine is None:
        raise HTTPException(status_code=503, detail="orchestration unavailable (MONGO_URL not configured)")
    return machine


MachineDep = Annotated[PieceMachine, Depends(get_machine)]


async def _state(machine: PieceMachine, piece: Piece) -> PieceStateResponse:
    assert piece.id is not None
    failures = await machine.open_failures(piece.id)
    return PieceStateResponse(
        id=piece.id,
        slug=piece.slug,
        stage=PieceStage(piece.stage).value,
        failures=[
            FailedJobRef(
                type=JobType(j.type).value,
                code=(j.error.code if j.error else JobStatus(j.status).value),
                message=(j.error.message if j.error else ""),
                triggered_by=j.triggered_by,
                retryable=(j.error.retryable if j.error else False),
                cost=j.cost,
            )
            for j in failures
        ],
    )


async def _run(machine: PieceMachine, piece_id: str, coro) -> PieceStateResponse:
    """Invoke a machine trigger and map its domain errors onto HTTP status codes."""
    try:
        piece = await coro
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StepNotRegistered as exc:  # subclass of LookupError — check before IllegalTrigger/ValueError
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except IllegalTrigger as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return await _state(machine, piece)


# --- the three human triggers -------------------------------------------------------------


@router.post("/api/pieces/{piece_id}/enough-input", response_model=PieceStateResponse)
async def enough_input(piece_id: str, machine: MachineDep, actor: str | None = None) -> PieceStateResponse:
    """HUMAN "enough input" (D16a): interviewing → drafting → council → review."""
    return await _run(machine, piece_id, machine.enough_input(piece_id, actor=actor))


@router.post("/api/pieces/{piece_id}/reviews-done", response_model=PieceStateResponse)
async def reviews_done(piece_id: str, machine: MachineDep, actor: str | None = None) -> PieceStateResponse:
    """HUMAN "reviews done" (D4): review → incorporating → re-council → review."""
    return await _run(machine, piece_id, machine.reviews_done(piece_id, actor=actor))


@router.post("/api/pieces/{piece_id}/finalize", response_model=PieceStateResponse)
async def finalize(
    piece_id: str,
    machine: MachineDep,
    actor: str | None = None,
    body: FinalizeRequest | None = None,
) -> PieceStateResponse:
    """HUMAN "finalize" (use case J): review → finalizing → finalized. An optional JSON body
    selects a subset of output formats; no body (or a null `formats`) takes the step's default."""
    formats = body.formats if body else None
    return await _run(machine, piece_id, machine.finalize(piece_id, actor=actor, formats=formats))


@router.post("/api/pieces/{piece_id}/finalize/retry", response_model=PieceStateResponse)
async def retry_finalize(
    piece_id: str, machine: MachineDep, actor: str | None = None
) -> PieceStateResponse:
    """Explicitly retry failed/stuck finalize work without replaying active/succeeded effects."""
    return await _run(machine, piece_id, machine.retry_finalize(piece_id, actor=actor))


# --- interactive gates / edges (no batch job needed) --------------------------------------


@router.post("/api/pieces/{piece_id}/capture-lessons", response_model=PieceStateResponse)
async def capture_lessons(piece_id: str, machine: MachineDep, actor: str | None = None) -> PieceStateResponse:
    """HUMAN "capture lessons" (use case H): finalized → lessons (D12 gate opens)."""
    return await _run(machine, piece_id, machine.capture_lessons(piece_id, actor=actor))


@router.post("/api/pieces/{piece_id}/finish-lessons", response_model=PieceStateResponse)
async def finish_lessons(piece_id: str, machine: MachineDep, actor: str | None = None) -> PieceStateResponse:
    """Close the D12 lessons gate: lessons → finalized."""
    return await _run(machine, piece_id, machine.finish_lessons(piece_id, actor=actor))


@router.post("/api/pieces/{piece_id}/route-to-interview", response_model=PieceStateResponse)
async def route_to_interview(piece_id: str, machine: MachineDep, actor: str | None = None) -> PieceStateResponse:
    """Route an information gap back to a targeted interview (D16a): council/review → interviewing."""
    return await _run(machine, piece_id, machine.route_to_interview(piece_id, actor=actor))


@router.post("/api/pieces/{piece_id}/pause", response_model=PieceStateResponse)
async def pause(piece_id: str, machine: MachineDep, actor: str | None = None) -> PieceStateResponse:
    """D6 "stop for the day": interviewing/review → paused."""
    return await _run(machine, piece_id, machine.pause(piece_id, actor=actor))


@router.post("/api/pieces/{piece_id}/resume", response_model=PieceStateResponse)
async def resume(piece_id: str, machine: MachineDep, actor: str | None = None) -> PieceStateResponse:
    """Resume a paused piece: paused → interviewing."""
    return await _run(machine, piece_id, machine.resume(piece_id, actor=actor))
