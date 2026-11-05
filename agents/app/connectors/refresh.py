"""On-demand source refresh (D7/D8) — the "refresh sources" entrypoint.

The single seam that drives the Green connectors: given the Source registry, it selects the
enabled ``scraped-periodically`` sources, dispatches each to the connector for its kind, ingests
what they pull into the lake, and stamps ``last_refreshed``. It runs **only when asked** — before
an Oracle run or from a "Refresh sources" action — never on a schedule (D7/§9, no scheduler).

Design notes:
- **Warns, does not block** (§5): a source that errors (missing creds, upstream failure, no
  connector) is recorded as a ``RefreshResult`` with an ``error`` and the loop moves on — one bad
  source never blocks the rest.
- **Config drives everything** (Item 6): a connector reads its config from the Source doc; adding /
  editing / toggling a source is a plain registry operation. Credentials stay server-side.
- ``read-as-needed`` sources (LinkedIn/X clip-in) are never refreshed here — they have no fetch.
"""

from __future__ import annotations

from app.config import Settings, get_settings
from app.connectors.base import RefreshResult, SourceConnector
from app.connectors.gdrive import GoogleDriveConnector, HttpDriveClient
from app.connectors.slack import HttpSlackClient, SlackConnector
from app.connectors.web_rss import HttpFeedFetcher, WebRssConnector
from app.lake.store import ContentLake
from app.models.common import utcnow
from app.models.source import Source, SourceClassification, SourceKind
from app.repositories import WorkStateStore


def build_connectors(settings: Settings | None = None) -> dict[SourceKind, SourceConnector]:
    """Wire the real Green connectors from server-side settings (D14).

    Every connector is built regardless of whether its credentials are present: a connector with
    missing creds raises a clear ``ConnectorError`` only *when it is used*, which the refresh
    service catches and reports per source — so the service always boots and unconfigured
    connectors simply report an error on refresh rather than crashing.
    """
    settings = settings or get_settings()
    return {
        SourceKind.gdrive: GoogleDriveConnector(
            HttpDriveClient(
                client_id=settings.google_oauth_client_id,
                client_secret=settings.google_oauth_client_secret,
                refresh_token=settings.google_oauth_refresh_token,
            )
        ),
        SourceKind.slack: SlackConnector(HttpSlackClient(bot_token=settings.slack_bot_token)),
        SourceKind.web_rss: WebRssConnector(HttpFeedFetcher()),
    }


class SourceRefreshService:
    """Refresh Green-connector sources on demand from the registry into the lake."""

    def __init__(
        self,
        store: WorkStateStore,
        lake: ContentLake,
        connectors: dict[SourceKind, SourceConnector],
    ) -> None:
        self.store = store
        self.lake = lake
        self.connectors = connectors

    async def refresh(
        self,
        *,
        source_id: str | None = None,
        kinds: list[str] | None = None,
        lookback_days: int | None = None,
    ) -> list[RefreshResult]:
        """Refresh the selected sources. Returns one ``RefreshResult`` per source attempted.

        Selection: a specific ``source_id``, or all enabled ``scraped-periodically`` sources
        (optionally narrowed to ``kinds``). ``lookback_days`` overrides each source's default
        window (D7).
        """
        sources = await self._select(source_id, kinds)
        results: list[RefreshResult] = []
        for source in sources:
            results.append(await self._refresh_one(source, lookback_days))
        return results

    async def _refresh_one(self, source: Source, lookback_days: int | None) -> RefreshResult:
        assert source.id is not None
        # read-as-needed sources (clip-in) are never programmatically refreshed.
        if SourceClassification(source.classification) != SourceClassification.scraped_periodically:
            return RefreshResult(
                source_id=source.id,
                kind=str(source.kind),
                error="source is read-as-needed (manual clip-in); nothing to refresh",
            )
        connector = self.connectors.get(SourceKind(source.kind))
        if connector is None:
            return RefreshResult(
                source_id=source.id,
                kind=str(source.kind),
                error=f"no connector registered for kind {source.kind}",
            )
        try:
            result = await connector.refresh(source, self.lake, lookback_days=lookback_days)
            await self.store.sources.update(source.id, {"last_refreshed": utcnow()})
            return result
        except Exception as exc:  # noqa: BLE001 — warns, does not block; one bad source is isolated
            return RefreshResult(source_id=source.id, kind=str(source.kind), error=str(exc))

    async def _select(self, source_id: str | None, kinds: list[str] | None) -> list[Source]:
        if source_id is not None:
            source = await self.store.sources.get(source_id)
            return [source] if source is not None else []
        enabled = await self.store.sources.list_enabled()
        scraped = [
            s
            for s in enabled
            if SourceClassification(s.classification) == SourceClassification.scraped_periodically
        ]
        if kinds:
            wanted = {SourceKind(k) for k in kinds}
            scraped = [s for s in scraped if SourceKind(s.kind) in wanted]
        return scraped
