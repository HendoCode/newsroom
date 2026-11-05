"""Google Drive connector tests (D8).

Drives ``GoogleDriveConnector`` end-to-end into the in-memory lake with a fake ``DriveClient`` (the
Drive API seam, mocked). Proves folder listing → text export → lake, the file-type filter passthrough,
the modified-after window, provenance metadata, and idempotent re-refresh. OAuth creds are
server-side and never appear here.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.connectors import DriveFile, GoogleDriveConnector
from app.connectors.base import ConnectorError
from app.lake import ContentLake
from app.models.common import utcnow
from app.models.source import Source, SourceClassification, SourceKind


class FakeDriveClient:
    """A ``DriveClient`` serving canned files per folder + canned text per file id."""

    def __init__(
        self, files_by_folder: dict[str, list[DriveFile]], text_by_id: dict[str, str]
    ) -> None:
        self.files_by_folder = files_by_folder
        self.text_by_id = text_by_id
        self.list_calls: list[tuple[str, list[str], datetime | None]] = []

    async def list_files(self, folder_id, *, mime_types, modified_after):
        self.list_calls.append((folder_id, mime_types, modified_after))
        return self.files_by_folder.get(folder_id, [])

    async def export_text(self, file_id: str, mime_type: str) -> str:
        return self.text_by_id.get(file_id, "")


def _source(**config) -> Source:
    return Source(
        display_name="transcripts",
        kind=SourceKind.gdrive,
        classification=SourceClassification.scraped_periodically,
        config=config,
        id="src-gdrive",
    )


async def test_gdrive_ingests_transcripts(lake: ContentLake) -> None:
    files = [
        DriveFile(
            id="f1",
            name="Webinar 2026-07 transcript",
            mime_type="application/vnd.google-apps.document",
            modified_time=utcnow() - timedelta(days=2),
            owners=["alex@company.com"],
            web_view_link="https://docs.google.com/d/f1",
        )
    ]
    client = FakeDriveClient(
        {"folder-A": files}, {"f1": "We discussed cold storage pricing at length."}
    )
    connector = GoogleDriveConnector(client)
    result = await connector.refresh(_source(folder_ids=["folder-A"]), lake)

    assert result.ingested == 1
    stored = await lake.get(result.item_ids[0])
    assert stored is not None
    assert stored.source_id == "src-gdrive"
    assert stored.classification == SourceClassification.scraped_periodically.value
    assert stored.metadata.title == "Webinar 2026-07 transcript"
    assert stored.metadata.author == "alex@company.com"
    assert stored.metadata.url == "https://docs.google.com/d/f1"
    assert stored.metadata.extra["folder_id"] == "folder-A"
    assert stored.metadata.extra["external_id"] == "f1"
    # File name is prepended to the exported body.
    assert "Webinar 2026-07 transcript" in stored.raw_content
    assert "cold storage pricing" in stored.raw_content
    assert stored.embedding is not None and stored.keyword_tokens


async def test_gdrive_passes_file_type_filter_and_window(lake: ContentLake) -> None:
    client = FakeDriveClient({"folder-A": []}, {})
    connector = GoogleDriveConnector(client)
    await connector.refresh(
        _source(folder_ids=["folder-A"], mime_types=["text/plain"]), lake, lookback_days=14
    )
    folder_id, mime_types, modified_after = client.list_calls[0]
    assert folder_id == "folder-A"
    assert mime_types == ["text/plain"]  # explicit file-type filter passed through
    assert modified_after is not None  # window translated to a modified-after bound


async def test_gdrive_default_mime_types(lake: ContentLake) -> None:
    client = FakeDriveClient({"folder-A": []}, {})
    connector = GoogleDriveConnector(client)
    await connector.refresh(_source(folder_ids=["folder-A"]), lake)
    _, mime_types, _ = client.list_calls[0]
    assert "application/vnd.google-apps.document" in mime_types


async def test_gdrive_skips_empty_export(lake: ContentLake) -> None:
    files = [DriveFile(id="f1", name="empty", mime_type="text/plain")]
    client = FakeDriveClient({"folder-A": files}, {"f1": "   "})
    connector = GoogleDriveConnector(client)
    result = await connector.refresh(_source(folder_ids=["folder-A"]), lake)
    assert result.ingested == 0


async def test_gdrive_refresh_is_idempotent(lake: ContentLake) -> None:
    files = [DriveFile(id="f1", name="doc", mime_type="text/plain")]
    client = FakeDriveClient({"folder-A": files}, {"f1": "content here"})
    connector = GoogleDriveConnector(client)
    src = _source(folder_ids=["folder-A"])
    await connector.refresh(src, lake)
    second = await connector.refresh(src, lake)
    assert second.ingested == 0 and second.skipped == 1
    assert await lake.count() == 1


async def test_gdrive_bad_config_raises() -> None:
    connector = GoogleDriveConnector(FakeDriveClient({}, {}))
    with pytest.raises(ConnectorError):
        await connector.fetch(_source(folder_ids="folder-A"), lookback_days=7)
