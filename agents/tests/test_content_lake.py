"""Content lake + hybrid index tests (D9, domain model §1.4).

Covers ingest (write + index-on-ingest + the no-delete invariant) and each retrieval leg in
isolation — semantic, keyword, structured-metadata, recency window — plus the combined hybrid
query and the top-K cap. Runs against the in-memory async Mongo via the ``lake`` fixture (local
hybrid index + deterministic hashing embedder), so it is green with no server and no API key.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.lake import ContentLake, ContentLakeItem, ContentMetadata, LakeQuery
from app.models.common import utcnow
from app.models.source import SourceClassification


def _item(
    raw: str,
    *,
    source_id: str = "src-1",
    classification: SourceClassification = SourceClassification.scraped_periodically,
    author: str | None = None,
    tags: list[str] | None = None,
    content_date=None,
) -> ContentLakeItem:
    return ContentLakeItem(
        raw_content=raw,
        source_id=source_id,
        classification=classification,
        metadata=ContentMetadata(author=author, tags=tags or [], content_date=content_date),
    )


# --- ingest -------------------------------------------------------------------------------


async def test_ingest_writes_and_indexes_on_ingest(lake: ContentLake) -> None:
    stored = await lake.ingest(_item("AWS S3 storage pricing for cold data"))
    assert stored.id is not None
    # Indexed on ingest: both computed legs are populated by the ingest call.
    assert stored.embedding is not None and len(stored.embedding) == lake.embedder.dim
    assert "storage" in stored.keyword_tokens and "pricing" in stored.keyword_tokens
    # content_date defaulted so the item is windowable.
    assert stored.metadata.content_date is not None
    # Round-trips through the store.
    fetched = await lake.get(stored.id)
    assert fetched is not None and fetched.raw_content == "AWS S3 storage pricing for cold data"


async def test_ingest_preserves_supplied_content_date(lake: ContentLake) -> None:
    when = utcnow() - timedelta(days=30)
    stored = await lake.ingest(_item("old news", content_date=when))
    assert stored.metadata.content_date == when


async def test_lake_never_deletes(lake: ContentLake) -> None:
    stored = await lake.ingest(_item("permanent record"))
    assert stored.id is not None
    with pytest.raises(NotImplementedError):
        await lake.repo.delete(stored.id)


# --- retrieval legs, in isolation ---------------------------------------------------------


async def test_semantic_only_retrieval(lake: ContentLake) -> None:
    await lake.ingest(_item("AWS S3 storage costs and pricing for large datasets"))
    await lake.ingest(_item("Kubernetes pod scheduling and node autoscaling"))
    await lake.ingest(_item("AWS storage tiering saves money on cold data"))

    results = await lake.query(
        LakeQuery(text="storage pricing on AWS", semantic_weight=1.0, keyword_weight=0.0)
    )
    # The unrelated Kubernetes item shares no vocabulary → excluded, not padded in.
    assert results, "expected at least one semantic match"
    assert all("Kubernetes" not in r.item.raw_content for r in results)
    # Pure semantic mode: the semantic leg drove the rank; the keyword leg is silent.
    assert all(r.semantic_score > 0.0 for r in results)
    assert all(r.keyword_score == 0.0 for r in results)
    # The most on-topic item ranks first.
    assert "S3 storage costs and pricing" in results[0].item.raw_content


async def test_keyword_only_retrieval(lake: ContentLake) -> None:
    await lake.ingest(_item("AWS S3 storage costs and pricing for large datasets"))
    await lake.ingest(_item("Kubernetes pod scheduling and node autoscaling"))

    results = await lake.query(
        LakeQuery(text="storage pricing", semantic_weight=0.0, keyword_weight=1.0)
    )
    assert len(results) == 1
    assert "storage" in results[0].item.raw_content
    # Pure keyword mode: keyword leg drove the rank; semantic leg silent.
    assert results[0].keyword_score > 0.0 and results[0].semantic_score == 0.0


async def test_metadata_only_filter_no_text(lake: ContentLake) -> None:
    await lake.ingest(_item("slack chatter", source_id="src-slack", author="alex", tags=["aws"]))
    await lake.ingest(_item("drive transcript", source_id="src-gdrive", author="demo-dana"))

    by_source = await lake.query(LakeQuery(source_ids=["src-slack"]))
    assert [r.item.metadata.author for r in by_source] == ["alex"]

    by_author = await lake.query(LakeQuery(authors=["demo-dana"]))
    assert len(by_author) == 1 and by_author[0].item.source_id == "src-gdrive"

    by_tag = await lake.query(LakeQuery(tags=["aws"]))
    assert len(by_tag) == 1 and by_tag[0].item.source_id == "src-slack"

    # No text query → recency browse, no ranking signal.
    assert all(r.score == 0.0 for r in by_source)


async def test_classification_filter(lake: ContentLake) -> None:
    await lake.ingest(_item("scraped feed item", classification=SourceClassification.scraped_periodically))
    await lake.ingest(_item("pasted clip", classification=SourceClassification.read_as_needed))

    results = await lake.query(LakeQuery(classification=SourceClassification.read_as_needed))
    assert len(results) == 1 and results[0].item.raw_content == "pasted clip"


async def test_recency_window(lake: ContentLake) -> None:
    await lake.ingest(_item("fresh AWS storage news", content_date=utcnow() - timedelta(days=1)))
    await lake.ingest(_item("stale AWS storage news", content_date=utcnow() - timedelta(days=90)))

    windowed = await lake.query(LakeQuery(text="AWS storage", lookback_days=7))
    assert len(windowed) == 1 and "fresh" in windowed[0].item.raw_content


# --- combined hybrid + discipline ---------------------------------------------------------


async def test_combined_hybrid_query(lake: ContentLake) -> None:
    await lake.ingest(
        _item("AWS storage cost breakdown", source_id="src-slack", tags=["aws"])
    )
    await lake.ingest(
        _item("AWS storage cost breakdown, older", source_id="src-slack", tags=["aws"],
              content_date=utcnow() - timedelta(days=120))
    )
    await lake.ingest(_item("AWS storage costs", source_id="src-other", tags=["aws"]))

    results = await lake.query(
        LakeQuery(
            text="AWS storage cost",
            source_ids=["src-slack"],  # metadata pre-filter
            lookback_days=30,  # recency pre-filter drops the 120-day-old item
            top_k=5,
        )
    )
    # Only the in-window src-slack item survives the hard filters, then ranks on the blend.
    assert len(results) == 1
    assert results[0].item.source_id == "src-slack"
    assert results[0].item.raw_content == "AWS storage cost breakdown"
    assert results[0].score > 0.0


async def test_top_k_cap(lake: ContentLake) -> None:
    for i in range(6):
        await lake.ingest(_item(f"AWS storage note number {i}"))
    results = await lake.query(LakeQuery(text="AWS storage note", top_k=2))
    assert len(results) == 2  # rank-and-retrieve: capped, never the whole lake


async def test_no_match_returns_empty(lake: ContentLake) -> None:
    await lake.ingest(_item("AWS storage pricing"))
    results = await lake.query(LakeQuery(text="quantum entanglement biology"))
    assert results == []  # nothing overlapped → no candidates, not the whole lake
