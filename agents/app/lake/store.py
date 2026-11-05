"""``ContentLake`` — the ingest + query facade over the lake (D9).

This is the single, connector-agnostic seam the rest of the system uses:

- **Ingest** (``ingest`` / ``ingest_many``): the push / on-refresh entrypoint the *connectors*
  ticket will call. A connector builds a ``ContentLakeItem`` from whatever it pulled and hands it
  over; the lake populates the hybrid index **on ingest** (embedding + keyword tokens), defaults
  the recency date, writes it, and returns the stored item. It never inspects the content as an
  instruction and it never deletes.
- **Query** (``query``): the on-demand hybrid query the *Oracle*, *research sidecar*, and
  *drafting* will call. Delegates to the configured ``HybridIndex`` (local or Atlas) and returns
  ranked candidates, capped at ``top_k`` — rank-and-retrieve, never the whole lake.

No connectors and no Oracle logic live here — only the lake, its index, and this API. Those tickets
plug into these two methods.
"""

from __future__ import annotations

from typing import Any

from app.config import Settings, get_settings
from app.lake.embeddings import Embedder, get_embedder, tokenize
from app.lake.index import HybridIndex, build_index
from app.lake.models import ContentLakeItem
from app.lake.query import LakeQuery, RankedCandidate
from app.lake.repository import ContentLakeRepository
from app.models.common import utcnow


class ContentLake:
    """Ingest + hybrid-query facade. Construct via ``build_content_lake`` (or inject parts)."""

    def __init__(
        self,
        repo: ContentLakeRepository,
        embedder: Embedder,
        index: HybridIndex,
    ) -> None:
        self.repo = repo
        self.embedder = embedder
        self.index = index

    # --- ingest ----------------------------------------------------------------------------

    async def ingest(self, item: ContentLakeItem) -> ContentLakeItem:
        """Write a raw item and index it **on ingest**. Returns the stored, indexed item.

        Populates the two computed index legs (semantic embedding + keyword tokens) and defaults
        ``metadata.content_date`` to ingest time so every item is windowable. The structured
        metadata is already native document fields, so it needs no separate indexing step.
        """
        if item.metadata.content_date is None:
            item.metadata.content_date = utcnow()
        # Index on ingest: both computed legs are derived from the raw content.
        item.keyword_tokens = tokenize(item.raw_content)
        item.embedding = self.embedder.embed([item.raw_content])[0]
        return await self.repo.insert(item)

    async def ingest_many(self, items: list[ContentLakeItem]) -> list[ContentLakeItem]:
        """Convenience for on-refresh batch pulls. Each item is indexed independently."""
        return [await self.ingest(item) for item in items]

    # --- query -----------------------------------------------------------------------------

    async def query(self, query: LakeQuery) -> list[RankedCandidate]:
        """Run an on-demand hybrid query; return ranked candidates (top_k capped)."""
        return await self.index.search(query)

    # --- reads (no delete — §1.4 "nothing is ever deleted") --------------------------------

    async def get(self, item_id: str) -> ContentLakeItem | None:
        return await self.repo.get(item_id)

    async def find_by_external_id(
        self, source_id: str, external_id: str | None
    ) -> ContentLakeItem | None:
        """Look up an already-ingested item by its origin ``source_id`` + stable ``external_id``.

        Lets an on-demand connector refresh be **idempotent**: a connector carries a per-source
        stable id (Drive file id, Slack ``ts``, RSS ``guid``) in ``metadata.extra.external_id`` so a
        repeat refresh can skip material already in the lake rather than duplicating it. This is a
        plain metadata read — it neither re-indexes nor deletes (§1.4). Returns ``None`` when
        ``external_id`` is unknown, so connectors that cannot supply one simply always ingest.
        """
        if not external_id:
            return None
        return await self.repo.find_one(
            {"source_id": source_id, "metadata.extra.external_id": external_id}
        )

    async def count(self, query_filter: dict[str, Any] | None = None) -> int:
        return await self.repo.count(query_filter)


def build_content_lake(database: Any, settings: Settings | None = None) -> ContentLake:
    """Wire a ``ContentLake`` from a Mongo database handle + server-side settings.

    The database is the **same** instance that backs work-state (§7); we only add the
    ``content_lake`` collection. Embedder and index backends are config-selected so local dev /
    tests use the dependency-free defaults and production flips to a real embedder + Atlas.
    """
    settings = settings or get_settings()
    repo = ContentLakeRepository(database)
    embedder = get_embedder(settings.embedding_backend, dim=settings.embedding_dim)
    index = build_index(settings.lake_index_backend, repo, embedder)
    return ContentLake(repo, embedder, index)
