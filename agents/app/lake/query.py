"""The on-demand hybrid-query contract over the content lake (D9).

One request type (``LakeQuery``) and one ranked-result type (``RankedCandidate``) shared by every
consumer — the Oracle, the research sidecar, and drafting. The query is deliberately *narrow*:
semantic + keyword + structured-metadata filters, a recency window, and a hard ``top_k`` cap. That
cap encodes the "rank-and-retrieve, never send the whole lake" discipline — a query returns ranked
*candidates*, never the lake.

The three retrieval legs combine as: **metadata + recency are hard pre-filters** (they narrow the
candidate set); **semantic and keyword are soft scores** (they rank what survives). Setting one
score weight to 0 gives a pure single-mode query; leaving ``text`` unset makes it a pure
metadata/recency browse ranked by recency.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.lake.models import ContentLakeItem
from app.models.source import SourceClassification


class LakeQuery(BaseModel):
    """An on-demand hybrid query. All filters are optional; an empty query is a recency browse."""

    # The semantic + keyword query text. Unset → no scoring; results are ranked by recency.
    text: str | None = None

    # --- structured-metadata hard filters (native document fields) ---------------------------
    source_ids: list[str] = Field(default_factory=list)  # origin Source ids (any-of)
    authors: list[str] = Field(default_factory=list)  # metadata.author (any-of)
    tags: list[str] = Field(default_factory=list)  # metadata.tags (any-of intersection)
    classification: SourceClassification | None = None

    # --- recency window (D7) -----------------------------------------------------------------
    # Keep only items whose metadata.content_date is within the last N days. None → no window.
    lookback_days: int | None = None

    # --- ranking + cap -----------------------------------------------------------------------
    top_k: int = 10  # hard cap on returned candidates (rank-and-retrieve discipline)
    semantic_weight: float = 0.5  # weight of the embedding/cosine signal
    keyword_weight: float = 0.5  # weight of the keyword/full-text signal

    def has_text_query(self) -> bool:
        return bool(self.text and self.text.strip())


class RankedCandidate(BaseModel):
    """One ranked hit: the item plus the per-leg scores that produced its combined rank.

    Exposing the component scores (not just the blend) lets callers reason about *why* something
    ranked, and lets tests assert each retrieval leg independently.
    """

    item: ContentLakeItem
    score: float  # combined rank score
    semantic_score: float  # cosine-derived, [0, 1]
    keyword_score: float  # token-overlap-derived, [0, 1]
