"""SourceRefreshService tests (D7/D8) — the on-demand "refresh sources" entrypoint.

Proves registry-driven dispatch by kind into the lake, ``last_refreshed`` stamping, the selection
rules (enabled + scraped-periodically only, optional kind/source filters), and the "warns, does not
block" isolation: a source whose connector errors is reported and the others still run. Uses fake
connectors so no network/creds are involved.
"""

from __future__ import annotations

from app.connectors import RawItem, SourceConnector, SourceRefreshService
from app.connectors.base import ConnectorError
from app.lake import ContentLake
from app.models.source import Source, SourceClassification, SourceKind
from app.repositories import WorkStateStore


class FakeConnector(SourceConnector):
    """A connector that returns preset RawItems (or raises) — no external system."""

    def __init__(
        self, kind: SourceKind, items: list[RawItem] | None = None, boom: str | None = None
    ) -> None:
        self.kind = kind  # instance attr shadows the ClassVar for the registry lookup
        self._items = items or []
        self._boom = boom

    async def fetch(self, source: Source, *, lookback_days: int) -> list[RawItem]:
        if self._boom is not None:
            raise ConnectorError(self._boom)
        return list(self._items)


async def _add_source(store: WorkStateStore, **kw) -> Source:
    defaults: dict = {
        "display_name": "s",
        "kind": SourceKind.web_rss,
        "classification": SourceClassification.scraped_periodically,
        "enabled": True,
    }
    defaults.update(kw)
    return await store.sources.insert(Source(**defaults))


def _connectors(**by_kind: SourceConnector) -> dict[SourceKind, SourceConnector]:
    return {c.kind: c for c in by_kind.values()}


async def test_refresh_all_dispatches_by_kind(store: WorkStateStore, lake: ContentLake) -> None:
    await _add_source(store, kind=SourceKind.web_rss, display_name="rss")
    await _add_source(store, kind=SourceKind.slack, display_name="slack")

    connectors = _connectors(
        rss=FakeConnector(SourceKind.web_rss, [RawItem(raw_content="feed item", external_id="a")]),
        slack=FakeConnector(SourceKind.slack, [RawItem(raw_content="slack msg", external_id="b")]),
    )
    service = SourceRefreshService(store, lake, connectors)
    results = await service.refresh()

    assert len(results) == 2
    assert all(r.error is None for r in results)
    assert sum(r.ingested for r in results) == 2
    assert await lake.count() == 2


async def test_refresh_stamps_last_refreshed(store: WorkStateStore, lake: ContentLake) -> None:
    src = await _add_source(store, kind=SourceKind.web_rss)
    service = SourceRefreshService(
        store,
        lake,
        _connectors(
            rss=FakeConnector(SourceKind.web_rss, [RawItem(raw_content="x", external_id="1")])
        ),
    )
    await service.refresh()
    refreshed = await store.sources.get(src.id)
    assert refreshed is not None and refreshed.last_refreshed is not None


async def test_refresh_skips_read_as_needed(store: WorkStateStore, lake: ContentLake) -> None:
    # A LinkedIn/X clip source is manual; refresh must never try to pull it.
    clip = await _add_source(
        store,
        kind=SourceKind.linkedin_x_clip,
        classification=SourceClassification.read_as_needed,
    )
    service = SourceRefreshService(store, lake, {})
    results = await service.refresh(source_id=clip.id)
    assert len(results) == 1
    assert results[0].error is not None and "read-as-needed" in results[0].error
    assert await lake.count() == 0


async def test_refresh_excludes_disabled_sources(store: WorkStateStore, lake: ContentLake) -> None:
    await _add_source(store, kind=SourceKind.web_rss, enabled=False)
    service = SourceRefreshService(
        store,
        lake,
        _connectors(
            rss=FakeConnector(SourceKind.web_rss, [RawItem(raw_content="x", external_id="1")])
        ),
    )
    results = await service.refresh()
    assert results == []  # a disabled source is not selected for a bulk refresh


async def test_refresh_filters_by_kind(store: WorkStateStore, lake: ContentLake) -> None:
    await _add_source(store, kind=SourceKind.web_rss)
    await _add_source(store, kind=SourceKind.slack)
    connectors = _connectors(
        rss=FakeConnector(SourceKind.web_rss, [RawItem(raw_content="r", external_id="r1")]),
        slack=FakeConnector(SourceKind.slack, [RawItem(raw_content="s", external_id="s1")]),
    )
    service = SourceRefreshService(store, lake, connectors)
    results = await service.refresh(kinds=["slack"])
    assert len(results) == 1 and results[0].kind == SourceKind.slack.value


async def test_refresh_one_bad_source_does_not_block_others(
    store: WorkStateStore, lake: ContentLake
) -> None:
    await _add_source(store, kind=SourceKind.web_rss, display_name="good")
    await _add_source(store, kind=SourceKind.slack, display_name="bad")
    connectors = _connectors(
        rss=FakeConnector(SourceKind.web_rss, [RawItem(raw_content="good item", external_id="g1")]),
        slack=FakeConnector(SourceKind.slack, boom="upstream 500"),
    )
    service = SourceRefreshService(store, lake, connectors)
    results = await service.refresh()

    by_kind = {r.kind: r for r in results}
    assert by_kind[SourceKind.web_rss.value].ingested == 1
    assert by_kind[SourceKind.web_rss.value].error is None
    # The failing source is reported, not raised — and the good source still ingested.
    assert by_kind[SourceKind.slack.value].error == "upstream 500"
    assert await lake.count() == 1


async def test_refresh_missing_connector_reports_error(
    store: WorkStateStore, lake: ContentLake
) -> None:
    await _add_source(store, kind=SourceKind.gdrive)
    service = SourceRefreshService(store, lake, {})  # no connector registered for gdrive
    results = await service.refresh()
    assert len(results) == 1 and results[0].error is not None
    assert "no connector" in results[0].error
