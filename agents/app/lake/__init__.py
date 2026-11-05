"""Content lake + hybrid index (domain model §1.4, §3; design D9).

The single ingest target for all raw material, with a hybrid index (semantic embedding +
keyword/full-text + structured metadata) queried on demand. A single Mongo instance backs both
this lake and the work-state store (§7), so the lake reuses the work-state Mongo patterns
(``MongoModel`` + ``BaseRepository``).

Public surface:
- ``ContentLakeItem`` / ``ContentMetadata`` — the ingested-item model and its metadata leg.
- ``ContentLake`` + ``build_content_lake`` — the ingest + hybrid-query facade (the seam the
  connectors, Oracle, research sidecar, and drafting tickets plug into).
- ``LakeQuery`` / ``RankedCandidate`` — the query request + ranked-result contract.

No connectors and no Oracle logic live here — lake + index + ingest/query API only.
"""

from __future__ import annotations

from app.lake.embeddings import Embedder, HashingEmbedder, cosine, get_embedder, tokenize
from app.lake.index import (
    AtlasHybridIndex,
    HybridIndex,
    LocalHybridIndex,
    build_index,
)
from app.lake.models import ContentLakeItem, ContentMetadata
from app.lake.query import LakeQuery, RankedCandidate
from app.lake.repository import ContentLakeRepository
from app.lake.store import ContentLake, build_content_lake

__all__ = [
    "AtlasHybridIndex",
    "ContentLake",
    "ContentLakeItem",
    "ContentLakeRepository",
    "ContentMetadata",
    "Embedder",
    "HashingEmbedder",
    "HybridIndex",
    "LakeQuery",
    "LocalHybridIndex",
    "RankedCandidate",
    "build_content_lake",
    "build_index",
    "cosine",
    "get_embedder",
    "tokenize",
]
