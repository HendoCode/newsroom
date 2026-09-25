"""Source connectors (D8) — the pull-and-ingest layer over the content lake.

Each connector turns one Source-registry entry (§1.3) into content-lake items (§1.4): it pulls raw
material from an external system and writes it to the lake via the lake's ingest API (D9). The
connector's job **ends** at ingest — indexing is the lake's concern, and Oracle/ranking logic is a
separate ticket.

v1 scope (D8):
- **Green connectors** (``scraped-periodically``, refreshed on demand — no scheduler, D7):
  - ``GoogleDriveConnector`` — transcript folders, server-side OAuth (D14).
  - ``SlackConnector`` — configured channels, server-side bot token (D14).
  - ``WebRssConnector`` — public RSS/Atom feeds, no credentials.
- **LinkedIn / X clip-in** (``ClipInService``): the credential-free ``read-as-needed`` paste path.
  No fetch, no scraper, nothing to authenticate — the *only* sanctioned LinkedIn/X path (D8).

Orchestration seams:
- ``SourceRefreshService`` + ``build_connectors`` — the on-demand "refresh sources" entrypoint,
  driven by the Source registry, with server-side credentials from ``Settings``.

Provider credentials are **server-side only** (env, via ``Settings``); they never live in a Source
registry doc and are never client-exposed. See ``README.md`` for what an admin must provision.
"""

from __future__ import annotations

from app.connectors.base import (
    ConnectorError,
    RawItem,
    RefreshResult,
    SourceConnector,
)
from app.connectors.clipin import ClipInError, ClipInService
from app.connectors.gdrive import (
    DriveClient,
    DriveFile,
    GoogleDriveConnector,
    HttpDriveClient,
)
from app.connectors.refresh import SourceRefreshService, build_connectors
from app.connectors.slack import (
    HttpSlackClient,
    SlackClient,
    SlackConnector,
    SlackMessage,
)
from app.connectors.web_rss import (
    FeedFetcher,
    HttpFeedFetcher,
    WebRssConnector,
    parse_feed,
)

__all__ = [
    "ClipInError",
    "ClipInService",
    "ConnectorError",
    "DriveClient",
    "DriveFile",
    "FeedFetcher",
    "GoogleDriveConnector",
    "HttpDriveClient",
    "HttpFeedFetcher",
    "HttpSlackClient",
    "RawItem",
    "RefreshResult",
    "SlackClient",
    "SlackConnector",
    "SlackMessage",
    "SourceConnector",
    "SourceRefreshService",
    "WebRssConnector",
    "build_connectors",
    "parse_feed",
]
