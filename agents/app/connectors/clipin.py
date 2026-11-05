"""LinkedIn / X manual clip-in (D8) — the credential-free ingest path.

LinkedIn and X have no clean legitimate read path, so the *only* sanctioned way material from them
enters the system is a human pasting it in (D8): there is **no fetch, no scraper, and nothing to
authenticate**. A human pastes text (and optionally a URL) plus the minimal metadata that can't be
inferred — source person/account, date, tags — and it goes straight to the content lake as a
``read-as-needed`` item.

This lives beside the Green connectors but is deliberately *not* a ``SourceConnector``: it never
pulls. It only needs a ``linkedin-x-clip`` Source (which the registry guarantees is
``read-as-needed``, credential-free) to attribute the clip to, and the lake to write to.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.lake.models import ContentLakeItem, ContentMetadata
from app.lake.store import ContentLake
from app.models.source import Source, SourceClassification, SourceKind
from app.repositories import WorkStateStore


class ClipInError(ValueError):
    """The clip target is missing or is not a linkedin-x-clip source."""


class ClipInService:
    """Write pasted LinkedIn/X material straight to the lake as a ``read-as-needed`` item."""

    def __init__(self, store: WorkStateStore, lake: ContentLake) -> None:
        self.store = store
        self.lake = lake

    async def clip_in(
        self,
        *,
        source_id: str,
        content: str,
        url: str | None = None,
        author: str | None = None,
        content_date: datetime | None = None,
        tags: list[str] | None = None,
        title: str | None = None,
    ) -> ContentLakeItem:
        """Ingest one clipped item. No auth, no fetch — just validate the target and write.

        ``source_id`` must reference a ``linkedin-x-clip`` Source (always ``read-as-needed``, D8).
        ``content`` is the pasted text (or a note about a pasted URL); ``author`` is the source
        person/account and the rest is the minimal metadata a human supplies.
        """
        if not content or not content.strip():
            raise ClipInError("clip-in content must not be empty")

        source: Source | None = await self.store.sources.get(source_id)
        if source is None:
            raise ClipInError(f"no source {source_id!r}")
        if SourceKind(source.kind) != SourceKind.linkedin_x_clip:
            raise ClipInError(
                f"clip-in requires a linkedin-x-clip source; {source_id!r} is {source.kind}"
            )

        extra: dict[str, Any] = {"clipped": True}
        item = ContentLakeItem(
            raw_content=content,
            source_id=source_id,
            # read-as-needed, always (§1.4 inherits from the source; enforced by the Source model).
            classification=SourceClassification.read_as_needed,
            metadata=ContentMetadata(
                content_date=content_date,
                author=author,
                title=title,
                url=url,
                tags=tags or [],
                extra=extra,
            ),
        )
        return await self.lake.ingest(item)
