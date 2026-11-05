"""Web / RSS connector (D8) — public, credential-free programmatic pull.

Reads configured feed/site URLs, parses RSS 2.0 and Atom, and hands each entry to the lake. This
is a *legitimate* programmatic pull of public feeds — not a scraper (D8): it fetches declared feed
URLs and parses their published XML, nothing more.

Two seams:
- ``parse_feed`` — a **pure** function (XML text → ``RawItem``s). All the real parsing logic lives
  here and is unit-tested directly with sample XML, no network.
- ``FeedFetcher`` — the network seam (URL → XML text). The real ``HttpFeedFetcher`` uses httpx;
  tests inject a fake mapping so the connector is exercised end-to-end offline.

Config (Source.config): ``feed_urls: list[str]``. No credentials (public).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Protocol
from xml.etree import ElementTree as ET

from app.connectors.base import ConnectorError, RawItem, SourceConnector
from app.models.common import utcnow
from app.models.source import Source, SourceKind

# Atom namespace (RSS 2.0 is namespace-free).
_ATOM = "{http://www.w3.org/2005/Atom}"


class FeedFetcher(Protocol):
    """Fetch the raw feed document for a URL. The only network-touching seam of this connector."""

    async def fetch(self, url: str) -> str: ...


def _naive_utc(dt: datetime | None) -> datetime | None:
    """Normalize to naive-UTC to match the store's timestamp convention (``app.models.common``)."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def _parse_date(text: str | None) -> datetime | None:
    """Parse an RSS (RFC 822) or Atom (RFC 3339) date; return None if unparseable."""
    if not text:
        return None
    text = text.strip()
    # RSS pubDate → RFC 822 (email.utils handles it).
    try:
        return _naive_utc(parsedate_to_datetime(text))
    except (TypeError, ValueError):
        pass
    # Atom updated/published → RFC 3339 / ISO 8601 (3.12 fromisoformat parses a trailing "Z").
    try:
        return _naive_utc(datetime.fromisoformat(text))
    except ValueError:
        return None


def _text(elem: ET.Element | None) -> str | None:
    return elem.text.strip() if elem is not None and elem.text else None


def parse_feed(xml_text: str) -> list[RawItem]:
    """Parse RSS 2.0 or Atom XML into ``RawItem``s. Pure — no I/O.

    Raises ``ConnectorError`` on XML that does not parse at all; skips individual malformed entries
    rather than failing the whole feed.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ConnectorError(f"feed did not parse as XML: {exc}") from exc

    items: list[RawItem] = []

    # RSS 2.0: <rss><channel><item>…
    for item in root.iter("item"):
        title = _text(item.find("title"))
        link = _text(item.find("link"))
        guid = _text(item.find("guid")) or link
        description = _text(item.find("description")) or ""
        author = _text(item.find("author")) or _text(
            item.find("{http://purl.org/dc/elements/1.1/}creator")
        )
        date = _parse_date(_text(item.find("pubDate")))
        body = "\n\n".join(part for part in (title, description) if part)
        if not body:
            continue
        items.append(
            RawItem(
                raw_content=body,
                external_id=guid,
                content_date=date,
                author=author,
                title=title,
                url=link,
                extra={"feed_format": "rss"},
            )
        )

    # Atom: <feed><entry>…
    for entry in root.iter(f"{_ATOM}entry"):
        title = _text(entry.find(f"{_ATOM}title"))
        link_el = entry.find(f"{_ATOM}link")
        link = link_el.get("href") if link_el is not None else None
        entry_id = _text(entry.find(f"{_ATOM}id")) or link
        summary = _text(entry.find(f"{_ATOM}summary")) or _text(entry.find(f"{_ATOM}content")) or ""
        author_el = entry.find(f"{_ATOM}author")
        author = _text(author_el.find(f"{_ATOM}name")) if author_el is not None else None
        date = _parse_date(
            _text(entry.find(f"{_ATOM}updated")) or _text(entry.find(f"{_ATOM}published"))
        )
        body = "\n\n".join(part for part in (title, summary) if part)
        if not body:
            continue
        items.append(
            RawItem(
                raw_content=body,
                external_id=entry_id,
                content_date=date,
                author=author,
                title=title,
                url=link,
                extra={"feed_format": "atom"},
            )
        )

    return items


class WebRssConnector(SourceConnector):
    """Pull public RSS/Atom feeds listed in a Source's ``config.feed_urls``. No credentials."""

    kind = SourceKind.web_rss

    def __init__(self, fetcher: FeedFetcher) -> None:
        self.fetcher = fetcher

    async def fetch(self, source: Source, *, lookback_days: int) -> list[RawItem]:
        feed_urls = source.config.get("feed_urls", [])
        if not isinstance(feed_urls, list):
            raise ConnectorError("web-rss config.feed_urls must be a list of URLs")

        # Recency window (D7): drop entries dated older than the window. Undated entries are kept
        # (the window can't be applied to what has no date) and the lake defaults their date.
        cutoff = utcnow() - timedelta(days=lookback_days)

        pulled: list[RawItem] = []
        for url in feed_urls:
            xml_text = await self.fetcher.fetch(str(url))
            for raw in parse_feed(xml_text):
                if raw.content_date is not None and raw.content_date < cutoff:
                    continue
                raw.extra["feed_url"] = url
                pulled.append(raw)
        return pulled


class HttpFeedFetcher:
    """Real ``FeedFetcher``: GET the feed URL over HTTP with httpx. No credentials (public pull)."""

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    async def fetch(self, url: str) -> str:
        import httpx  # local import keeps httpx off the import path for pure-parser tests

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "newsroom-connector/1.0"})
            resp.raise_for_status()
            return resp.text
