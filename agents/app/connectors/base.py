"""Source-connector base contract (D8, domain model §1.3/§1.4).

A **connector** turns one Source-registry entry into content-lake items: it *pulls* raw material
from an external system and *writes* it to the lake via the lake's ingest API. That is the whole
job — indexing is the lake's concern (D9), and ranking/Oracle logic lives in a separate ticket.

The contract is split into two seams so the network-touching part is trivially testable:

- ``fetch`` (abstract, per connector) — pull ``RawItem``s from the external system, given the
  Source's kind-specific ``config`` and a lookback window. Connectors take their external client
  by constructor injection, so tests pass a fake client and never touch the network.
- ``refresh`` (concrete, shared) — the on-demand entrypoint: call ``fetch``, map each ``RawItem``
  to a ``ContentLakeItem`` (classification **inherited from the Source**, §1.4), skip anything
  already ingested (idempotent re-refresh via ``external_id``), and ingest the rest through the
  lake facade. No connector reimplements this loop.

There is **no scheduler** (D7/§9): ``refresh`` runs only when a human/Oracle asks.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

from app.lake.models import ContentLakeItem, ContentMetadata
from app.lake.store import ContentLake
from app.models.source import Source, SourceKind


@dataclass
class RawItem:
    """One unit a connector pulled, before it becomes a ``ContentLakeItem``.

    Deliberately connector-agnostic: raw content plus whatever metadata the source could supply.
    ``external_id`` is the source's own stable id for this unit (Drive file id, Slack message
    ``ts``, RSS ``guid``) — it powers idempotent re-refresh and is never interpreted as content.
    """

    raw_content: str
    external_id: str | None = None
    content_date: datetime | None = None
    author: str | None = None
    title: str | None = None
    url: str | None = None
    tags: list[str] = field(default_factory=list)
    # Connector-specific provenance (channel id, folder id, mime type…) — carried, not interpreted.
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RefreshResult:
    """Outcome of refreshing one Source: how many items were ingested vs skipped, or an error.

    A per-source error is *reported*, never raised past the refresh service — one failing source
    must not block the others (the "warns, does not block" principle, §5).
    """

    source_id: str
    kind: str
    ingested: int = 0
    skipped: int = 0
    item_ids: list[str] = field(default_factory=list)
    error: str | None = None


class ConnectorError(RuntimeError):
    """A connector could not pull (auth missing, upstream failure). Reported per source."""


class SourceConnector(ABC):
    """Base for every Green connector. Subclasses set ``kind`` and implement ``fetch``."""

    kind: ClassVar[SourceKind]

    async def refresh(
        self,
        source: Source,
        lake: ContentLake,
        *,
        lookback_days: int | None = None,
    ) -> RefreshResult:
        """Pull from ``source`` and write new items to ``lake``. On-demand only (no scheduler).

        The window defaults to the Source's ``lookback_default_days`` (D7). Items whose
        ``external_id`` already exists in the lake for this source are skipped, so a repeat refresh
        is idempotent rather than duplicating material.
        """
        window = lookback_days if lookback_days is not None else source.lookback_default_days
        raw_items = await self.fetch(source, lookback_days=window)

        assert source.id is not None
        ingested_ids: list[str] = []
        skipped = 0
        for raw in raw_items:
            existing = await lake.find_by_external_id(source.id, raw.external_id)
            if existing is not None:
                skipped += 1
                continue
            stored = await lake.ingest(self._to_item(source, raw))
            assert stored.id is not None
            ingested_ids.append(stored.id)

        return RefreshResult(
            source_id=source.id,
            kind=str(source.kind),
            ingested=len(ingested_ids),
            skipped=skipped,
            item_ids=ingested_ids,
        )

    def _to_item(self, source: Source, raw: RawItem) -> ContentLakeItem:
        """Map a pulled ``RawItem`` onto a ``ContentLakeItem``.

        Classification is **inherited verbatim from the origin Source** (§1.4). The stable
        ``external_id`` is stored under ``metadata.extra`` for provenance + idempotent re-refresh.
        """
        assert source.id is not None
        extra: dict[str, Any] = dict(raw.extra)
        if raw.external_id is not None:
            extra["external_id"] = raw.external_id
        return ContentLakeItem(
            raw_content=raw.raw_content,
            source_id=source.id,
            classification=source.classification,
            metadata=ContentMetadata(
                content_date=raw.content_date,
                author=raw.author,
                title=raw.title,
                url=raw.url,
                tags=raw.tags,
                extra=extra,
            ),
        )

    @abstractmethod
    async def fetch(self, source: Source, *, lookback_days: int) -> list[RawItem]:
        """Pull raw items from the external system for ``source`` within the lookback window."""
        raise NotImplementedError
