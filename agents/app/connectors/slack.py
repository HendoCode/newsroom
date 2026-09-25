"""Slack connector (D8) — read configured channels via a server-side bot token.

Pulls message history from a configured workspace + channel list and hands each message to the
lake. The bot token is **server-side only** (``Settings.slack_bot_token``, D14) — never in the
Source registry doc and never client-exposed. (The same Slack app also carries the expert
deep-link share, but that is a UI concern; here the connector is read-only.)

Seams:
- ``SlackClient`` — the Slack Web API seam (``conversations.history``). Tests inject a fake.
- ``HttpSlackClient`` — the real client (httpx against ``https://slack.com/api``), built from the
  server-side bot token.

Config (Source.config): ``channel_ids: list[str]`` (channels to ingest), optional ``workspace``
(label only). No credentials in config.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.connectors.base import ConnectorError, RawItem, SourceConnector
from app.models.common import utcnow
from app.models.source import Source, SourceKind


@dataclass
class SlackMessage:
    """One Slack message as the connector needs it (a thin projection of the API payload)."""

    ts: str  # Slack's per-channel message id (also its timestamp) — the stable external id
    text: str
    user: str | None = None


class SlackClient(Protocol):
    """Read message history for a channel since ``oldest`` (a Slack epoch-seconds string)."""

    async def channel_history(self, channel_id: str, *, oldest: str) -> list[SlackMessage]: ...


def _slack_ts_to_date(ts: str) -> datetime | None:
    """Slack ``ts`` is ``"<epoch>.<seq>"``; the integer part is epoch seconds (UTC)."""
    try:
        return datetime.fromtimestamp(float(ts), tz=UTC).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


class SlackConnector(SourceConnector):
    """Pull message history from the channels listed in a Source's ``config.channel_ids``."""

    kind = SourceKind.slack

    def __init__(self, client: SlackClient) -> None:
        self.client = client

    async def fetch(self, source: Source, *, lookback_days: int) -> list[RawItem]:
        channel_ids = source.config.get("channel_ids", [])
        if not isinstance(channel_ids, list):
            raise ConnectorError("slack config.channel_ids must be a list of channel ids")
        workspace = source.config.get("workspace")

        # Recency window (D7) → Slack's `oldest` epoch-seconds bound.
        oldest_dt = utcnow().timestamp() - lookback_days * 86400
        oldest = f"{oldest_dt:.6f}"

        pulled: list[RawItem] = []
        for channel_id in channel_ids:
            messages = await self.client.channel_history(str(channel_id), oldest=oldest)
            for msg in messages:
                if not msg.text.strip():
                    continue
                extra: dict[str, Any] = {"channel_id": channel_id}
                if workspace is not None:
                    extra["workspace"] = workspace
                pulled.append(
                    RawItem(
                        raw_content=msg.text,
                        # Unique per (channel, ts) so the same message in two channels is distinct.
                        external_id=f"{channel_id}:{msg.ts}",
                        content_date=_slack_ts_to_date(msg.ts),
                        author=msg.user,
                        url=None,
                        extra=extra,
                    )
                )
        return pulled


class HttpSlackClient:
    """Real ``SlackClient`` over the Slack Web API. Bot token is server-side only (D14)."""

    BASE_URL = "https://slack.com/api"

    def __init__(self, bot_token: str, timeout: float = 20.0) -> None:
        self._bot_token = bot_token
        self.timeout = timeout

    async def channel_history(self, channel_id: str, *, oldest: str) -> list[SlackMessage]:
        if not self._bot_token:
            raise ConnectorError(
                "Slack bot token not configured (SLACK_BOT_TOKEN); provision the Slack app "
                "(see app/connectors/README.md)"
            )
        import httpx  # local import so pure connector logic tests need no httpx on the path

        headers = {"Authorization": f"Bearer {self._bot_token}"}
        messages: list[SlackMessage] = []
        cursor: str | None = None
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            while True:
                params: dict[str, Any] = {"channel": channel_id, "oldest": oldest, "limit": 200}
                if cursor:
                    params["cursor"] = cursor
                resp = await client.get(
                    f"{self.BASE_URL}/conversations.history", params=params, headers=headers
                )
                resp.raise_for_status()
                body = resp.json()
                if not body.get("ok", False):
                    raise ConnectorError(f"Slack API error: {body.get('error', 'unknown')}")
                for m in body.get("messages", []):
                    if m.get("type") == "message" and "text" in m:
                        messages.append(
                            SlackMessage(
                                ts=m.get("ts", ""), text=m.get("text", ""), user=m.get("user")
                            )
                        )
                cursor = body.get("response_metadata", {}).get("next_cursor") or None
                if not cursor:
                    break
        return messages
