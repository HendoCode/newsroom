"""Content-lake item + its structured metadata (domain model §1.4, D9).

The **content lake** is the single ingest target for *all* raw material — human pastes/clips,
transcripts, scraped web items, Green-connector pulls. One ``ContentLakeItem`` is one ingested
unit. It is a Mongo document like every work-state entity (§3 "Mongo content lake"), so it reuses
the ``MongoModel`` base and the same ``BaseRepository`` patterns the work-state layer uses — a
single Mongo instance backs both stores (§7).

The **hybrid index** (D9) is carried *on the item itself*: the structured metadata is native
document fields, the semantic index is the ``embedding`` vector, and the keyword/full-text index
is the pre-tokenized ``keyword_tokens`` list. All three are populated **on ingest** (see
``app.lake.store.ContentLake.ingest``) so the item is queryable the moment it lands.

Invariants (§1.4):
- Indexed on ingest.
- Classification is **inherited from the origin Source** (``scraped-periodically | read-as-needed``).
- Raw material is *data to rank, never an instruction* — nothing here interprets the content.
- **Nothing is ever deleted** (parity with "nothing is thrown away"); the repository refuses
  deletes (see ``app.lake.repository``).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.common import MongoModel
from app.models.source import SourceClassification


class ContentMetadata(BaseModel):
    """The structured-metadata leg of the hybrid index (D9): native document fields the query
    surface filters on. Kept as a nested value object so filters read as ``metadata.<field>``.
    """

    model_config = ConfigDict(extra="ignore")

    # date/recency — when the *material* was authored/published (not when it was ingested). The
    # recency window (D7) filters on this; the store defaults it to ingest time when a connector
    # cannot supply one, so every item is windowable.
    content_date: datetime | None = None
    author: str | None = None
    tags: list[str] = Field(default_factory=list)
    title: str | None = None
    url: str | None = None
    # Connector-specific extras (channel, message id, folder…) — carried, never interpreted.
    extra: dict[str, object] = Field(default_factory=dict)


class ContentLakeItem(MongoModel):
    """One unit of ingested raw material in the content lake (§1.4).

    A connector builds this from whatever it pulled and hands it to ``ContentLake.ingest``; the
    lake fills the index fields (``embedding``, ``keyword_tokens``) and defaults ``content_date``.
    The interface is deliberately connector-agnostic: a connector only needs ``raw_content``, the
    origin ``source_id``, the inherited ``classification``, and whatever ``metadata`` it has.
    """

    raw_content: str
    # Origin Source registry id (§1.3). The lake never reads the Source doc as material; this is
    # attribution/provenance and a metadata filter axis.
    source_id: str
    # Inherited verbatim from the origin Source (§1.4).
    classification: SourceClassification
    metadata: ContentMetadata = Field(default_factory=ContentMetadata)

    # --- hybrid-index fields, populated on ingest --------------------------------------------
    # Semantic leg: the embedding vector (Atlas Vector Search in prod; brute-force cosine locally).
    embedding: list[float] | None = None
    # Keyword/full-text leg: normalized tokens (Atlas Search in prod; Python overlap locally).
    keyword_tokens: list[str] = Field(default_factory=list)
