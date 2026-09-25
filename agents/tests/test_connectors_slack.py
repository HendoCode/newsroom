"""Slack connector tests (D8).

Drives ``SlackConnector`` end-to-end into the in-memory lake with a fake ``SlackClient`` (the Slack
Web API seam, mocked). Proves per-channel history → lake, the ``oldest`` window bound, provenance
metadata, and idempotent re-refresh. The real bot token never appears — creds are server-side.
"""

from __future__ import annotations

import pytest

from app.connectors import SlackConnector, SlackMessage
from app.connectors.base import ConnectorError
from app.lake import ContentLake
from app.models.source import Source, SourceClassification, SourceKind


class FakeSlackClient:
    """A ``SlackClient`` serving canned messages per channel, recording the ``oldest`` bound."""

    def __init__(self, by_channel: dict[str, list[SlackMessage]]) -> None:
        self.by_channel = by_channel
        self.oldest_seen: dict[str, str] = {}

    async def channel_history(self, channel_id: str, *, oldest: str) -> list[SlackMessage]:
        self.oldest_seen[channel_id] = oldest
        return self.by_channel.get(channel_id, [])


def _source(**config) -> Source:
    return Source(
        display_name="slack",
        kind=SourceKind.slack,
        classification=SourceClassification.scraped_periodically,
        config=config,
        id="src-slack",
    )


async def test_slack_ingests_channel_history(lake: ContentLake) -> None:
    client = FakeSlackClient(
        {
            "C123": [
                SlackMessage(
                    ts="1753000000.000100", text="AWS storage costs are dropping", user="U1"
                ),
                SlackMessage(ts="1753000100.000200", text="great point on tiering", user="U2"),
            ]
        }
    )
    connector = SlackConnector(client)
    result = await connector.refresh(_source(channel_ids=["C123"], workspace="hendo"), lake)

    assert result.ingested == 2 and result.skipped == 0
    stored = await lake.get(result.item_ids[0])
    assert stored is not None
    assert stored.source_id == "src-slack"
    assert stored.classification == SourceClassification.scraped_periodically.value
    assert stored.metadata.author == "U1"
    assert stored.metadata.extra["channel_id"] == "C123"
    assert stored.metadata.extra["workspace"] == "hendo"
    assert stored.metadata.extra["external_id"] == "C123:1753000000.000100"
    # Slack ts → content_date.
    assert stored.metadata.content_date is not None
    # Indexed on ingest.
    assert stored.embedding is not None and stored.keyword_tokens


async def test_slack_passes_lookback_as_oldest_bound(lake: ContentLake) -> None:
    client = FakeSlackClient({"C1": []})
    connector = SlackConnector(client)
    await connector.refresh(_source(channel_ids=["C1"]), lake, lookback_days=7)
    # The connector translated the window into an epoch-seconds `oldest` string.
    oldest = float(client.oldest_seen["C1"])
    assert oldest > 0


async def test_slack_skips_empty_messages(lake: ContentLake) -> None:
    client = FakeSlackClient(
        {
            "C1": [
                SlackMessage(ts="1.0", text="   ", user="U1"),
                SlackMessage(ts="2.0", text="real", user="U2"),
            ]
        }
    )
    connector = SlackConnector(client)
    result = await connector.refresh(_source(channel_ids=["C1"]), lake)
    assert result.ingested == 1


async def test_slack_refresh_is_idempotent(lake: ContentLake) -> None:
    client = FakeSlackClient({"C1": [SlackMessage(ts="1753000000.0001", text="hi", user="U1")]})
    connector = SlackConnector(client)
    src = _source(channel_ids=["C1"])
    await connector.refresh(src, lake)
    second = await connector.refresh(src, lake)
    assert second.ingested == 0 and second.skipped == 1
    assert await lake.count() == 1


async def test_slack_multiple_channels(lake: ContentLake) -> None:
    client = FakeSlackClient(
        {
            "C1": [SlackMessage(ts="1.0", text="from one", user="U1")],
            "C2": [SlackMessage(ts="2.0", text="from two", user="U2")],
        }
    )
    connector = SlackConnector(client)
    result = await connector.refresh(_source(channel_ids=["C1", "C2"]), lake)
    assert result.ingested == 2


async def test_slack_bad_config_raises() -> None:
    connector = SlackConnector(FakeSlackClient({}))
    with pytest.raises(ConnectorError):
        await connector.fetch(_source(channel_ids="C1"), lookback_days=7)
