"""The review round-trip's Google Docs seam (feedback-intake.md; domain model §1.15 Doc).

Item 7 / feedback-intake.md's round-trip is four Drive/Docs calls: push (``createDocFromHTML``) →
share (``shareFile``, role="writer" — reviewers edit the Doc directly, not just comment;
cmw-reviewer-can-edit-doc) → collect (``listComments``) → close
(``replyToComment``). The finalize render (D13, Item 5) already built the create-with-conversion
push (:class:`app.render.docs_export.HttpGoogleDocsClient`) over the same server-side incremental
OAuth grant as the Drive connector; :class:`HttpReviewDocsClient` reuses that exact push (no second
create-doc implementation) and adds the three calls finalize never needed: share, list comments,
and reply. ``get_document_html`` (an HTML export) is the one addition beyond feedback-intake.md
itself — it lets :mod:`app.review.collect` diff the Doc body against the frozen revision for the
assisted ingest preview (Item 7: "12 comments · 8 inline edits detected — fold these in?"),
carrying real structure (headings/paragraph breaks/emphasis — decision-structure-intake.md), not
just flattened text: an earlier version of this method exported ``mimeType=text/plain`` instead,
which destroyed that structure before the diff ever ran (see :mod:`app.review.structure`).

Note (cmw-reviewer-can-edit-doc, Hendo): a diff-detected edit is rewritten in voice rather than
applied verbatim, and has no comment thread to reply to (``comment_id=None`` — see
:mod:`app.review.collect`), so the reviewer gets no acknowledgement that their edit was seen. This
is a deliberate, accepted trade-off ("the lack of reviewer edits and comments [being acknowledged]
is OK for the org I work for") — not an oversight, and not something a future ticket should
silently "fix" by adding one without re-raising it as a product decision first.

Tests inject a fake behind :class:`ReviewDocsClient`; production wires :class:`HttpReviewDocsClient`
from the same ``GOOGLE_OAUTH_CLIENT_ID`` / ``_SECRET`` / ``_REFRESH_TOKEN`` settings.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from app.render.docs_export import DocRef, DocsExportError, HttpGoogleDocsClient

__all__ = ["CommentThread", "DocRef", "DocsExportError", "HttpReviewDocsClient", "ReviewDocsClient"]


class CommentThread(BaseModel):
    """One Google Docs comment thread (``listComments``) — the raw shape feedback-intake.md's
    "COLLECT" step pulls one row per item from."""

    comment_id: str
    author: str | None = None
    quoted_text: str | None = None  # the anchored text the comment is attached to, if any
    content: str  # the comment body — the actual ask
    resolved: bool = False


class ReviewDocsClient(Protocol):
    """Every Drive/Docs call the review round-trip needs. A real implementation is
    :class:`HttpReviewDocsClient`; tests inject a fake."""

    async def create_doc_from_html(
        self, title: str, html: str, *, description: str = "", parent_id: str | None = None
    ) -> DocRef: ...

    async def share_file(
        self, doc_id: str, *, emails: list[str] | None = None, role: str = "commenter"
    ) -> None:
        """``shareFile`` (feedback-intake.md): grant ``role`` to each email, or — with no emails —
        anyone-with-the-link (the caller decides; see :mod:`app.review.mint` for the external-share
        guardrail around confidential drafts)."""

    async def unshare_public(self, file_id: str) -> None:
        """Remove any 'anyone' public-read permission from the file/folder. Missing file/permission is normal (skip, per resilient-to-deletion)."""

    async def list_comments(self, doc_id: str) -> list[CommentThread]:
        """``listComments`` — every comment thread, author + quoted text + content (no filtering:
        "no silent drops" applies to collection too, feedback-intake.md)."""

    async def get_document_html(self, doc_id: str) -> str:
        """HTML export of the Doc body — the diff base for detecting inline edits alongside
        comments (Item 7's assisted-preview "N inline edits detected"), carrying the heading/
        paragraph/emphasis structure a plain-text export would destroy (decision-structure-
        intake.md; see :mod:`app.review.structure`)."""

    async def reply_to_comment(self, doc_id: str, comment_id: str, reply: str) -> None:
        """``replyToComment`` — close the loop: tell the reviewer what happened to their note."""


class HttpReviewDocsClient(HttpGoogleDocsClient):
    """Real :class:`ReviewDocsClient` over Drive v3, reusing the parent's OAuth token dance and
    ``create_doc_from_html`` push (the same ``createDocFromHTML`` mechanism finalize already uses)."""

    PERMISSIONS_URL = "https://www.googleapis.com/drive/v3/files/{file_id}/permissions"
    COMMENTS_URL = "https://www.googleapis.com/drive/v3/files/{file_id}/comments"
    REPLIES_URL = "https://www.googleapis.com/drive/v3/files/{file_id}/comments/{comment_id}/replies"
    EXPORT_URL = "https://www.googleapis.com/drive/v3/files/{file_id}/export"

    async def share_file(
        self, doc_id: str, *, emails: list[str] | None = None, role: str = "commenter"
    ) -> None:
        self._require_creds()
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            token = await self._access_token(client)
            headers = {"Authorization": f"Bearer {token}"}
            url = self.PERMISSIONS_URL.format(file_id=doc_id)
            grants = (
                [{"type": "user", "role": role, "emailAddress": email} for email in emails]
                if emails
                # No explicit reviewer list: anyone-with-the-link may comment. Callers deciding
                # whether that is appropriate for an EXTERNAL share is a product/guardrail
                # concern handled upstream in app.review.mint, not this transport-only client.
                else [{"type": "anyone", "role": role}]
            )
            for body in grants:
                # supportsAllDrives=true is required to grant permissions on a file living in a
                # Shared Drive (cmw-drive-piece-folders — review Docs may now be parented into the
                # piece's Drive folder); harmless/no-op for a plain My Drive file, so always sent.
                resp = await client.post(
                    url, params={"supportsAllDrives": "true"}, headers=headers, json=body
                )
                resp.raise_for_status()

    async def unshare_public(self, file_id: str) -> None:
        self._require_creds()
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            token = await self._access_token(client)
            headers = {"Authorization": f"Bearer {token}"}
            # List permissions, find 'anyone' type, delete it if present. Missing file -> 404 normal skip.
            list_url = self.PERMISSIONS_URL.format(file_id=file_id)
            try:
                resp = await client.get(
                    list_url,
                    headers=headers,
                    params={"supportsAllDrives": "true", "fields": "permissions(id,type)"},
                )
                resp.raise_for_status()
                for perm in resp.json().get("permissions", []):
                    if perm.get("type") == "anyone":
                        del_url = f"{list_url}/{perm['id']}"
                        del_resp = await client.delete(
                            del_url, headers=headers, params={"supportsAllDrives": "true"}
                        )
                        # 404 on delete is also normal (race or already gone)
                        if del_resp.status_code not in (200, 204, 404):
                            del_resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 404:
                    raise

    async def list_comments(self, doc_id: str) -> list[CommentThread]:
        self._require_creds()
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            token = await self._access_token(client)
            resp = await client.get(
                self.COMMENTS_URL.format(file_id=doc_id),
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "fields": "comments(id,author/displayName,quotedFileContent/value,content,resolved)"
                },
            )
            resp.raise_for_status()
            payload = resp.json()
        threads: list[CommentThread] = []
        for raw in payload.get("comments", []):
            author = (raw.get("author") or {}).get("displayName")
            quoted = (raw.get("quotedFileContent") or {}).get("value")
            threads.append(
                CommentThread(
                    comment_id=raw["id"],
                    author=author,
                    quoted_text=quoted,
                    content=raw.get("content", ""),
                    resolved=bool(raw.get("resolved", False)),
                )
            )
        return threads

    async def get_document_html(self, doc_id: str) -> str:
        self._require_creds()
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            token = await self._access_token(client)
            resp = await client.get(
                self.EXPORT_URL.format(file_id=doc_id),
                headers={"Authorization": f"Bearer {token}"},
                params={"mimeType": "text/html"},
            )
            resp.raise_for_status()
            return resp.text

    async def reply_to_comment(self, doc_id: str, comment_id: str, reply: str) -> None:
        self._require_creds()
        import httpx

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            token = await self._access_token(client)
            resp = await client.post(
                self.REPLIES_URL.format(file_id=doc_id, comment_id=comment_id),
                headers={"Authorization": f"Bearer {token}"},
                params={"fields": "id"},
                json={"content": reply},
            )
            resp.raise_for_status()
