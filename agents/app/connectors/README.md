# Source connectors (D8)

The pull-and-ingest layer over the content lake. Each connector turns one **Source registry**
entry (`app/models/source.py`, domain model §1.3) into **content-lake items** (§1.4): it pulls raw
material from an external system and writes it to the lake through the lake's ingest API
(`ContentLake.ingest`, D9). **The connector's job ends at ingest** — indexing is the lake's concern,
and Oracle/ranking logic is a separate ticket (not here). There are **no scrapers** and **no
scheduler** (D7/§9): refresh runs only when a human/Oracle asks.

## What's here

| Piece | Kind | Classification | Credentials | Refresh |
|-------|------|----------------|-------------|---------|
| `GoogleDriveConnector` (`gdrive.py`) | `gdrive` | scraped-periodically | server-side OAuth (below) | on demand |
| `SlackConnector` (`slack.py`) | `slack` | scraped-periodically | server-side bot token (below) | on demand |
| `WebRssConnector` (`web_rss.py`) | `web-rss` | scraped-periodically | none (public) | on demand |
| `ClipInService` (`clipin.py`) | `linkedin-x-clip` | **read-as-needed** | **none — no auth, no scraper** | manual paste |

- **Green connectors** implement `SourceConnector` (`base.py`): a `fetch` seam (pull `RawItem`s,
  network-touching, injectable client) and a shared `refresh` (map → dedup by `external_id` →
  ingest). Each real client (`Http*`) is built from server-side `Settings` by `build_connectors`
  in `refresh.py`.
- **`SourceRefreshService`** (`refresh.py`) is the on-demand "refresh sources" entrypoint: it
  selects enabled `scraped-periodically` sources from the registry, dispatches by kind, ingests,
  stamps `last_refreshed`, and **isolates failures** (one bad source is reported, never blocks the
  rest — the "warns, does not block" principle).
- **LinkedIn/X clip-in** is the credential-free path (D8): a human pastes text/URL + minimal
  metadata and it lands in the lake as `read-as-needed`. No fetch, no scraper, nothing to
  authenticate — the *only* sanctioned LinkedIn/X path.
- **REST** (`routes.py`): `POST /api/connectors/refresh`, `POST /api/connectors/clip`.

Adding / editing / toggling a source is a plain **Source registry** operation (Mongo work-state).
Credentials are **never** stored in a Source doc — the registry rejects credential-looking config
keys (`app/models/source.py`) — and are **never** client-exposed; they live server-side in
`Settings` only.

## Admin provisioning (the credentials an admin must set up)

All secrets are **server-side env** (`agents/.env`, injected by compose/deploy). Leave them blank
in dev: a connector with missing creds reports a clear error on refresh for its sources and never
crashes the service.

### Google Drive — incremental OAuth on the SSO identity (recommended)

`docs/design.md` D8/D10 and the open-decisions Item-6 recommendation: server-side incremental OAuth
on the SSO (NextAuth Google) identity — least privilege, no separate service-account secret.

1. In Google Cloud Console, create an **OAuth 2.0 client** (type: Web application) in the project
   tied to the company Workspace.
2. Add **both** the **Drive read-only** scope (`https://www.googleapis.com/auth/drive.readonly`,
   this connector's reads) **and** the **Drive file** scope
   (`https://www.googleapis.com/auth/drive.file`, needed by the finalize/review Google Docs export
   — `app/render/README.md`, `app/review/README.md` — which shares this exact same grant). Request
   both in the same consent pass; there is only one client id/secret/refresh token for all of it.
3. Complete a one-time **offline** consent to obtain a **refresh token** (offline access so the
   server can mint access tokens unattended).
4. Set: `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REFRESH_TOKEN`. In
   the AWS POC deploy these are SSM SecureString parameters resolved live by the secrets shim
   (`infra/aws-poc/secrets.tf`, "Google Docs/Drive OAuth grant for `agents`" in that directory's
   README) — populated out-of-band, never as a Terraform variable value.
5. Configure each Drive Source's `config`: `folder_ids: [...]` (transcript folders), optionally
   `mime_types: [...]` (defaults to Google Docs + `text/plain`).

*Fallback (unattended, folder-scoped):* a **service account** granted read on the transcript
folders. Same code path — swap `HttpDriveClient` for a service-account token source. Documented as
the fallback if offline user-OAuth refresh is not acceptable.

### Slack — a Slack app / bot token

1. Create a Slack app for the workspace; add **bot scopes** `channels:history`, `channels:read`,
   and `groups:history` (for private channels the bot is in).
2. Install the app to the workspace and copy the **bot token** (`xoxb-…`).
3. Set: `SLACK_BOT_TOKEN`.
4. Configure each Slack Source's `config`: `channel_ids: [...]`, optional `workspace` (label only).

*Note:* the same Slack app also carries the expert deep-link share (a UI concern, use case C) —
one app, two uses. Here the connector is read-only.

### Web / RSS — nothing to provision

Public feeds. Configure each Source's `config`: `feed_urls: [...]`. No credentials.

### LinkedIn / X — nothing to provision

Credential-free by design (D8). Create a Source of kind `linkedin-x-clip` (always
`read-as-needed`) to attribute clips to; then humans paste via `POST /api/connectors/clip`.
