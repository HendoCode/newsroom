"""Hybrid index — the three retrieval legs over the lake (D9), behind one query surface.

Two interchangeable implementations of the same ``HybridIndex.search`` contract:

- ``LocalHybridIndex`` — the **working local fallback**. Runs against plain community MongoDB
  (``mongo:7`` in compose) and the in-memory test double: a native ``$match`` handles the
  structured-metadata + recency pre-filter, then semantic (cosine over the stored embedding) and
  keyword (token overlap) scores are computed in Python and blended. This is the default.
- ``AtlasHybridIndex`` — the **production wiring**. Pushes the same query down to Atlas Vector
  Search (``$vectorSearch``) + Atlas Search (``$search``) with native metadata filters, and fuses
  the two rankings. Selected by config (``lake_index_backend="atlas"``); requires the Atlas index
  definitions in ``app/lake/README.md``.

Both return ``list[RankedCandidate]`` for an identical ``LakeQuery``, so moving from local to Atlas
is a config change, not a rewrite. See ``README.md`` for the exact behavioural differences.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.lake.embeddings import Embedder, cosine, tokenize
from app.lake.query import LakeQuery, RankedCandidate
from app.lake.repository import ContentLakeRepository


class HybridIndex(Protocol):
    """The query surface every consumer (Oracle, research sidecar, drafting) depends on."""

    async def search(self, query: LakeQuery) -> list[RankedCandidate]: ...


def _keyword_score(query_tokens: set[str], doc_tokens: list[str]) -> float:
    """Fraction of distinct query terms present in the document, in ``[0, 1]``.

    A deliberately simple full-text signal — enough to rank locally and to test the keyword leg in
    isolation. Atlas Search replaces it with proper BM25 scoring over a text index (see README).
    """
    if not query_tokens:
        return 0.0
    matched = query_tokens.intersection(doc_tokens)
    return len(matched) / len(query_tokens)


def _blend(query: LakeQuery, semantic: float, keyword: float) -> float:
    return query.semantic_weight * semantic + query.keyword_weight * keyword


class LocalHybridIndex:
    """Working hybrid search over plain MongoDB — metadata/recency in Mongo, ranking in Python."""

    def __init__(self, repo: ContentLakeRepository, embedder: Embedder) -> None:
        self._repo = repo
        self._embedder = embedder

    async def search(self, query: LakeQuery) -> list[RankedCandidate]:
        candidates = await self._repo.candidates(query)

        # No text query → pure structured-metadata / recency browse, already recency-sorted.
        if not query.has_text_query():
            return [
                RankedCandidate(item=item, score=0.0, semantic_score=0.0, keyword_score=0.0)
                for item in candidates[: query.top_k]
            ]

        assert query.text is not None
        query_embedding = self._embedder.embed([query.text])[0]
        query_tokens = set(tokenize(query.text))

        ranked: list[RankedCandidate] = []
        for item in candidates:
            semantic = 0.0
            if item.embedding and query.semantic_weight:
                # relu: an anti-correlated (negative-cosine) item is "no match", not a penalty.
                semantic = max(0.0, cosine(query_embedding, item.embedding))
            keyword = _keyword_score(query_tokens, item.keyword_tokens) if query.keyword_weight else 0.0
            score = _blend(query, semantic, keyword)
            if score <= 0.0:
                continue  # nothing matched this leg → not a candidate (never send the whole lake)
            ranked.append(
                RankedCandidate(
                    item=item, score=score, semantic_score=semantic, keyword_score=keyword
                )
            )

        # Stable sort by score desc; candidates arrived recency-desc, so ties keep newest-first.
        ranked.sort(key=lambda c: c.score, reverse=True)
        return ranked[: query.top_k]


class AtlasHybridIndex:
    """Production hybrid search pushed down to Atlas Vector Search + Atlas Search.

    Exercised only against a real Atlas cluster (Vector Search / Search are unavailable on the
    local ``mongo:7`` and the in-memory test double), so it is **not** covered by the local pytest
    suite — the ``LocalHybridIndex`` is. It is included so production is a config flip. It runs two
    Atlas aggregations (vector + full-text), each with the same metadata/recency pre-filter, and
    fuses them with reciprocal rank fusion (RRF) — MongoDB's documented hybrid-search pattern.

    Requires two Atlas indexes on the ``content_lake`` collection (definitions in README.md):
    a ``vector`` index on ``embedding`` and an Atlas Search index over ``raw_content`` + metadata.
    """

    # RRF constant (MongoDB's documented default); dampens the weight of low-ranked hits.
    _RRF_K = 60

    def __init__(
        self,
        repo: ContentLakeRepository,
        embedder: Embedder,
        *,
        vector_index: str = "content_lake_vector",
        search_index: str = "content_lake_search",
    ) -> None:
        self._repo = repo
        self._embedder = embedder
        self._vector_index = vector_index
        self._search_index = search_index

    def _atlas_filter(self, query: LakeQuery) -> dict[str, Any]:
        """The metadata/recency pre-filter, reusing the exact local filter builder for parity."""
        return ContentLakeRepository.build_filter(query)

    def _vector_pipeline(self, query: LakeQuery, embedding: list[float]) -> list[dict[str, Any]]:
        num_candidates = max(query.top_k * 10, 100)
        stage: dict[str, Any] = {
            "index": self._vector_index,
            "path": "embedding",
            "queryVector": embedding,
            "numCandidates": num_candidates,
            "limit": query.top_k,
        }
        filt = self._atlas_filter(query)
        if filt:
            stage["filter"] = filt
        return [{"$vectorSearch": stage}, {"$project": {"_score": {"$meta": "vectorSearchScore"}}}]

    def _search_pipeline(self, query: LakeQuery) -> list[dict[str, Any]]:
        assert query.text is not None
        compound: dict[str, Any] = {
            "must": [{"text": {"query": query.text, "path": "raw_content"}}]
        }
        filt = self._atlas_filter(query)
        if filt:
            compound["filter"] = [filt]
        return [
            {"$search": {"index": self._search_index, "compound": compound}},
            {"$limit": query.top_k},
            {"$project": {"_score": {"$meta": "searchScore"}}},
        ]

    async def _run(self, pipeline: list[dict[str, Any]]) -> list[str]:
        cursor = self._repo.collection.aggregate(pipeline)
        return [doc["_id"] async for doc in cursor]

    async def search(self, query: LakeQuery) -> list[RankedCandidate]:
        if not query.has_text_query():
            # No ranking signal → same recency browse as local, via the shared repo path.
            candidates = await self._repo.candidates(query)
            return [
                RankedCandidate(item=item, score=0.0, semantic_score=0.0, keyword_score=0.0)
                for item in candidates[: query.top_k]
            ]

        assert query.text is not None
        embedding = self._embedder.embed([query.text])[0]
        vector_ids = await self._run(self._vector_pipeline(query, embedding)) if query.semantic_weight else []
        search_ids = await self._run(self._search_pipeline(query)) if query.keyword_weight else []

        # Reciprocal rank fusion of the two rankings, weighted by the query's leg weights.
        fused: dict[str, float] = {}
        sem_rank: dict[str, int] = {}
        kw_rank: dict[str, int] = {}
        for rank, _id in enumerate(vector_ids):
            sem_rank[_id] = rank
            fused[_id] = fused.get(_id, 0.0) + query.semantic_weight / (self._RRF_K + rank + 1)
        for rank, _id in enumerate(search_ids):
            kw_rank[_id] = rank
            fused[_id] = fused.get(_id, 0.0) + query.keyword_weight / (self._RRF_K + rank + 1)

        ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)[: query.top_k]
        out: list[RankedCandidate] = []
        for _id, score in ordered:
            item = await self._repo.get(_id)
            if item is None:  # pragma: no cover — indexed doc vanished between passes
                continue
            # Surface each leg's presence as a normalized [0,1] rank signal for callers/tests.
            semantic = 1.0 / (sem_rank[_id] + 1) if _id in sem_rank else 0.0
            keyword = 1.0 / (kw_rank[_id] + 1) if _id in kw_rank else 0.0
            out.append(
                RankedCandidate(item=item, score=score, semantic_score=semantic, keyword_score=keyword)
            )
        return out


def build_index(
    backend: str, repo: ContentLakeRepository, embedder: Embedder
) -> HybridIndex:
    """Construct the configured hybrid index. ``local`` (default) or ``atlas`` (production)."""
    normalized = backend.lower()
    if normalized == "local":
        return LocalHybridIndex(repo, embedder)
    if normalized == "atlas":
        return AtlasHybridIndex(repo, embedder)
    raise ValueError(f"unknown lake index backend {backend!r} (expected 'local' or 'atlas')")
