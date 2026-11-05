"""Google Drive connector (D8) — pull transcripts from configured folders.

Reads configured Drive folder IDs (transcript folders) filtered by file type, exports each file's
text, and hands it to the lake. Authentication is **server-side only** (D14): the recommended
model is incremental OAuth on the SSO (NextAuth Google) identity — a server-held offline refresh
token exchanged for short-lived access tokens (open-decisions Item 6). No credentials live in the
Source registry doc or reach the client.

Seams:
- ``DriveClient`` — the Drive API seam (``list_files`` + ``export_text``). Tests inject a fake.
- ``HttpDriveClient`` — the real client (httpx against the Drive v3 + OAuth token endpoints),
  built from the server-side OAuth settings.

Config (Source.config): ``folder_ids: list[str]`` (transcript folders to watch), optional
``mime_types: list[str]`` (file-type filter; defaults to Google Docs + plain text). No credentials.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from app.connectors.base import ConnectorError, RawItem, SourceConnector
from app.models.common import utcnow
from app.models.source import Source, SourceKind

# Default transcript file types: native Google Docs + plain text. Overridable per source.
_DEFAULT_MIME_TYPES = ["application/vnd.google-apps.document", "text/plain"]


@dataclass
class DriveFile:
    """A Drive file's listing metadata (a thin projection of the API's file resource)."""

    id: str
    name: str
    mime_type: str
    modified_time: datetime | None = None
    owners: list[str] = field(default_factory=list)
    web_view_link: str | None = None


class DriveClient(Protocol):
    """List files in a folder (filtered by type + modified-after) and export a file's text."""

    async def list_files(
        self,
        folder_id: str,
        *,
        mime_types: list[str],
        modified_after: datetime | None,
    ) -> list[DriveFile]: ...

    async def export_text(self, file_id: str, mime_type: str) -> str: ...


class GoogleDriveConnector(SourceConnector):
    """Pull transcript files from the folders listed in a Source's ``config.folder_ids``."""

    kind = SourceKind.gdrive

    def __init__(self, client: DriveClient) -> None:
        self.client = client

    async def fetch(self, source: Source, *, lookback_days: int) -> list[RawItem]:
        folder_ids = source.config.get("folder_ids", [])
        if not isinstance(folder_ids, list):
            raise ConnectorError("gdrive config.folder_ids must be a list of folder ids")
        mime_types = source.config.get("mime_types") or _DEFAULT_MIME_TYPES
        if not isinstance(mime_types, list):
            raise ConnectorError("gdrive config.mime_types must be a list of MIME types")

        modified_after = utcnow() - _days(lookback_days)

        pulled: list[RawItem] = []
        for folder_id in folder_ids:
            files = await self.client.list_files(
                str(folder_id), mime_types=mime_types, modified_after=modified_after
            )
            for f in files:
                text = await self.client.export_text(f.id, f.mime_type)
                if not text.strip():
                    continue
                body = f"{f.name}\n\n{text}" if f.name else text
                pulled.append(
                    RawItem(
                        raw_content=body,
                        external_id=f.id,
                        content_date=f.modified_time,
                        author=f.owners[0] if f.owners else None,
                        title=f.name,
                        url=f.web_view_link,
                        extra={"folder_id": folder_id, "mime_type": f.mime_type},
                    )
                )
        return pulled


def _days(n: int):
    from datetime import timedelta

    return timedelta(days=n)


class HttpDriveClient:
    """Real ``DriveClient`` over Drive v3 + Google OAuth. All credentials are server-side (D14).

    Uses the recommended incremental-OAuth model: a server-held offline **refresh token** is
    exchanged for a short-lived access token, which authorizes ``files.list`` / ``files.export``.
    """

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    DRIVE_URL = "https://www.googleapis.com/drive/v3"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        timeout: float = 30.0,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self.timeout = timeout

    def _require_creds(self) -> None:
        if not (self._client_id and self._client_secret and self._refresh_token):
            raise ConnectorError(
                "Google Drive OAuth not configured (GOOGLE_OAUTH_CLIENT_ID / _SECRET / "
                "_REFRESH_TOKEN); provision incremental OAuth (see app/connectors/README.md)"
            )

    async def _access_token(self, client: Any) -> str:
        resp = await client.post(
            self.TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        return str(resp.json()["access_token"])

    async def list_files(
        self,
        folder_id: str,
        *,
        mime_types: list[str],
        modified_after: datetime | None,
    ) -> list[DriveFile]:
        self._require_creds()
        import httpx

        clauses = [f"'{folder_id}' in parents", "trashed = false"]
        if mime_types:
            mime_q = " or ".join(f"mimeType = '{m}'" for m in mime_types)
            clauses.append(f"({mime_q})")
        if modified_after is not None:
            iso = modified_after.replace(tzinfo=UTC).isoformat()
            clauses.append(f"modifiedTime > '{iso}'")
        query = " and ".join(clauses)

        files: list[DriveFile] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            token = await self._access_token(client)
            headers = {"Authorization": f"Bearer {token}"}
            page_token: str | None = None
            while True:
                params: dict[str, Any] = {
                    "q": query,
                    "fields": "nextPageToken, files(id, name, mimeType, modifiedTime, "
                    "owners(emailAddress), webViewLink)",
                    "pageSize": 100,
                }
                if page_token:
                    params["pageToken"] = page_token
                resp = await client.get(f"{self.DRIVE_URL}/files", params=params, headers=headers)
                resp.raise_for_status()
                body = resp.json()
                for f in body.get("files", []):
                    files.append(
                        DriveFile(
                            id=f["id"],
                            name=f.get("name", ""),
                            mime_type=f.get("mimeType", ""),
                            modified_time=_parse_iso(f.get("modifiedTime")),
                            owners=[
                                o["emailAddress"]
                                for o in f.get("owners", [])
                                if "emailAddress" in o
                            ],
                            web_view_link=f.get("webViewLink"),
                        )
                    )
                page_token = body.get("nextPageToken")
                if not page_token:
                    break
        return files

    async def export_text(self, file_id: str, mime_type: str) -> str:
        self._require_creds()
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            token = await self._access_token(client)
            headers = {"Authorization": f"Bearer {token}"}
            if mime_type == "application/vnd.google-apps.document":
                # Native Google Doc → export as plain text.
                resp = await client.get(
                    f"{self.DRIVE_URL}/files/{file_id}/export",
                    params={"mimeType": "text/plain"},
                    headers=headers,
                )
            else:
                # Binary/text file → download media directly.
                resp = await client.get(
                    f"{self.DRIVE_URL}/files/{file_id}",
                    params={"alt": "media"},
                    headers=headers,
                )
            resp.raise_for_status()
            return resp.text


def _parse_iso(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        # Python 3.12 fromisoformat parses a trailing "Z"; normalize to naive-UTC (store convention).
        return datetime.fromisoformat(text).astimezone(UTC).replace(tzinfo=None)
    except ValueError:
        return None
