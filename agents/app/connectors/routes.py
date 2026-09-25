"""HTTP surface for the source connectors (D8) — on-demand refresh + clip-in over REST.

Thin wrappers over the connector services so the Next.js BFF (and any operator action) can drive
them over the service's REST boundary:

- ``POST /api/connectors/refresh`` — the on-demand "refresh sources" entrypoint (D7). Pulls from
  the enabled Green-connector sources into the lake. No scheduler.
- ``POST /api/connectors/clip`` — the credential-free LinkedIn/X clip-in path (D8).

Both need the work-state store (the Source registry) and the content lake; when Mongo is not
configured they report 503, mirroring the lake routes. Credentials are read server-side (from
``Settings`` via the connector factory) and never touched here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.connectors.clipin import ClipInError, ClipInService
from app.connectors.refresh import SourceRefreshService, build_connectors
from app.lake.store import ContentLake
from app.repositories import WorkStateStore
from app.schemas import (
    ClipInRequest,
    ClipInResponse,
    RefreshRequest,
    RefreshResponse,
    RefreshResultOut,
)

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


def _require(request: Request) -> tuple[WorkStateStore, ContentLake]:
    """Resolve the work-state store + lake from app state, or 503 if Mongo is unconfigured."""
    store = getattr(request.app.state, "work_state", None)
    lake = getattr(request.app.state, "content_lake", None)
    if store is None or lake is None:
        raise HTTPException(
            status_code=503,
            detail="connectors unavailable (MONGO_URL not configured)",
        )
    return store, lake


Deps = Annotated[tuple[WorkStateStore, ContentLake], Depends(_require)]


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(req: RefreshRequest, deps: Deps, request: Request) -> RefreshResponse:
    """On-demand refresh of Green-connector sources into the lake (D7 — runs only when asked)."""
    store, lake = deps
    # Connectors (with their server-side clients) are wired once in the lifespan; fall back to
    # building them on demand so the route is robust even if the lifespan seam was skipped.
    connectors = getattr(request.app.state, "connectors", None) or build_connectors()
    service = SourceRefreshService(store, lake, connectors)
    results = await service.refresh(
        source_id=req.source_id, kinds=req.kinds, lookback_days=req.lookback_days
    )
    return RefreshResponse(
        refreshed=[
            RefreshResultOut(
                source_id=r.source_id,
                kind=r.kind,
                ingested=r.ingested,
                skipped=r.skipped,
                error=r.error,
            )
            for r in results
        ]
    )


@router.post("/clip", response_model=ClipInResponse)
async def clip(req: ClipInRequest, deps: Deps) -> ClipInResponse:
    """Credential-free LinkedIn/X clip-in: write pasted material to the lake as read-as-needed."""
    store, lake = deps
    service = ClipInService(store, lake)
    try:
        item = await service.clip_in(
            source_id=req.source_id,
            content=req.content,
            url=req.url,
            author=req.author,
            content_date=req.content_date,
            tags=req.tags,
            title=req.title,
        )
    except ClipInError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    assert item.id is not None
    return ClipInResponse(id=item.id, classification=str(item.classification), indexed=True)
