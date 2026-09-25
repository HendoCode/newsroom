"""The "clean Google Doc" finalize output (D13, Item 5; domain model §1.15 Doc).

Item 5: "Clean Google Doc = the semantic content pushed to Docs (styling stripped, since Docs
strips styling anyway) — the same push path the review round-trip already uses." This mirrors the
server-side-only OAuth pattern the Drive connector already established
(``app/connectors/gdrive.py``: a server-held offline refresh token exchanged for a short-lived
access token, D14) rather than inventing a second credential story — the same
``GOOGLE_OAUTH_CLIENT_ID`` / ``_SECRET`` / ``_REFRESH_TOKEN`` settings authorize this call.

The Doc gets only the semantic content (title + stripped body) — never the decorative branded
wrapper, since Docs strips inline styling anyway. Provenance (source revision + template version)
is recorded on the Drive file's ``description`` metadata instead of inside the document body, so
the "clean" Doc content stays exactly that.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol


class DocsExportError(RuntimeError):
    """Google Docs credentials are missing, or the create-doc call failed."""


@dataclass(frozen=True)
class DocRef:
    doc_id: str
    url: str


class GoogleDocsClient(Protocol):
    """Create a native Google Doc from semantic HTML. Tests inject a fake; production wires
    :class:`HttpGoogleDocsClient`."""

    async def create_doc_from_html(
        self, title: str, html: str, *, description: str = "", parent_id: str | None = None
    ) -> DocRef:
        """``parent_id`` (cmw-drive-piece-folders), when given, is the piece's Shared Drive
        folder id — the Doc lands there instead of loose at the Drive root."""


class HttpGoogleDocsClient:
    """Real :class:`GoogleDocsClient` over Drive v3's create-with-conversion upload: a multipart
    upload whose ``mimeType`` is ``application/vnd.google-apps.document`` converts the HTML body
    straight into a native Doc (the same ``createDocFromHTML`` mechanism the review round-trip
    relies on) in one call — no separate convert step.
    """

    TOKEN_URL = "https://oauth2.googleapis.com/token"
    UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        *,
        timeout: float = 30.0,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self.timeout = timeout

    def _require_creds(self) -> None:
        if not (self._client_id and self._client_secret and self._refresh_token):
            raise DocsExportError(
                "Google Docs export not configured (GOOGLE_OAUTH_CLIENT_ID / _SECRET / "
                "_REFRESH_TOKEN) — provision the same incremental OAuth grant as the Drive "
                "connector (see app/connectors/README.md)"
            )

    async def _access_token(self, client) -> str:
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

    async def create_doc_from_html(
        self, title: str, html: str, *, description: str = "", parent_id: str | None = None
    ) -> DocRef:
        self._require_creds()
        import httpx

        metadata: dict[str, object] = {
            "name": title,
            "mimeType": "application/vnd.google-apps.document",
            "description": description,
        }
        if parent_id:
            metadata["parents"] = [parent_id]
        boundary = "cmw-finalize-boundary"
        body = (
            f"--{boundary}\r\n"
            "Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{json.dumps(metadata)}\r\n"
            f"--{boundary}\r\n"
            "Content-Type: text/html; charset=UTF-8\r\n\r\n"
            f"{html}\r\n"
            f"--{boundary}--"
        )
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            token = await self._access_token(client)
            resp = await client.post(
                self.UPLOAD_URL,
                # supportsAllDrives=true is required once `parent_id` points into a Shared Drive
                # (cmw-drive-piece-folders) — harmless/no-op otherwise, so it's always sent rather
                # than branching on whether a parent was given (confirmed against the live Drive
                # API during this ticket's verification, not assumed).
                params={"uploadType": "multipart", "supportsAllDrives": "true", "fields": "id,webViewLink"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": f"multipart/related; boundary={boundary}",
                },
                content=body.encode("utf-8"),
            )
            resp.raise_for_status()
            payload = resp.json()
        doc_id = payload["id"]
        url = payload.get("webViewLink") or f"https://docs.google.com/document/d/{doc_id}/edit"
        return DocRef(doc_id=doc_id, url=url)
