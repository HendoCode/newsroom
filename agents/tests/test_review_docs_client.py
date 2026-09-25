"""HttpReviewDocsClient credential guard + real-request-shape tests (feedback-intake.md).

No real Drive/Docs credentials are available in this test environment — the credential-guard
tests below prove the guard every method shares with the inherited ``create_doc_from_html`` (the
"Docs API calls can be mocked/guarded" acceptance bar), not a real HTTP round-trip.

The request-shape tests route ``httpx.AsyncClient`` through an ``httpx.MockTransport`` and assert
on the actual outgoing request (method/path/query params/body) rather than a mocked return value.
This is the level of test that would have caught ``reply_to_comment``'s missing ``fields`` query
param: Drive v3's ``comments``/``replies`` (excluding ``delete``) resources 400 without one
("The 'fields' parameter is required for this method", confirmed live 2026-08-08), while
``permissions`` and ``files.export`` have documented defaults and need no such param — a mock that
only stubs a return value can't distinguish "sent a valid request" from "sent a request Drive
would reject."
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.render.docs_export import DocsExportError
from app.review.docs_client import HttpReviewDocsClient


@pytest.fixture
def client() -> HttpReviewDocsClient:
    return HttpReviewDocsClient("", "", "")


def _mock_transport(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    """Make every ``httpx.AsyncClient`` the module under test constructs use a MockTransport
    wired to ``handler``, so real request objects (never a stubbed return value) reach the
    assertions below."""
    transport = httpx.MockTransport(handler)
    base_client = httpx.AsyncClient

    class _TransportPinnedClient(base_client):
        def __init__(self, *args, **kwargs) -> None:
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _TransportPinnedClient)


def _fake_token_exchange(request: httpx.Request) -> httpx.Response | None:
    """Every real method here first exchanges the refresh token for an access token; stub that
    leg so it never reaches the network, and let callers handle only the call under test."""
    if request.url.host == "oauth2.googleapis.com":
        return httpx.Response(200, json={"access_token": "test-token"})
    return None


async def test_share_file_requires_credentials(client: HttpReviewDocsClient) -> None:
    with pytest.raises(DocsExportError):
        await client.share_file("doc-1")


async def test_list_comments_requires_credentials(client: HttpReviewDocsClient) -> None:
    with pytest.raises(DocsExportError):
        await client.list_comments("doc-1")


async def test_get_document_html_requires_credentials(client: HttpReviewDocsClient) -> None:
    with pytest.raises(DocsExportError):
        await client.get_document_html("doc-1")


async def test_reply_to_comment_requires_credentials(client: HttpReviewDocsClient) -> None:
    with pytest.raises(DocsExportError):
        await client.reply_to_comment("doc-1", "comment-1", "thanks")


async def test_create_doc_from_html_still_requires_credentials(client: HttpReviewDocsClient) -> None:
    """The inherited push path (finalize's mechanism) still requires the same grant."""
    with pytest.raises(DocsExportError):
        await client.create_doc_from_html("Title", "<h1>Hi</h1>")


async def test_reply_to_comment_sends_the_required_fields_param(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bug: ``comments.replies.create`` 400s ("The 'fields' parameter is required for this
    method") without an explicit ``fields`` query param. Assert it on the real request, not a
    mocked return value."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        token_response = _fake_token_exchange(request)
        if token_response is not None:
            return token_response
        requests.append(request)
        return httpx.Response(200, json={"id": "reply-1"})

    _mock_transport(monkeypatch, handler)
    client = HttpReviewDocsClient("cid", "secret", "refresh")
    await client.reply_to_comment("doc-1", "comment-1", "thanks")

    assert len(requests) == 1
    req = requests[0]
    assert req.method == "POST"
    assert req.url.path == "/drive/v3/files/doc-1/comments/comment-1/replies"
    assert req.url.params.get("fields")  # must be present and non-empty, or Drive 400s
    assert json.loads(req.content) == {"content": "thanks"}


async def test_share_file_needs_no_fields_param(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neighbour check: ``permissions.create`` has a documented default response (kind/id/type/
    role) — unlike comments/replies, Drive does not require ``fields`` here. Pin the real request
    shape so a future change can't silently start relying on one being needed."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        token_response = _fake_token_exchange(request)
        if token_response is not None:
            return token_response
        requests.append(request)
        return httpx.Response(200, json={"id": "perm-1"})

    _mock_transport(monkeypatch, handler)
    client = HttpReviewDocsClient("cid", "secret", "refresh")
    await client.share_file("doc-1", emails=["a@example.com"], role="commenter")

    assert len(requests) == 1
    req = requests[0]
    assert req.url.path == "/drive/v3/files/doc-1/permissions"
    assert json.loads(req.content) == {
        "type": "user",
        "role": "commenter",
        "emailAddress": "a@example.com",
    }


async def test_list_comments_sends_the_required_fields_param(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neighbour check: ``comments.list`` is in the same required-``fields`` family as
    ``replies.create`` — confirm it already sends one (it's why this call has worked live)."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        token_response = _fake_token_exchange(request)
        if token_response is not None:
            return token_response
        requests.append(request)
        return httpx.Response(200, json={"comments": []})

    _mock_transport(monkeypatch, handler)
    client = HttpReviewDocsClient("cid", "secret", "refresh")
    await client.list_comments("doc-1")

    assert len(requests) == 1
    req = requests[0]
    assert req.url.path == "/drive/v3/files/doc-1/comments"
    assert req.url.params.get("fields")


async def test_get_document_html_needs_no_fields_param(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neighbour check: ``files.export`` returns raw bytes, not a Drive resource, so the
    fields-selector concept (and the required-fields quirk) doesn't apply here."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        token_response = _fake_token_exchange(request)
        if token_response is not None:
            return token_response
        requests.append(request)
        return httpx.Response(200, text="<html><body><p>hi</p></body></html>")

    _mock_transport(monkeypatch, handler)
    client = HttpReviewDocsClient("cid", "secret", "refresh")
    html = await client.get_document_html("doc-1")

    assert html == "<html><body><p>hi</p></body></html>"
    assert len(requests) == 1
    req = requests[0]
    assert req.url.path == "/drive/v3/files/doc-1/export"
    assert req.url.params.get("mimeType") == "text/html"
