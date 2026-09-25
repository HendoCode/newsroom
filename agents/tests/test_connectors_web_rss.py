"""Web/RSS connector tests (D8).

Two layers: the **pure** ``parse_feed`` (RSS 2.0 + Atom, no I/O) tested directly against sample
XML, and the ``WebRssConnector`` end-to-end into the in-memory lake with a fake ``FeedFetcher`` (so
the connector's fetch → map → ingest path runs offline, no network). Web/RSS is credential-free.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.connectors import RawItem, WebRssConnector, parse_feed
from app.connectors.base import ConnectorError
from app.lake import ContentLake
from app.models.common import utcnow
from app.models.source import Source, SourceClassification, SourceKind

RSS_XML = """<?xml version="1.0"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>Cloud Weekly</title>
    <item>
      <title>S3 storage tiering explained</title>
      <link>https://example.com/s3-tiering</link>
      <guid>guid-s3-tiering</guid>
      <description>How cold storage saves money.</description>
      <dc:creator>alex</dc:creator>
      <pubDate>Wed, 23 Jul 2026 10:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Kubernetes autoscaling</title>
      <link>https://example.com/k8s</link>
      <description>Node pools and HPA.</description>
      <pubDate>Tue, 22 Jul 2026 09:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""

ATOM_XML = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Eng Blog</title>
  <entry>
    <title>Vector search at scale</title>
    <id>tag:example.com,2026:vector</id>
    <link href="https://example.com/vector"/>
    <summary>Hybrid indexes in production.</summary>
    <author><name>demo-dana</name></author>
    <updated>2026-07-24T12:30:00Z</updated>
  </entry>
</feed>
"""


class FakeFeedFetcher:
    """A ``FeedFetcher`` that serves canned XML per URL — the network seam, mocked."""

    def __init__(self, by_url: dict[str, str]) -> None:
        self.by_url = by_url
        self.calls: list[str] = []

    async def fetch(self, url: str) -> str:
        self.calls.append(url)
        return self.by_url[url]


def _source(**config) -> Source:
    return Source(
        display_name="feeds",
        kind=SourceKind.web_rss,
        classification=SourceClassification.scraped_periodically,
        config=config,
        id="src-rss",
    )


# --- pure parser --------------------------------------------------------------------------


def test_parse_rss() -> None:
    items = parse_feed(RSS_XML)
    assert len(items) == 2
    first = items[0]
    assert first.title == "S3 storage tiering explained"
    assert first.external_id == "guid-s3-tiering"
    assert first.url == "https://example.com/s3-tiering"
    assert first.author == "alex"
    assert "cold storage" in first.raw_content
    assert first.content_date is not None and first.content_date.year == 2026
    assert first.extra["feed_format"] == "rss"


def test_parse_atom() -> None:
    items = parse_feed(ATOM_XML)
    assert len(items) == 1
    entry = items[0]
    assert entry.title == "Vector search at scale"
    assert entry.external_id == "tag:example.com,2026:vector"
    assert entry.url == "https://example.com/vector"
    assert entry.author == "demo-dana"
    assert entry.content_date is not None and entry.content_date.month == 7
    assert entry.extra["feed_format"] == "atom"


def test_parse_bad_xml_raises() -> None:
    with pytest.raises(ConnectorError):
        parse_feed("<not-xml <<<")


# --- connector → lake ---------------------------------------------------------------------


async def test_web_rss_ingests_into_lake(lake: ContentLake) -> None:
    fetcher = FakeFeedFetcher({"https://example.com/rss": RSS_XML})
    connector = WebRssConnector(fetcher)
    # Wide window so the fixed sample dates aren't filtered (the window is covered separately).
    result = await connector.refresh(
        _source(feed_urls=["https://example.com/rss"]), lake, lookback_days=3650
    )

    assert result.ingested == 2 and result.skipped == 0
    assert fetcher.calls == ["https://example.com/rss"]
    # Landed in the lake with the right classification + provenance metadata.
    stored = await lake.get(result.item_ids[0])
    assert stored is not None
    assert stored.classification == SourceClassification.scraped_periodically.value
    assert stored.source_id == "src-rss"
    assert stored.metadata.extra["feed_url"] == "https://example.com/rss"
    assert stored.metadata.extra["external_id"] == "guid-s3-tiering"
    # Indexed on ingest (lake concern, proven end-to-end here).
    assert stored.embedding is not None and stored.keyword_tokens


async def test_web_rss_refresh_is_idempotent(lake: ContentLake) -> None:
    fetcher = FakeFeedFetcher({"u": RSS_XML})
    connector = WebRssConnector(fetcher)
    src = _source(feed_urls=["u"])

    first = await connector.refresh(src, lake, lookback_days=3650)
    second = await connector.refresh(src, lake, lookback_days=3650)

    assert first.ingested == 2
    assert second.ingested == 0 and second.skipped == 2  # nothing duplicated on re-refresh
    assert await lake.count() == 2


async def test_web_rss_applies_lookback_window(lake: ContentLake) -> None:
    # One entry inside a 7-day window, one well outside it.
    fresh = (utcnow() - timedelta(days=1)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    stale = (utcnow() - timedelta(days=60)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    xml = f"""<rss version="2.0"><channel>
      <item><title>fresh</title><guid>g-fresh</guid><pubDate>{fresh}</pubDate></item>
      <item><title>stale</title><guid>g-stale</guid><pubDate>{stale}</pubDate></item>
    </channel></rss>"""
    connector = WebRssConnector(FakeFeedFetcher({"u": xml}))
    result = await connector.refresh(_source(feed_urls=["u"]), lake, lookback_days=7)

    assert result.ingested == 1
    stored = await lake.get(result.item_ids[0])
    assert stored is not None and "fresh" in stored.raw_content


async def test_web_rss_bad_config_raises() -> None:
    connector = WebRssConnector(FakeFeedFetcher({}))
    with pytest.raises(ConnectorError):
        await connector.fetch(_source(feed_urls="not-a-list"), lookback_days=7)


def test_parse_feed_returns_rawitems() -> None:
    # Guard the return contract the connector relies on.
    assert all(isinstance(i, RawItem) for i in parse_feed(RSS_XML))
