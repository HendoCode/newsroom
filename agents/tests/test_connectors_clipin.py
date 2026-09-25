"""LinkedIn/X manual clip-in tests (D8) — the credential-free path.

Proves the clip-in writes pasted material straight to the lake as ``read-as-needed`` with the
human-supplied metadata, requires a ``linkedin-x-clip`` source, and never fetches or authenticates
anything (there is no client to inject — that is the point).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.connectors import ClipInService
from app.connectors.clipin import ClipInError
from app.lake import ContentLake
from app.models.common import utcnow
from app.models.source import Source, SourceClassification, SourceKind
from app.repositories import WorkStateStore


async def _clip_source(store: WorkStateStore) -> Source:
    return await store.sources.insert(
        Source(
            display_name="LinkedIn clips",
            kind=SourceKind.linkedin_x_clip,
            classification=SourceClassification.read_as_needed,
        )
    )


async def test_clip_in_writes_read_as_needed(store: WorkStateStore, lake: ContentLake) -> None:
    source = await _clip_source(store)
    service = ClipInService(store, lake)

    item = await service.clip_in(
        source_id=source.id,
        content="Great thread on why storage beats tokens for long-context.",
        url="https://linkedin.com/posts/xyz",
        author="Jane Expert",
        content_date=utcnow() - timedelta(days=3),
        tags=["storage", "context"],
        title="Storage vs tokens",
    )

    assert item.id is not None
    assert item.classification == SourceClassification.read_as_needed.value
    assert item.source_id == source.id
    assert item.metadata.author == "Jane Expert"
    assert item.metadata.url == "https://linkedin.com/posts/xyz"
    assert item.metadata.tags == ["storage", "context"]
    assert item.metadata.extra["clipped"] is True
    # Indexed on ingest, retrievable, and read-as-needed queryable.
    assert item.embedding is not None and item.keyword_tokens
    fetched = await lake.get(item.id)
    assert fetched is not None and "long-context" in fetched.raw_content


async def test_clip_in_requires_linkedin_source(store: WorkStateStore, lake: ContentLake) -> None:
    # A non-clip source (e.g. slack) must be rejected — clip-in is LinkedIn/X only.
    slack = await store.sources.insert(
        Source(
            display_name="slack",
            kind=SourceKind.slack,
            classification=SourceClassification.scraped_periodically,
        )
    )
    service = ClipInService(store, lake)
    with pytest.raises(ClipInError):
        await service.clip_in(source_id=slack.id, content="pasted")


async def test_clip_in_unknown_source(store: WorkStateStore, lake: ContentLake) -> None:
    service = ClipInService(store, lake)
    with pytest.raises(ClipInError):
        await service.clip_in(source_id="nope", content="pasted")


async def test_clip_in_rejects_empty_content(store: WorkStateStore, lake: ContentLake) -> None:
    source = await _clip_source(store)
    service = ClipInService(store, lake)
    with pytest.raises(ClipInError):
        await service.clip_in(source_id=source.id, content="   ")


async def test_clip_in_minimal_metadata(store: WorkStateStore, lake: ContentLake) -> None:
    # Only content + source required; everything else is optional (human supplies what they can).
    source = await _clip_source(store)
    service = ClipInService(store, lake)
    item = await service.clip_in(source_id=source.id, content="a bare paste with no extras")
    assert item.classification == SourceClassification.read_as_needed.value
    # content_date defaulted by the lake so the clip is still windowable.
    assert item.metadata.content_date is not None
