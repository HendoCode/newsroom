"""Narrative REST surface (domain model §1.5) — Oracle Entry B's seed.

An author-spoken seed carrying audience/angle intent (use case B). ``POST /api/narratives``
creates one; its id is what ``POST /api/oracle/run`` (``entry_mode=narrative``) needs as
``narrative_id``. No update/delete in v1 — a narrative is create-once, consumed by exactly one
Oracle run (the run records ``oracle_run_id`` back onto it, see ``app.oracle.service``).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.models.narrative import DistributionIntent, Narrative
from app.repositories import WorkStateStore
from app.schemas import DistributionIntentOut, NarrativeCreateRequest, NarrativeOut

router = APIRouter(prefix="/api/narratives", tags=["narratives"])


def narrative_to_out(narrative: Narrative) -> NarrativeOut:
    assert narrative.id is not None
    return NarrativeOut(
        id=narrative.id,
        author=narrative.author,
        seed_text=narrative.seed_text,
        intent=DistributionIntentOut(
            audience=narrative.intent.audience, angle=narrative.intent.angle
        ),
        oracle_run_id=narrative.oracle_run_id,
    )


def _require_store(request: Request) -> WorkStateStore:
    store = getattr(request.app.state, "work_state", None)
    if store is None:
        raise HTTPException(
            status_code=503, detail="narratives unavailable (MONGO_URL not configured)"
        )
    return store


@router.post("", response_model=NarrativeOut, status_code=201)
async def create_narrative(req: NarrativeCreateRequest, request: Request) -> NarrativeOut:
    """Speak a narrative (screen 8): seed text + audience/angle intent, attributed to its author."""
    store = _require_store(request)
    narrative = Narrative(
        author=req.author or "unknown",
        seed_text=req.seed_text,
        intent=DistributionIntent(audience=req.audience, angle=req.angle),
    )
    stored = await store.narratives.insert(narrative)
    return narrative_to_out(stored)


@router.get("/{narrative_id}", response_model=NarrativeOut)
async def get_narrative(narrative_id: str, request: Request) -> NarrativeOut:
    store = _require_store(request)
    narrative = await store.narratives.get(narrative_id)
    if narrative is None:
        raise HTTPException(status_code=404, detail=f"no narrative {narrative_id!r}")
    return narrative_to_out(narrative)
