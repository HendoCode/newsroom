"""Per-piece Google Drive folder scoped under one named My-Drive root (cmw-drive-named-folder-scoping).

Every Google artifact a piece produces — each review-round Doc (`app.review.mint`), the finalized
clean Doc + branded HTML/PDF (`app.render.step`), and publish's own re-rendered copies
(`app.publish.service`) — lands in ONE folder per piece, parented under a single specifically-
named folder in the app account's own My Drive, rather than loose at the Drive root. Sharing that
one root folder (which the app created itself under the `drive.file` scope) gives a reviewer
everything for that app in one place.

Folder creation is idempotent **by persisted pointer, never by search**: the folder id is recorded
on `Piece.drive_folder_id` the first time it's created and reused on every later call — finalize in
particular can run more than once per piece. This is the same trade-off `Piece.final_doc`/
`published_doc` already make for their own Drive pointers: no Drive search call, no race between
concurrent creates, at the cost of "a lost pointer means a second folder" (accepted — nothing here
reconciles that case; see README.md for what a future ticket would need to do instead). Only the
*root* is resolved by name (via `find_or_create_folder`) — and that lookup is cached once per
process, so a lost root pointer at worst recovers the same named folder rather than duplicating it.

Deliberately gated behind `Settings.google_drive_root_folder_name`, exactly like
`published_assets_bucket`: every caller must treat a blank name (or no client) as "behave exactly as
before this ticket" — no folder, current behavior — never a crash. No Shared Drive exists anymore,
so there is nothing to provision out-of-band: the app finds-or-creates the named root itself under
the `drive.file` scope (a root the human pre-creates by hand would be invisible to a
`drive.file`-scoped app, so the root MUST come from this find-or-create path, never a
human-provisioned id).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.models import Piece
from app.repositories import WorkStateStore

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
PUBLISHED_SUBFOLDER_NAME = "Published"


class DriveFolderError(RuntimeError):
    """The Drive root isn't configured, or a folder/file Drive call failed."""


@dataclass(frozen=True)
class DriveFileRef:
    file_id: str
    url: str


def folder_url(file_id: str) -> str:
    return f"https://drive.google.com/drive/folders/{file_id}"


class DriveFolderClient(Protocol):
    """The Drive calls a per-piece folder needs, beyond the existing create-Doc/share seam
    (`app.render.docs_export.GoogleDocsClient`). Tests inject a fake; production wires
    :class:`~app.drive.http_client.HttpDriveFolderClient`."""

    async def find_or_create_folder(
        self, name: str, *, parent_id: str = "root"
    ) -> DriveFileRef:
        """Find a folder named ``name`` that the app itself created under ``parent_id`` (default:
        My Drive root), else create it. Returns its id/link."""

    async def create_folder(self, name: str, *, parent_id: str) -> DriveFileRef:
        """Create a folder named ``name`` under ``parent_id`` and return its id/link."""

    async def upload_file(
        self, name: str, content: bytes, mime_type: str, *, parent_id: str
    ) -> DriveFileRef:
        """Upload ``content`` as an ordinary Drive file (never converted to a Google format —
        Hendo's call) named ``name`` under ``parent_id``, and return its id/link."""


class PieceDriveFolders:
    """Ensures the one Drive folder per piece (under the named My-Drive root) and its
    `Published/` subfolder.

    A blank ``root_folder_name`` (or a ``None`` client) makes :attr:`enabled` false and every
    ``ensure_*`` method a no-op returning ``None`` — the exact unset-configuration behavior this
    ticket must preserve.
    """

    def __init__(
        self,
        store: WorkStateStore,
        client: DriveFolderClient | None,
        root_folder_name: str,
    ) -> None:
        self.store = store
        self.client = client
        self.root_folder_name = root_folder_name
        self._root_folder_id: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.client is not None and self.root_folder_name)

    async def _root_folder(self) -> DriveFileRef:
        """Resolve the configured named root folder under My Drive, creating it on first use and
        caching the id for the lifetime of this instance — every piece reuses the same root."""
        assert self.client is not None
        if self._root_folder_id is None:
            root = await self.client.find_or_create_folder(self.root_folder_name)
            self._root_folder_id = root.file_id
        return DriveFileRef(self._root_folder_id, folder_url(self._root_folder_id))

    async def ensure_piece_folder(self, piece: Piece) -> DriveFileRef | None:
        """The piece's own folder — named after its slug (the same identity Git paths already key
        on, e.g. `drafts/<slug>/...`), created directly under the configured named root."""
        if not self.enabled:
            return None
        assert self.client is not None
        if piece.drive_folder_id:
            return DriveFileRef(
                piece.drive_folder_id, piece.drive_folder_url or folder_url(piece.drive_folder_id)
            )
        root = await self._root_folder()
        ref = await self.client.create_folder(piece.slug, parent_id=root.file_id)
        assert piece.id is not None
        await self.store.pieces.update(
            piece.id, {"drive_folder_id": ref.file_id, "drive_folder_url": ref.url}
        )
        return ref

    async def ensure_published_subfolder(self, piece: Piece) -> DriveFileRef | None:
        """The piece folder's `Published/` child — created (and persisted) the first time
        anything is published, reused after. Never re-parents the finalize originals living
        alongside it in the piece folder; publish always writes its own fresh copies here."""
        if not self.enabled:
            return None
        parent = await self.ensure_piece_folder(piece)
        if parent is None:
            return None
        assert self.client is not None
        if piece.drive_published_folder_id:
            return DriveFileRef(
                piece.drive_published_folder_id, folder_url(piece.drive_published_folder_id)
            )
        ref = await self.client.create_folder(PUBLISHED_SUBFOLDER_NAME, parent_id=parent.file_id)
        assert piece.id is not None
        await self.store.pieces.update(piece.id, {"drive_published_folder_id": ref.file_id})
        return ref