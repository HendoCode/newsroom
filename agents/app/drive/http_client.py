"""Real :class:`~app.drive.folder.DriveFolderClient` over Drive v3 (cmw-drive-piece-folders).

Extends :class:`~app.render.docs_export.HttpGoogleDocsClient` to reuse its OAuth token dance
(same server-side `GOOGLE_OAUTH_CLIENT_ID`/`_SECRET`/`_REFRESH_TOKEN` grant — no new credential,
see README.md) rather than duplicating it. Adds folder creation and ordinary-file upload, both
Shared-Drive-aware: every write here passes `supportsAllDrives=true`, required whenever the target
(or its parent) lives in a Shared Drive rather than a My Drive
(https://developers.google.com/workspace/drive/api/reference/rest/v3/files/create) — confirmed
against the live API during this ticket's verification (see the PR description), not assumed.
"""

from __future__ import annotations

import json

from app.drive.folder import FOLDER_MIME_TYPE, DriveFileRef, folder_url
from app.render.docs_export import HttpGoogleDocsClient


class HttpDriveFolderClient(HttpGoogleDocsClient):
    FILES_URL = "https://www.googleapis.com/drive/v3/files"

    async def find_or_create_folder(
        self, name: str, *, parent_id: str = "root"
    ) -> DriveFileRef:
        """Find a folder named ``name`` the app itself created (a My Drive listing, so under
        the ``drive.file`` scope only files this app created are visible/candidates), else
        create it under ``parent_id`` (default My Drive root). The root is idempotent-by-name,
        unlike piece folders (which are idempotent-by-persisted-pointer)."""
        self._require_creds()
        import httpx

        q = (
            f"name = '{name}' and mimeType = '{FOLDER_MIME_TYPE}' "
            "and trashed = false"
        )
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            token = await self._access_token(client)
            resp = await client.get(
                self.FILES_URL,
                params={"q": q, "fields": "files(id, webViewLink)"},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            payload = resp.json()
        files = payload.get("files") or []
        if files:
            file_id = files[0]["id"]
            url = files[0].get("webViewLink") or folder_url(file_id)
            return DriveFileRef(file_id=file_id, url=url)
        return await self.create_folder(name, parent_id=parent_id)

    async def create_folder(self, name: str, *, parent_id: str) -> DriveFileRef:
        self._require_creds()
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            token = await self._access_token(client)
            resp = await client.post(
                self.FILES_URL,
                params={"supportsAllDrives": "true", "fields": "id,webViewLink"},
                headers={"Authorization": f"Bearer {token}"},
                json={"name": name, "mimeType": FOLDER_MIME_TYPE, "parents": [parent_id]},
            )
            resp.raise_for_status()
            payload = resp.json()
        file_id = payload["id"]
        url = payload.get("webViewLink") or f"https://drive.google.com/drive/folders/{file_id}"
        return DriveFileRef(file_id=file_id, url=url)

    async def upload_file(
        self, name: str, content: bytes, mime_type: str, *, parent_id: str
    ) -> DriveFileRef:
        self._require_creds()
        import httpx

        metadata = {"name": name, "parents": [parent_id]}
        boundary = "cmw-drive-folder-boundary"
        body = (
            f"--{boundary}\r\n"
            "Content-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{json.dumps(metadata)}\r\n"
            f"--{boundary}\r\n"
            f"Content-Type: {mime_type}\r\n\r\n"
        ).encode("utf-8")
        body += content
        body += f"\r\n--{boundary}--".encode("utf-8")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            token = await self._access_token(client)
            resp = await client.post(
                self.UPLOAD_URL,
                params={
                    "uploadType": "multipart",
                    "supportsAllDrives": "true",
                    "fields": "id,webViewLink",
                },
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": f"multipart/related; boundary={boundary}",
                },
                content=body,
            )
            resp.raise_for_status()
            payload = resp.json()
        file_id = payload["id"]
        url = payload.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"
        return DriveFileRef(file_id=file_id, url=url)
