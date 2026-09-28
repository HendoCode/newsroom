"""PieceDriveFolders: named-root resolution + idempotent per-piece folder + Published/ subfolder
(cmw-drive-named-folder-scoping).

Drive itself is faked — these tests cover the resolution/gating/lookup logic that's independent of
the real API (covered instead by test_drive_http_client.py's request-shape tests and the original
ticket's live verification against a real Drive).
"""

from __future__ import annotations

import pytest

from app.drive.folder import DriveFileRef, PieceDriveFolders
from app.models import Piece
from app.repositories import WorkStateStore

ROOT_NAME = "newsroom"


class FakeDriveClient:
    def __init__(self) -> None:
        self.created: list[tuple[str, str]] = []  # (name, parent_id)
        self.root_searches: list[str] = []  # names passed to find_or_create_folder
        self._next_id = 1
        self._by_name: dict[str, str] = {}

    async def find_or_create_folder(self, name: str, *, parent_id: str = "root") -> DriveFileRef:
        # First call for a given name creates a fresh id (as if the app just found nothing and
        # created it); the caller (PieceDriveFolders) caches the result so it is never called
        # again for the same instance.
        self.root_searches.append(name)
        if name in self._by_name:
            return DriveFileRef(
                self._by_name[name],
                f"https://drive.google.com/drive/folders/{self._by_name[name]}",
            )
        return await self.create_folder(name, parent_id=parent_id)

    async def create_folder(self, name: str, *, parent_id: str) -> DriveFileRef:
        self.created.append((name, parent_id))
        file_id = f"folder-{self._next_id}"
        self._next_id += 1
        self._by_name[name] = file_id
        return DriveFileRef(file_id=file_id, url=f"https://drive.google.com/drive/folders/{file_id}")

    async def upload_file(self, name, content, mime_type, *, parent_id):  # pragma: no cover - unused here
        raise NotImplementedError


async def _piece(store: WorkStateStore, *, slug: str = "the-board-on-the-wall") -> Piece:
    return await store.pieces.insert(Piece(slug=slug, voice="demo-dana"))


async def test_disabled_when_root_folder_name_is_blank(store: WorkStateStore) -> None:
    folders = PieceDriveFolders(store, FakeDriveClient(), "")
    piece = await _piece(store)

    assert folders.enabled is False
    assert await folders.ensure_piece_folder(piece) is None
    assert await folders.ensure_published_subfolder(piece) is None


async def test_disabled_when_client_is_none(store: WorkStateStore) -> None:
    folders = PieceDriveFolders(store, None, ROOT_NAME)
    piece = await _piece(store)

    assert folders.enabled is False
    assert await folders.ensure_piece_folder(piece) is None


async def test_root_folder_is_resolved_once_and_reused(store: WorkStateStore) -> None:
    """The named root is found-or-created once per PieceDriveFolders instance (cached), so a
    second piece on the same instance reuses it without another search/create."""
    client = FakeDriveClient()
    folders = PieceDriveFolders(store, client, ROOT_NAME)
    p1 = await _piece(store, slug="first")
    p2 = await _piece(store, slug="second")

    await folders.ensure_piece_folder(p1)
    await folders.ensure_piece_folder(p2)

    # Root resolved exactly once; each piece folder parents under it (not under the Drive root).
    assert client.root_searches == [ROOT_NAME]
    assert client.created[0] == (ROOT_NAME, "root")
    assert client.created[1] == ("first", "folder-1")  # root's id, resolved once
    assert client.created[2] == ("second", "folder-1")


async def test_ensure_piece_folder_creates_once_named_after_the_slug(store: WorkStateStore) -> None:
    client = FakeDriveClient()
    folders = PieceDriveFolders(store, client, ROOT_NAME)
    piece = await _piece(store, slug="my-great-piece")

    ref = await folders.ensure_piece_folder(piece)

    assert ref is not None
    assert client.created == [(ROOT_NAME, "root"), ("my-great-piece", "folder-1")]
    updated = await store.pieces.get(piece.id)
    assert updated is not None
    assert updated.drive_folder_id == ref.file_id
    assert updated.drive_folder_url == ref.url


async def test_ensure_piece_folder_is_idempotent_across_calls_and_instances(store: WorkStateStore) -> None:
    """Finalize can run more than once per piece — the second call (even through a brand-new
    PieceDriveFolders instance, mirroring FinalizeStep building one fresh per run) must reuse the
    pointer already persisted on the Piece rather than creating a second folder."""
    client = FakeDriveClient()
    piece = await _piece(store)

    first = await PieceDriveFolders(store, client, ROOT_NAME).ensure_piece_folder(piece)
    refreshed = await store.pieces.get(piece.id)
    assert refreshed is not None
    second = await PieceDriveFolders(store, client, ROOT_NAME).ensure_piece_folder(refreshed)

    # Two instances each resolve the (created) root once by name, but never a second piece folder.
    assert len(client.created) == 2  # root + one piece folder
    assert first == second


async def test_ensure_published_subfolder_creates_the_piece_folder_first(store: WorkStateStore) -> None:
    client = FakeDriveClient()
    folders = PieceDriveFolders(store, client, ROOT_NAME)
    piece = await _piece(store, slug="my-great-piece")

    ref = await folders.ensure_published_subfolder(piece)

    assert ref is not None
    assert len(client.created) == 3  # root + piece folder + Published
    piece_folder_name, piece_folder_parent = client.created[1]
    subfolder_name, subfolder_parent = client.created[2]
    assert (piece_folder_name, piece_folder_parent) == ("my-great-piece", "folder-1")
    assert subfolder_name == "Published"

    updated = await store.pieces.get(piece.id)
    assert updated is not None
    assert updated.drive_folder_id is not None
    assert subfolder_parent == updated.drive_folder_id  # Published nests under the piece folder
    assert updated.drive_published_folder_id == ref.file_id


async def test_ensure_published_subfolder_reuses_an_existing_piece_folder(store: WorkStateStore) -> None:
    client = FakeDriveClient()
    folders = PieceDriveFolders(store, client, ROOT_NAME)
    piece = await _piece(store)

    piece_folder = await folders.ensure_piece_folder(piece)
    refreshed = await store.pieces.get(piece.id)
    assert refreshed is not None
    await folders.ensure_published_subfolder(refreshed)

    # Exactly three creates total: root, the piece folder (already created above), Published.
    assert len(client.created) == 3
    assert client.created[2] == ("Published", piece_folder.file_id)


async def test_ensure_published_subfolder_is_idempotent(store: WorkStateStore) -> None:
    client = FakeDriveClient()
    folders = PieceDriveFolders(store, client, ROOT_NAME)
    piece = await _piece(store)

    first = await folders.ensure_published_subfolder(piece)
    refreshed = await store.pieces.get(piece.id)
    assert refreshed is not None
    second = await folders.ensure_published_subfolder(refreshed)

    assert len(client.created) == 3  # root + piece folder + Published, never repeated
    assert first == second