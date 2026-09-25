"""A plain Drive file pointer (cmw-drive-piece-folders).

Distinct from `app.models.review_round.DocRef`: that shape carries a Google Doc's `share_mode`,
which doesn't apply to an ordinary uploaded file (a branded HTML/PDF upload, never converted to a
Google format) — this is just an id + link.
"""

from __future__ import annotations

from pydantic import BaseModel


class DriveFileRef(BaseModel):
    file_id: str | None = None
    url: str | None = None
