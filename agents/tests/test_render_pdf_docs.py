"""PDF (headless Chromium) and Google Docs export seams — guarded/mocked (D13, Item 5).

Neither external renderer is available in this test environment (no downloaded Chromium binary, no
Google OAuth credentials) — which is exactly the "Chromium/Docs calls can be mocked/guarded"
acceptance bar: these tests prove the *guard*, not a real Chromium/Drive round-trip.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.render.docs_export import DocsExportError, HttpGoogleDocsClient
from app.render.pdf import ChromiumPdfRenderer, PdfRenderError


@pytest.mark.asyncio
async def test_chromium_renderer_raises_a_clear_error_without_playwright() -> None:
    renderer = ChromiumPdfRenderer()
    with pytest.raises(PdfRenderError):
        await renderer.render("<html><body>hi</body></html>")


@pytest.mark.asyncio
async def test_docs_client_requires_credentials() -> None:
    client = HttpGoogleDocsClient("", "", "")
    with pytest.raises(DocsExportError):
        await client.create_doc_from_html("Title", "<h1>Hi</h1>")


def _mock_transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    """Same pattern as test_review_docs_client.py — pin every ``httpx.AsyncClient`` this module
    constructs to a ``MockTransport`` so assertions see the real outgoing request."""
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


@pytest.mark.asyncio
async def test_create_doc_from_html_with_no_parent_omits_parents_but_still_sends_supports_all_drives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pre-cmw-drive-piece-folders behavior: no ``parents`` in the metadata — the Doc lands at the
    Drive root, exactly as before this ticket. ``supportsAllDrives=true`` is sent unconditionally
    (documented as a no-op for a plain My Drive file) rather than branching on ``parent_id``."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        token_response = _fake_token_exchange(request)
        if token_response is not None:
            return token_response
        requests.append(request)
        return httpx.Response(200, json={"id": "doc-1", "webViewLink": "https://docs.google.com/x"})

    _mock_transport(monkeypatch, handler)
    client = HttpGoogleDocsClient("cid", "secret", "refresh")
    await client.create_doc_from_html("Title", "<h1>Hi</h1>", description="desc")

    assert len(requests) == 1
    req = requests[0]
    assert req.url.params.get("supportsAllDrives") == "true"
    body = req.content.decode("utf-8")
    metadata_json = body.split("\r\n\r\n", 1)[1].split("\r\n", 1)[0]
    metadata = json.loads(metadata_json)
    assert "parents" not in metadata


@pytest.mark.asyncio
async def test_create_doc_from_html_with_a_parent_sets_parents_and_supports_all_drives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cmw-drive-piece-folders: a ``parent_id`` puts the Doc in the piece's Shared Drive folder —
    confirmed live against a real Shared Drive during this ticket's verification that this needs
    ``supportsAllDrives=true`` (not assumed from the API reference alone)."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        token_response = _fake_token_exchange(request)
        if token_response is not None:
            return token_response
        requests.append(request)
        return httpx.Response(200, json={"id": "doc-1", "webViewLink": "https://docs.google.com/x"})

    _mock_transport(monkeypatch, handler)
    client = HttpGoogleDocsClient("cid", "secret", "refresh")
    await client.create_doc_from_html("Title", "<h1>Hi</h1>", parent_id="folder-1")

    assert len(requests) == 1
    req = requests[0]
    assert req.url.params.get("supportsAllDrives") == "true"
    body = req.content.decode("utf-8")
    metadata_json = body.split("\r\n\r\n", 1)[1].split("\r\n", 1)[0]
    metadata = json.loads(metadata_json)
    assert metadata["parents"] == ["folder-1"]
