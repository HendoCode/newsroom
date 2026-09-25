"""Content-lake Mongo repository (§3 "Mongo content lake", D9).

A thin ``BaseRepository`` subclass — the lake reuses the exact work-state persistence patterns
(string ``_id``, managed timestamps, driver-agnostic CRUD) against the *same* Mongo instance
(§7). It adds only what the hybrid query needs: a structured-metadata + recency pre-filter builder
and a candidate fetch.

The one deliberate divergence from the base: **deletes are refused.** §1.4's invariant is
"nothing is ever deleted" (parity with "nothing is thrown away"), so overriding ``delete`` to
raise makes that invariant load-bearing rather than a comment.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.lake.models import ContentLakeItem
from app.lake.query import LakeQuery
from app.models.common import utcnow
from app.repositories.base import BaseRepository, mongo_encode


class ContentLakeRepository(BaseRepository[ContentLakeItem]):
    model = ContentLakeItem
    collection_name = "content_lake"

    async def delete(self, id: str) -> bool:
        """Refused by design: the content lake never deletes (§1.4, "nothing is thrown away")."""
        raise NotImplementedError(
            "content-lake items are never deleted (§1.4 'nothing is ever deleted')"
        )

    @staticmethod
    def build_filter(query: LakeQuery) -> dict[str, Any]:
        """Translate a ``LakeQuery`` into a native Mongo filter for the hard pre-filter legs.

        Only the structured-metadata + recency legs live here; semantic/keyword ranking is applied
        after the candidate fetch (locally) or pushed into the Atlas pipeline (production). Keeping
        the filter builder identical for both backends means the metadata/recency semantics never
        diverge between local and Atlas.
        """
        clauses: list[dict[str, Any]] = []
        if query.source_ids:
            clauses.append({"source_id": {"$in": list(query.source_ids)}})
        if query.authors:
            clauses.append({"metadata.author": {"$in": list(query.authors)}})
        if query.tags:
            clauses.append({"metadata.tags": {"$in": list(query.tags)}})
        if query.classification is not None:
            clauses.append({"classification": mongo_encode(query.classification)})
        if query.lookback_days is not None:
            cutoff = utcnow() - timedelta(days=query.lookback_days)
            clauses.append({"metadata.content_date": {"$gte": cutoff}})
        if not clauses:
            return {}
        return {"$and": clauses} if len(clauses) > 1 else clauses[0]

    async def candidates(self, query: LakeQuery) -> list[ContentLakeItem]:
        """Fetch the items that survive the metadata + recency pre-filter, newest first.

        Newest-first ordering makes an empty-text query a recency browse for free, and gives the
        local ranker a deterministic, recency-biased tie-break among equal scores.
        """
        return await self.find(
            self.build_filter(query), sort=[("metadata.content_date", -1)]
        )
