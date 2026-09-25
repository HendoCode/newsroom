"""HTTP surface for the content lake (D9) — the ingest + query API over REST.

Thin wrappers over the ``ContentLake`` facade so the push/on-refresh ingest and on-demand query
are reachable over the service's REST boundary (the same boundary the Next.js BFF and any
out-of-process connector use). The facade is the real API; these routes just expose it.

The lake is attached to ``app.state.content_lake`` in the lifespan (``app.main``). When Mongo is
not configured the lake is absent and these endpoints report 503 — the service still boots.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.lake.models import ContentLakeItem, ContentMetadata
from app.lake.query import LakeQuery, RankedCandidate
from app.lake.store import ContentLake
from app.models.source import SourceClassification
from app.schemas import IngestRequest, IngestResponse

router = APIRouter(prefix="/api/lake", tags=["content-lake"])


def get_lake(request: Request) -> ContentLake:
    """Resolve the ContentLake from app state, or 503 if the lake is not configured."""
    lake = getattr(request.app.state, "content_lake", None)
    if lake is None:
        raise HTTPException(
            status_code=503,
            detail="content lake unavailable (MONGO_URL not configured)",
        )
    return lake


LakeDep = Annotated[ContentLake, Depends(get_lake)]


@router.post("/ingest", response_model=IngestResponse)
async def ingest(req: IngestRequest, lake: LakeDep) -> IngestResponse:
    """Push / on-refresh ingest: write a raw item + metadata and index it on ingest.

    Connector-agnostic — a connector supplies raw content, origin source id, the inherited
    classification, and whatever metadata it has.
    """
    item = ContentLakeItem(
        raw_content=req.raw_content,
        source_id=req.source_id,
        classification=SourceClassification(req.classification),
        metadata=ContentMetadata(**req.metadata),
    )
    stored = await lake.ingest(item)
    assert stored.id is not None
    return IngestResponse(id=stored.id, indexed=True)


@router.post("/query", response_model=list[RankedCandidate])
async def query(q: LakeQuery, lake: LakeDep) -> list[RankedCandidate]:
    """On-demand hybrid query: semantic + keyword + metadata, windowed and top-K capped."""
    return await lake.query(q)
