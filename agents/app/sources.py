"""Source registry (Item 6 / D8): manage what the Oracle reads.

REST surface over the ``Source`` work-state collection (``app/models/source.py``,
``WorkStateStore.sources``) — the CRUD counterpart to the connectors' on-demand refresh + clip-in
(``app/connectors/routes.py``). This module owns list/create/edit/enable-disable/retire; it never
reimplements ingest or refresh, which stay in ``app/connectors``.

``GET /api/sources`` follows the same store-vs-seed convention as ``app/dashboard.py``: real Mongo
work-state when populated, else built-in seed rows (mirroring the wireframe's example registry) so
the screen is browsable before an admin has added anything. Writes always require a configured
store (503 otherwise, matching ``app/connectors/routes.py``) since there is nowhere durable to put
them without one.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request
from pydantic import ValidationError

from app.models.common import utcnow
from app.models.source import Source, SourceClassification, SourceKind
from app.repositories import WorkStateStore
from app.schemas import (
    SourceCreateRequest,
    SourceDeleteResponse,
    SourceListResponse,
    SourceOut,
    SourceUpdateRequest,
)

router = APIRouter(prefix="/api/sources", tags=["sources"])


def source_to_out(source: Source) -> SourceOut:
    assert source.id is not None
    return SourceOut(
        id=source.id,
        display_name=source.display_name,
        kind=str(source.kind),
        classification=str(source.classification),
        enabled=source.enabled,
        lookback_default_days=source.lookback_default_days,
        config=source.config,
        owner=source.owner,
        last_refreshed=source.last_refreshed,
    )


def seed_sources() -> list[Source]:
    """Built-in example registry mirroring the wireframe (screen 7): three Green connectors plus
    the credential-free LinkedIn/X clip-in source. Gmail is deliberately absent — it is deferred
    (§9) and not a real connector kind, so the UI renders it as a static, non-manageable row."""
    now = utcnow()
    return [
        Source(
            id="seed-gdrive",
            display_name="Call & webinar transcripts",
            kind=SourceKind.gdrive,
            classification=SourceClassification.scraped_periodically,
            config={"folder_ids": ["1AbCdEfGhIjK", "1LmNoPqRsTuV", "1WxYzAbCdEfG"]},
            owner="owner@example.com",
            last_refreshed=now - timedelta(hours=2),
        ),
        Source(
            id="seed-slack",
            display_name="Team workspace Slack",
            kind=SourceKind.slack,
            classification=SourceClassification.scraped_periodically,
            config={"channel_ids": ["#partner-eng", "#product", "#wins"]},
            last_refreshed=now - timedelta(hours=2),
        ),
        Source(
            id="seed-web-rss",
            display_name="Industry blogs / RSS",
            kind=SourceKind.web_rss,
            classification=SourceClassification.scraped_periodically,
            config={"feed_urls": [f"https://example.com/feed-{n}.xml" for n in range(1, 8)]},
            last_refreshed=now - timedelta(days=1),
        ),
        Source(
            id="seed-linkedin-x",
            display_name="LinkedIn / X clips",
            kind=SourceKind.linkedin_x_clip,
            classification=SourceClassification.read_as_needed,
            config={},
        ),
    ]


def _require_store(request: Request) -> WorkStateStore:
    store = getattr(request.app.state, "work_state", None)
    if store is None:
        raise HTTPException(
            status_code=503, detail="source registry unavailable (MONGO_URL not configured)"
        )
    return store


@router.get("", response_model=SourceListResponse)
async def list_sources(request: Request) -> SourceListResponse:
    """The registry table (screen 7): real work-state when populated, else seed rows."""
    store = getattr(request.app.state, "work_state", None)
    if store is not None:
        stored = await store.sources.find({})
        if stored:
            return SourceListResponse(source="store", items=[source_to_out(s) for s in stored])
    return SourceListResponse(source="seed", items=[source_to_out(s) for s in seed_sources()])


@router.post("", response_model=SourceOut, status_code=201)
async def create_source(req: SourceCreateRequest, request: Request) -> SourceOut:
    """Add a Green connector or the LinkedIn/X clip-in source. This form sets WHAT to read —
    credentials are provisioned server-side by an admin and never accepted here (D14)."""
    store = _require_store(request)
    try:
        source = Source(
            display_name=req.display_name,
            kind=SourceKind(req.kind),
            classification=SourceClassification(req.classification),
            lookback_default_days=req.lookback_default_days,
            config=req.config,
            owner=req.owner,
        )
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    stored = await store.sources.insert(source)
    return source_to_out(stored)


@router.patch("/{source_id}", response_model=SourceOut)
async def update_source(source_id: str, req: SourceUpdateRequest, request: Request) -> SourceOut:
    """Edit a source: display name, classification, enable/disable, lookback window, or config.

    Re-validates the FULL merged document (not a raw ``$set``) so the credential-free-config and
    linkedin-is-always-read-as-needed invariants (``app/models/source.py``) hold on every edit, not
    just at creation.
    """
    store = _require_store(request)
    existing = await store.sources.get(source_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"no source {source_id!r}")
    changes = req.model_dump(exclude_unset=True)
    merged = existing.model_dump(by_alias=False)
    merged.update(changes)
    try:
        updated = Source.model_validate(merged)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    stored = await store.sources.replace(updated)
    return source_to_out(stored)


@router.delete("/{source_id}", response_model=SourceDeleteResponse)
async def retire_source(source_id: str, request: Request) -> SourceDeleteResponse:
    """Retire a source: it stops being read entirely (distinct from the enable/disable toggle)."""
    store = _require_store(request)
    deleted = await store.sources.delete(source_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"no source {source_id!r}")
    return SourceDeleteResponse(id=source_id, deleted=True)
