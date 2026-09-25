"""Spikes & Vault REST surface (domain model §1.6/§1.7, D15) — the browser + the pick hand-off.

``GET /api/spikes`` returns the full spike pool, any status: the D15 filters (creator/topic/date/
status) and the convergence sort are applied client-side in ``web/`` (the same discipline as the
dashboard's ``FilterBar`` — see ``lib/dashboard/filters.ts``), not as query params here. It falls
back to the same seed spikes ``app.dashboard.seed_work_state`` already builds for the dashboard's
"Spikes & Vault" tab, so the two surfaces never show diverging placeholder data.

``POST /api/spikes/{id}/pick`` is the use-case-C hand-off (wireframe screen 6, steps 1-2): pick a
spike, create its Piece at stage ``interviewing`` (Oracle already scaffolds pieces there — this
mirrors that), AND open its first Interview — all in one all-or-nothing call
(cmw-piece-interviewing-without-interview). Before this, piece-creation and interview-creation
were two separate steps (this endpoint, then a later ``POST /api/pieces/{id}/interviews`` "generate
link" click from ``spike-kickoff.tsx``) — a piece that never got its link generated sat in
``interviewing`` with zero Interviews to conduct, a state genuinely indistinguishable (from the
stage alone) from a healthy in-progress one. The spike's own ``creator``/``origin`` attribution is
untouched; ownership is attribution, not a lock (D15). ``POST /api/pieces/{id}/interviews`` still
exists and is still reachable from the kickoff screen — it now serves two narrower, still-real
purposes: opening a second/later Interview on an already-interviewing piece (D16a, multiple
experts over time) and manually recovering a piece that reached this broken state before this fix
shipped (see that ticket's PR description for the two known-affected pieces).
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Request, Query

from app.dashboard import seed_work_state
from app.interview.engine import InterviewEngine, UnknownPersona
from app.models.piece import Piece, PieceStage
from app.models.spike import Spike, SpikeOrigin, SpikeOriginKind, SpikeStatus
from app.repositories import WorkStateStore
from app.schemas import (
    DistributionIntentOut,
    MintSpikeFromNarrativeRequest,
    PickSpikeRequest,
    PickSpikeResponse,
    SpikeListResponse,
    SpikeOriginOut,
    SpikeOut,
)

router = APIRouter(prefix="/api/spikes", tags=["spikes"])

# A spike already promoted (picked / in-flight) is no longer eligible to be re-picked into a
# second piece — pick is a one-way, use-case-C hand-off.
_PICKABLE_STATUSES = frozenset({SpikeStatus.proposed, SpikeStatus.vaulted})


def spike_to_out(spike: Spike) -> SpikeOut:
    assert spike.id is not None
    return SpikeOut(
        id=spike.id,
        headline=spike.headline,
        status=str(spike.status),
        convergence_score=spike.convergence_score,
        creator=spike.creator,
        # `SpikeOrigin` is a plain nested BaseModel (not a MongoModel), so the outer Spike's
        # `use_enum_values` config does NOT cascade into it (Pydantic v2 only converts enums on
        # the model they're declared directly on) — `spike.origin.kind` is a real SpikeOriginKind
        # instance here, and `str(...)` on a str-mixin Enum gives "SpikeOriginKind.oracle_run", not
        # its value. Use `.value` explicitly.
        origin=SpikeOriginOut(kind=spike.origin.kind.value, ref=spike.origin.ref),
        source_ids=list(spike.source_ids),
        customer_partner=spike.customer_partner,
        outcome_metric=spike.outcome_metric,
        rank_rationale=spike.rank_rationale,
        convergence_note=spike.convergence_note,
        intent=(
            DistributionIntentOut(audience=spike.intent.audience, angle=spike.intent.angle)
            if spike.intent is not None
            else None
        ),
        piece_id=spike.piece_id,
        updated_at=spike.updated_at,
    )


def _slugify(headline: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", headline.lower()).strip("-")
    return slug or "spike"


def _filter_spikes_by_origin(spikes: list[Spike], origin_ref: str | None, origin_kind: str | None) -> list[Spike]:
    """Filter spikes by origin.ref and/or origin.kind."""
    filtered = spikes
    if origin_ref is not None:
        filtered = [s for s in filtered if s.origin.ref == origin_ref]
    if origin_kind is not None:
        filtered = [s for s in filtered if s.origin.kind.value == origin_kind]
    return filtered


def _require_store(request: Request) -> WorkStateStore:
    store = getattr(request.app.state, "work_state", None)
    if store is None:
        raise HTTPException(
            status_code=503, detail="spikes unavailable (MONGO_URL not configured)"
        )
    return store


def _require_engine(request: Request) -> InterviewEngine:
    engine = getattr(request.app.state, "interview_engine", None)
    if engine is None:
        raise HTTPException(
            status_code=503, detail="pick unavailable (interview engine not configured)"
        )
    return engine


@router.get("", response_model=SpikeListResponse)
async def list_spikes(
    request: Request,
    origin_ref: str | None = Query(None, description="Filter by origin.ref"),
    origin_kind: str | None = Query(None, description="Filter by origin.kind"),
) -> SpikeListResponse:
    """The Spikes & Vault table (screen 5): real work-state when populated, else the dashboard's
    seed spikes. Optionally filter by origin."""
    store = getattr(request.app.state, "work_state", None)
    if store is not None:
        stored = await store.spikes.find({})
        if stored:
            filtered = _filter_spikes_by_origin(stored, origin_ref, origin_kind)
            return SpikeListResponse(source="store", items=[spike_to_out(s) for s in filtered])
    seed = seed_work_state().spikes
    filtered = _filter_spikes_by_origin(seed, origin_ref, origin_kind)
    return SpikeListResponse(source="seed", items=[spike_to_out(s) for s in filtered])


@router.get("/{spike_id}", response_model=SpikeOut)
async def get_spike(spike_id: str, request: Request) -> SpikeOut:
    """One spike (the kickoff screen's starting point, screen 6 step 1). Same store-or-seed
    fallback as ``list_spikes``, so a spike card's link target always resolves — the seed's
    deterministic headline-slug-derived ids match across independent calls."""
    store = getattr(request.app.state, "work_state", None)
    if store is not None:
        spike = await store.spikes.get(spike_id)
        if spike is not None:
            return spike_to_out(spike)
    for seed_spike in seed_work_state().spikes:
        if seed_spike.id == spike_id:
            return spike_to_out(seed_spike)
    raise HTTPException(status_code=404, detail=f"no spike {spike_id!r}")


@router.post("/from-narrative", response_model=SpikeOut, status_code=201)
async def mint_spike_from_narrative(
    req: MintSpikeFromNarrativeRequest, request: Request
) -> SpikeOut:
    """The "new piece from my own idea" fast path (Option B, cmw-narrative-first-entry-point):
    mint a Spike directly from a Narrative, with no Oracle ranking run and no ranked-spikes
    review table hop — the caller goes straight from this call to `POST /{id}/pick`. See
    `MintSpikeFromNarrativeRequest`'s docstring for why the Spike itself is non-negotiable even
    on this shortened path."""
    store = _require_store(request)
    narrative = await store.narratives.get(req.narrative_id)
    if narrative is None:
        raise HTTPException(status_code=404, detail=f"no narrative {req.narrative_id!r}")
    assert narrative.id is not None

    spike = Spike(
        headline=req.headline,
        status=SpikeStatus.proposed,
        creator=req.creator or narrative.author,
        origin=SpikeOrigin(kind=SpikeOriginKind.narrative, ref=narrative.id),
        intent=narrative.intent,
    )
    stored = await store.spikes.insert(spike)
    return spike_to_out(stored)


@router.post("/{spike_id}/pick", response_model=PickSpikeResponse, status_code=201)
async def pick_spike(spike_id: str, req: PickSpikeRequest, request: Request) -> PickSpikeResponse:
    """Pick a spike -> create its Piece (stage=interviewing) AND open its first Interview, in one
    all-or-nothing call — carrying the spike's audience/angle intent forward (§5-Q5). Rejects
    re-picking an already-picked/in-flight spike (409) — pick is a one-way hand-off, not an edit.

    Every field needed to open the Interview is validated (non-empty, real persona names) BEFORE
    the Piece is written, so a bad request never leaves a half-created piece behind — the exact
    defect this endpoint exists to prevent (cmw-piece-interviewing-without-interview).
    """
    store = _require_store(request)
    engine = _require_engine(request)
    spike = await store.spikes.get(spike_id)
    if spike is None:
        raise HTTPException(status_code=404, detail=f"no spike {spike_id!r}")
    if SpikeStatus(spike.status) not in _PICKABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"spike {spike_id!r} is already {spike.status!r} — cannot re-pick",
        )
    if not req.interviewer_personas:
        raise HTTPException(
            status_code=422, detail="pick requires at least one interviewer persona"
        )
    if engine.brain is None:
        raise HTTPException(
            status_code=503, detail="pick unavailable (brain not configured)"
        )
    known_personas = set(engine.brain.list_personas("interviewer"))
    unknown = [p for p in req.interviewer_personas if p not in known_personas]
    if unknown:
        raise HTTPException(
            status_code=422, detail=f"unknown interviewer persona(s): {', '.join(unknown)}"
        )

    piece = Piece(
        slug=req.slug or _slugify(spike.headline),
        voice=req.voice,
        title=req.title or spike.headline,
        origin_spike_id=spike.id,
        target=req.target,
        stage=PieceStage.interviewing,
        owner=req.owner,
        intent=spike.intent,
    )
    stored_piece = await store.pieces.insert(piece)
    assert stored_piece.id is not None

    try:
        interview = await engine.open_interview(
            stored_piece.id,
            interviewer_personas=req.interviewer_personas,
            assigned_expert=req.assigned_expert,
            about=req.about or spike.headline,
        )
    except UnknownPersona as exc:
        # Every name was already validated above — this can only mean a genuine race (the
        # roster changed mid-request). Undo the piece rather than leave it dangling: a piece must
        # never sit in `interviewing` with no Interview to conduct.
        await store.pieces.delete(stored_piece.id)
        raise HTTPException(
            status_code=422, detail=f"unknown interviewer persona: {exc}"
        ) from exc
    assert interview.id is not None

    updated_spike = await store.spikes.update(
        spike_id, {"status": SpikeStatus.picked, "piece_id": stored_piece.id}
    )
    assert updated_spike is not None

    return PickSpikeResponse(
        piece_id=stored_piece.id,
        slug=stored_piece.slug,
        spike=spike_to_out(updated_spike),
        interview_id=interview.id,
    )
