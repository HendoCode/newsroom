"""HTTP surface for derivative lineage (cmw-lesson-lineage-impl).

Child artifacts of an anchor by default; promote mints a top-level Piece. Native generation is
out of scope — creating a child records the destination, it does not draft the native.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.derivatives.errors import (
    DerivativeAlreadyExists,
    DerivativeAlreadyPromoted,
    DerivativeNotFound,
)
from app.derivatives.quality import (
    DERIVATIVE_QUALITY_BAR,
    UNIVERSAL_GATE_NAMES,
    derivative_council_editors,
    derivative_publish_gate,
)
from app.derivatives.service import DerivativesService
from app.models import DerivativeArtifact, DerivativeLineage
from app.repositories import WorkStateStore
from app.schemas import (
    CreateDerivativeRequest,
    DerivativeArtifactOut,
    DerivativeQualityOut,
    PromoteDerivativeRequest,
)

router = APIRouter(prefix="/api/pieces", tags=["derivatives"])


async def _quality(store: WorkStateStore, artifact: DerivativeArtifact) -> DerivativeQualityOut:
    """The derivative quality bar for one artifact (app.derivatives.quality). Children are never
    publishable on their own; a promoted artifact reports its promoted piece's live gate."""
    editors = list(derivative_council_editors(artifact.destination))
    gates = list(UNIVERSAL_GATE_NAMES)
    if DerivativeLineage(artifact.lineage) != DerivativeLineage.promoted or not artifact.promoted_piece_id:
        return DerivativeQualityOut(
            required=True,
            cleared=False,
            bar=DERIVATIVE_QUALITY_BAR,
            reasons=[
                "child artifact — a child cannot publish; promote it, and the promoted piece "
                f"must clear its own council at {DERIVATIVE_QUALITY_BAR:g}/10 first"
            ],
            editors=editors,
            universal_gates=gates,
        )
    piece = await store.pieces.get(artifact.promoted_piece_id)
    if piece is None:
        return DerivativeQualityOut(
            required=True,
            cleared=False,
            bar=DERIVATIVE_QUALITY_BAR,
            reasons=["the promoted piece no longer exists — the gate cannot be evaluated"],
            editors=editors,
            universal_gates=gates,
        )
    gate = await derivative_publish_gate(store, piece)
    return DerivativeQualityOut(
        required=gate.required,
        cleared=gate.cleared,
        bar=gate.bar,
        aggregate=gate.aggregate,
        council_revision=gate.council_revision,
        reasons=gate.reasons,
        editors=editors,
        universal_gates=gates,
    )


async def _out(store: WorkStateStore, artifact: DerivativeArtifact) -> DerivativeArtifactOut:
    assert artifact.id is not None
    lineage = artifact.lineage if isinstance(artifact.lineage, str) else artifact.lineage.value
    return DerivativeArtifactOut(
        id=artifact.id,
        anchor_piece_id=artifact.anchor_piece_id,
        content_project_id=artifact.content_project_id,
        destination=artifact.destination,
        title=artifact.title,
        voice=artifact.voice,
        lineage=lineage,
        promoted_piece_id=artifact.promoted_piece_id,
        quality=await _quality(store, artifact),
    )


def _require_store(request: Request) -> WorkStateStore:
    store = getattr(request.app.state, "work_state", None)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="derivatives unavailable (MONGO_URL not configured)",
        )
    return store


@router.get("/{piece_id}/derivatives", response_model=list[DerivativeArtifactOut])
async def list_derivatives(piece_id: str, request: Request) -> list[DerivativeArtifactOut]:
    store = _require_store(request)
    service = DerivativesService(store)
    try:
        artifacts = await service.list_for_anchor(piece_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [await _out(store, item) for item in artifacts]


@router.post("/{piece_id}/derivatives", response_model=DerivativeArtifactOut, status_code=201)
async def create_derivative(
    piece_id: str, req: CreateDerivativeRequest, request: Request
) -> DerivativeArtifactOut:
    store = _require_store(request)
    service = DerivativesService(store)
    try:
        artifact = await service.create_child(
            piece_id, destination=req.destination, title=req.title
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DerivativeAlreadyExists as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _out(store, artifact)


@router.post(
    "/{piece_id}/derivatives/{artifact_id}/promote",
    response_model=DerivativeArtifactOut,
)
async def promote_derivative(
    piece_id: str,
    artifact_id: str,
    req: PromoteDerivativeRequest,
    request: Request,
) -> DerivativeArtifactOut:
    store = _require_store(request)
    service = DerivativesService(store)
    try:
        artifact, _piece = await service.promote(
            piece_id, artifact_id, owner=req.owner or req.actor
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DerivativeNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DerivativeAlreadyPromoted as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return await _out(store, artifact)
