"""HttpDriveFolderClient credential guard + real-request-shape tests (cmw-drive-piece-folders).

Same MockTransport discipline as test_review_docs_client.py: assert on the real outgoing request
(method/path/query params/body) rather than a stubbed return value — the level of test that would
have caught a missing ``supportsAllDrives`` param, which the Drive API reference documents as
required for any write against a Shared Drive file
(https://developers.google.com/workspace/drive/api/reference/rest/v3/files/create and
.../permissions/create — confirmed during this ticket, not assumed) and which this repo also
confirmed live against a real Shared Drive (see the PR description for the verification evidence).
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.drive.http_client import HttpDriveFolderClient
from app.render.docs_export import DocsExportError


@pytest.fixture
def client() -> HttpDriveFolderClient:
    return HttpDriveFolderClient("", "", "")


def _mock_transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    base_client = httpx.AsyncClient

    class _TransportPinnedClient(base_client):
        def __init__(self, *args, **kwargs) -> None:
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _TransportPinnedClient)


def _fake_token_exchange(request: httpx.Request) -> httpx.Response | None:
    if request.url.host == "oauth2.googleapis.com":
        return httpx.Response(200, json={"access_token": "test-token"})
    return None


async def test_create_folder_requires_credentials(client: HttpDriveFolderClient) -> None:
    with pytest.raises(DocsExportError):
        await client.create_folder("my-piece", parent_id="drive-1")


async def test_upload_file_requires_credentials(client: HttpDriveFolderClient) -> None:
    with pytest.raises(DocsExportError):
        await client.upload_file("branded.html", b"<html></html>", "text/html", parent_id="folder-1")


async def test_create_folder_sends_the_right_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        token_response = _fake_token_exchange(request)
        if token_response is not None:
            return token_response
        requests.append(request)
        return httpx.Response(
            200, json={"id": "folder-1", "webViewLink": "https://drive.google.com/drive/folders/folder-1"}
        )

    _mock_transport(monkeypatch, handler)
    client = HttpDriveFolderClient("cid", "secret", "refresh")
    ref = await client.create_folder("my-piece", parent_id="drive-1")

    assert ref.file_id == "folder-1"
    assert ref.url == "https://drive.google.com/drive/folders/folder-1"
    assert len(requests) == 1
    req = requests[0]
    assert req.method == "POST"
    assert req.url.path == "/drive/v3/files"
    assert req.url.params.get("supportsAllDrives") == "true"
    assert req.url.params.get("fields")
    assert json.loads(req.content) == {
        "name": "my-piece",
        "mimeType": "application/vnd.google-apps.folder",
        "parents": ["drive-1"],
    }


async def test_find_or_create_returns_an_existing_root_via_files_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        token_response = _fake_token_exchange(request)
        if token_response is not None:
            return token_response
        requests.append(request)
        assert request.method == "GET"
        return httpx.Response(
            200,
            json={
                "files": [
                    {
                        "id": "root-1",
                        "webViewLink": "https://drive.google.com/drive/folders/root-1",
                    }
                ]
            },
        )

    _mock_transport(monkeypatch, handler)
    client = HttpDriveFolderClient("cid", "secret", "refresh")
    ref = await client.find_or_create_folder("content-machine")

    assert ref.file_id == "root-1"
    assert ref.url == "https://drive.google.com/drive/folders/root-1"
    assert len(requests) == 1
    req = requests[0]
    assert req.url.path == "/drive/v3/files"
    q = req.url.params.get("q")
    assert "name = 'content-machine'" in q
    assert "mimeType = 'application/vnd.google-apps.folder'" in q
    assert "trashed = false" in q
    assert req.url.params.get("fields")


async def test_find_or_create_creates_the_root_when_the_list_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        token_response = _fake_token_exchange(request)
        if token_response is not None:
            return token_response
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"files": []})
        return httpx.Response(
            200, json={"id": "root-1", "webViewLink": "https://drive.google.com/drive/folders/root-1"}
        )

    _mock_transport(monkeypatch, handler)
    client = HttpDriveFolderClient("cid", "secret", "refresh")
    ref = await client.find_or_create_folder("content-machine")

    assert ref.file_id == "root-1"
    # A list then a create — the create is parented at the My Drive root.
    assert [r.method for r in requests] == ["GET", "POST"]
    create_req = requests[1]
    assert json.loads(create_req.content) == {
        "name": "content-machine",
        "mimeType": "application/vnd.google-apps.folder",
        "parents": ["root"],
    }


async def test_find_or_create_requires_credentials(client: HttpDriveFolderClient) -> None:
    with pytest.raises(DocsExportError):
        await client.find_or_create_folder("content-machine")


async def test_create_folder_falls_back_to_a_constructed_url_without_webviewlink(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        token_response = _fake_token_exchange(request)
        if token_response is not None:
            return token_response
        return httpx.Response(200, json={"id": "folder-1"})

    _mock_transport(monkeypatch, handler)
    client = HttpDriveFolderClient("cid", "secret", "refresh")
    ref = await client.create_folder("my-piece", parent_id="drive-1")

    assert ref.url == "https://drive.google.com/drive/folders/folder-1"


async def test_upload_file_sends_multipart_metadata_and_raw_content(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        token_response = _fake_token_exchange(request)
        if token_response is not None:
            return token_response
        requests.append(request)
        return httpx.Response(
            200, json={"id": "file-1", "webViewLink": "https://drive.google.com/file/d/file-1/view"}
        )

    _mock_transport(monkeypatch, handler)
    client = HttpDriveFolderClient("cid", "secret", "refresh")
    pdf_bytes = b"%PDF-1.4 not a real pdf but binary-safe\x00\x01\x02"
    ref = await client.upload_file("branded.pdf", pdf_bytes, "application/pdf", parent_id="folder-1")

    assert ref.file_id == "file-1"
    assert len(requests) == 1
    req = requests[0]
    assert req.method == "POST"
    assert req.url.path == "/upload/drive/v3/files"
    assert req.url.params.get("uploadType") == "multipart"
    assert req.url.params.get("supportsAllDrives") == "true"
    assert req.url.params.get("fields")

    body = req.content
    assert pdf_bytes in body  # the binary content survives the multipart assembly untouched
    metadata_json = body.split(b"\r\n\r\n", 1)[1].split(b"\r\n", 1)[0]
    assert json.loads(metadata_json) == {"name": "branded.pdf", "parents": ["folder-1"]}
    assert b"Content-Type: application/pdf" in body
