"""Assisted ingest preview tests (open-decisions Item 7) — read-only, never persists anything."""

from __future__ import annotations

from app.models import DocRef, ReviewRound, ReviewRoundStatus, ShareMode
from app.render.editorial import strip_editorial_block
from app.review.docs_client import CommentThread
from app.review.preview import preview_round


class FakeDocsClient:
    def __init__(self, comments, document_html) -> None:
        self._comments = comments
        self._document_html = document_html

    async def list_comments(self, doc_id: str):
        return self._comments

    async def get_document_html(self, doc_id: str) -> str:
        if isinstance(self._document_html, Exception):
            raise self._document_html
        return self._document_html


def _round(
    content_store, *, doc_id: str | None = "doc-1", share_mode: ShareMode = ShareMode.internal
) -> ReviewRound:
    sha = content_store.revision_history("token-vs-storage", max_count=1)[0].sha
    return ReviewRound(
        piece_id="p1",
        round_number=1,
        minted_from_revision=sha,
        doc=DocRef(doc_id=doc_id, url="https://docs.google.com/x", share_mode=share_mode),
        status=ReviewRoundStatus.open,
    )


async def test_preview_counts_comments_and_edits(content_store):
    docs = FakeDocsClient(
        comments=[CommentThread(comment_id="c1", content="tighten this")],
        document_html="<article><p>Completely different body text that will diff against the real draft.</p></article>",
    )
    round_ = _round(content_store)

    result = await preview_round(docs, content_store, round_, slug="token-vs-storage")

    assert result.round_number == 1
    assert result.comment_count == 1
    assert result.edit_count > 0
    assert result.no_changes is False
    assert result.diff_degraded is False
    assert result.samples


async def test_preview_no_changes_when_nothing_collected(content_store):
    # No comments, and the Doc's HTML matches the frozen revision. An internal round's Doc
    # genuinely keeps the editorial block, so "unchanged" means the raw revision, unstripped
    # (cmw-internal-round-editorial-diff-asymmetry) — see app.review.mint.render_for_share_mode.
    unchanged_html = content_store.read_draft("token-vs-storage")
    docs = FakeDocsClient(comments=[], document_html=unchanged_html)
    round_ = _round(content_store, share_mode=ShareMode.internal)

    result = await preview_round(docs, content_store, round_, slug="token-vs-storage")

    assert result.no_changes is True
    assert result.comment_count == 0


async def test_preview_no_changes_for_external_round_with_stripped_doc(content_store):
    """External rounds are unaffected by this fix — the Doc never had the editorial block, so
    "unchanged" means the stripped revision, exactly as before."""
    unchanged_html = strip_editorial_block(content_store.read_draft("token-vs-storage"))
    docs = FakeDocsClient(comments=[], document_html=unchanged_html)
    round_ = _round(content_store, share_mode=ShareMode.external)

    result = await preview_round(docs, content_store, round_, slug="token-vs-storage")

    assert result.no_changes is True
    assert result.comment_count == 0


async def test_preview_degrades_when_diff_fails_but_keeps_comments(content_store):
    docs = FakeDocsClient(
        comments=[CommentThread(comment_id="c1", content="tighten this")],
        document_html=RuntimeError("export failed"),
    )
    round_ = _round(content_store)

    result = await preview_round(docs, content_store, round_, slug="token-vs-storage")

    assert result.diff_degraded is True
    assert result.comment_count == 1
    assert result.edit_count == 0


async def test_preview_with_no_doc_id_is_no_changes(content_store):
    round_ = _round(content_store, doc_id=None)

    result = await preview_round(FakeDocsClient([], ""), content_store, round_, slug="token-vs-storage")

    assert result.no_changes is True
    assert result.comment_count == 0
    assert result.edit_count == 0
