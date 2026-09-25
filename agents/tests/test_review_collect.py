"""COLLECT tests (feedback-intake.md; decision-structure-intake.md): comments + structural
diff-detected inline edits, no silent drops."""

from __future__ import annotations

from app.models import ShareMode
from app.review.collect import RawFeedbackItem, collect_comments, diff_edits, gather_raw_items
from app.review.docs_client import CommentThread

SIMPLE_HTML = (
    "<html><body><article><h1>Title</h1><p>First paragraph.</p><p>Second paragraph.</p>"
    "</article><hr><section class=\"editorial\">[GAP] hidden</section></body></html>"
)

# The real draft.html shape (app.render.editorial): a heading/paragraph nested *inside* the
# editorial <section>, not flat text — matches what strip_editorial_block/render_for_share_mode
# actually operate on, and what an internal round's Doc export flattens down to (structure.py).
REALISTIC_EDITORIAL_HTML = (
    "<html><body><article><h1>Title</h1><p>First paragraph.</p></article>"
    '<hr><section class="editorial"><h3>Editorial annotations</h3><p>[GAP] hidden</p></section>'
    "</body></html>"
)


class FakeDocsClient:
    def __init__(self, comments: list[CommentThread], document_html: str | Exception) -> None:
        self._comments = comments
        self._document_html = document_html

    async def list_comments(self, doc_id: str) -> list[CommentThread]:
        return self._comments

    async def get_document_html(self, doc_id: str) -> str:
        if isinstance(self._document_html, Exception):
            raise self._document_html
        return self._document_html


async def test_collect_comments_maps_every_thread_regardless_of_resolved_flag():
    docs = FakeDocsClient(
        comments=[
            CommentThread(comment_id="c1", author="Alice", quoted_text="Second paragraph.", content="tighten this", resolved=False),
            CommentThread(comment_id="c2", author="Bob", quoted_text=None, content="already resolved but still collected", resolved=True),
        ],
        document_html="",
    )

    items = await collect_comments(docs, "doc-1")

    assert len(items) == 2  # no silent drops — resolved comments are collected too
    assert items[0] == RawFeedbackItem(
        ask="tighten this", reviewer="Alice", location="Second paragraph.", channel="google-docs", comment_id="c1"
    )
    assert items[1].comment_id == "c2"


def test_diff_edits_detects_a_pure_text_change():
    original = "<article><p>Line one.</p><p>Line two.</p><p>Line three.</p></article>"
    current = "<article><p>Line one.</p><p>Line TWO changed.</p><p>Line three.</p></article>"

    items = diff_edits(original, current)

    assert len(items) == 1
    item = items[0]
    assert item.channel == "google-docs-edit"
    assert item.comment_id is None  # never anchored to a Doc comment
    assert "Line two." in item.ask and "Line TWO changed." in item.ask
    assert item.before == "Line two."
    assert item.after == "Line TWO changed."


def test_diff_edits_detects_insert_and_delete():
    original = "<article><p>Line one.</p><p>Line two.</p></article>"
    current = "<article><p>Line one.</p><p>Line two.</p><p>Line three added.</p></article>"

    items = diff_edits(original, current)
    assert len(items) == 1
    assert "added" in items[0].ask and "Line three added." in items[0].ask
    assert items[0].before == ""
    assert items[0].after == "Line three added."

    items = diff_edits(current, original)  # the reverse: a deletion
    assert len(items) == 1
    assert "removed" in items[0].ask and "Line three added." in items[0].ask


def test_diff_edits_detects_a_new_heading_with_unchanged_text():
    """The signal Hendo actually asked for: marking a line as a heading, with no text change at
    all, must still be detected — a pure-text diff would see nothing here."""
    original = "<article><p>Line one.</p><p>Section title.</p></article>"
    current = "<article><p>Line one.</p><h2>Section title.</h2></article>"

    items = diff_edits(original, current)

    assert len(items) == 1
    assert "Heading 2" in items[0].ask
    assert "Section title." in items[0].ask
    assert items[0].before == items[0].after == "Section title."  # text itself never changed


def test_diff_edits_detects_new_emphasis_with_unchanged_text():
    original = "<article><p>Plain phrase here.</p></article>"
    current = "<article><p><b>Plain phrase here.</b></p></article>"

    items = diff_edits(original, current)

    assert len(items) == 1
    assert "bold" in items[0].ask
    assert "Plain phrase here." in items[0].ask


def test_diff_edits_detects_a_split_that_adds_a_heading():
    """"stating that a new paragraph is a header and then some body text follows it" — Hendo's
    own example. A single old paragraph splits into a new Heading 2 followed by a paragraph."""
    original = "<article><p>Intro line. Body text follows.</p></article>"
    current = "<article><h2>Intro line.</h2><p>Body text follows.</p></article>"

    items = diff_edits(original, current)

    assert len(items) == 1
    ask = items[0].ask
    assert "[Heading 2] 'Intro line.'" in ask
    assert "[paragraph] 'Body text follows.'" in ask


def test_diff_edits_recognizes_our_own_semantic_tags_as_equivalent_to_googles_style_based_ones():
    """Google's Doc export never round-trips <strong>/<em>/<u> as themselves — it re-expresses
    them as inline-styled <span>s (verified empirically; see app.review.structure's docstring).
    An untouched bold phrase must therefore still compare equal even though the two sides spell
    "bold" completely differently."""
    original = "<article><p>One <strong>bold</strong> word.</p></article>"
    current = '<article><p>One <span style="font-weight:700">bold</span> word.</p></article>'

    assert diff_edits(original, current) == []


def test_diff_edits_ignores_nbsp_round_trip_noise():
    """Google's HTML export inserts its own &nbsp; at some span boundaries as a round-trip
    artifact even when nobody touched the content (verified empirically) — this must never read
    as a reviewer edit."""
    original = "<article><p>S3 Standard is cheap for the first 50 TB.</p></article>"
    current = "<article><p>S3 Standard is cheap&nbsp;for the first 50 TB.</p></article>"

    assert diff_edits(original, current) == []


def test_diff_edits_is_purely_mechanical_with_no_editorial_block_awareness():
    """diff_edits itself no longer strips anything (cmw-internal-round-editorial-diff-asymmetry) —
    it diffs exactly what it's given. Handing it an editorial block present on only one side reads
    as a real removal, same as any other content; reconstructing the correct comparison sides is
    gather_raw_items'/render_for_share_mode's job, not this function's — see the tests below."""
    original = (
        "<article><h1>Title</h1><p>First paragraph.</p></article><hr>"
        '<section class="editorial"><h3>Editorial annotations</h3><p>[GAP] hidden</p></section>'
    )
    current = "<article><h1>Title</h1><p>First paragraph.</p></article>"

    items = diff_edits(original, current)

    assert items  # the (unstripped) editorial block reads as removed content, as expected


def test_diff_edits_no_changes_returns_nothing():
    original = "<article><p>Same.</p></article>"

    assert diff_edits(original, original) == []


async def test_gather_raw_items_combines_comments_and_edits():
    docs = FakeDocsClient(
        comments=[CommentThread(comment_id="c1", content="fix this", resolved=False)],
        document_html="<article><h1>Title</h1><p>First paragraph changed.</p><p>Second paragraph.</p></article>",
    )

    items, diff_ok = await gather_raw_items(
        docs, doc_id="doc-1", minted_from_html=SIMPLE_HTML, share_mode=ShareMode.external
    )

    assert diff_ok is True
    assert any(i.comment_id == "c1" for i in items)
    assert any(i.comment_id is None for i in items)  # the diff-detected edit


async def test_gather_raw_items_degrades_gracefully_when_diff_fails():
    docs = FakeDocsClient(
        comments=[CommentThread(comment_id="c1", content="fix this", resolved=False)],
        document_html=RuntimeError("export failed"),
    )

    items, diff_ok = await gather_raw_items(
        docs, doc_id="doc-1", minted_from_html=SIMPLE_HTML, share_mode=ShareMode.external
    )

    assert diff_ok is False
    assert len(items) == 1  # comments still collected even though the diff half failed
    assert items[0].comment_id == "c1"


# --- cmw-internal-round-editorial-diff-asymmetry: the diff base must match what actually got
# minted for THIS round's share mode, not assume a strip that only ever happens externally --------


async def test_gather_raw_items_internal_round_editorial_block_is_not_a_phantom_edit():
    """An internal round's Doc genuinely keeps the editorial block (its wrapper doesn't survive
    the round trip, but the child heading/paragraph elements do — app.review.structure); the Doc
    export below reflects exactly that shape. Before this fix, diff_edits always stripped the Git
    side regardless of share mode, so this exact scenario read the machine's own GAP note as a
    reviewer addition."""
    docs = FakeDocsClient(
        comments=[],
        # Google flattens away <section class="editorial">, keeping its children — exactly what a
        # real internal-round Doc export looks like (app.review.structure's docstring).
        document_html=(
            "<article><h1>Title</h1><p>First paragraph.</p></article>"
            "<h3>Editorial annotations</h3><p>[GAP] hidden</p>"
        ),
    )

    items, diff_ok = await gather_raw_items(
        docs,
        doc_id="doc-1",
        minted_from_html=REALISTIC_EDITORIAL_HTML,
        share_mode=ShareMode.internal,
    )

    assert diff_ok is True
    assert items == []  # no phantom "reviewer added the GAP note" item


async def test_gather_raw_items_external_round_still_strips_editorial_block_from_diff_base():
    """External rounds are unaffected by this fix — the Doc never had the block (mint.py strips it
    before upload, D11), so the diff base must strip it too, exactly as before."""
    docs = FakeDocsClient(
        comments=[],
        document_html="<article><h1>Title</h1><p>First paragraph.</p></article>",
    )

    items, diff_ok = await gather_raw_items(
        docs,
        doc_id="doc-1",
        minted_from_html=REALISTIC_EDITORIAL_HTML,
        share_mode=ShareMode.external,
    )

    assert diff_ok is True
    assert items == []  # no phantom "reviewer deleted the editorial block" item either


# --- cmw-phantom-edits-from-doc-roundtrip: the DRAFT banner is authored as a non-block <div> (so
# it never becomes a Block on our own reconstructed side), but Drive's HTML-to-Docs conversion
# turns it into a real <p> on the exported side (confirmed live) — that phantom "reviewer added
# the banner" item must never surface, on external rounds specifically (the only ones that get a
# banner at all) ------------------------------------------------------------------------------


async def test_gather_raw_items_external_round_banner_paragraph_is_not_a_phantom_edit():
    """Google's conversion of the banner <div> into a real exported <p> must not read as a
    reviewer addition — this is the second of the two pre-existing artefacts this ticket fixes,
    confirmed live against a real Doc (see test_review_google_docs_roundtrip.py)."""
    docs = FakeDocsClient(
        comments=[],
        document_html=(
            "<p>DRAFT — not for external distribution</p>"
            "<article><h1>Title</h1><p>First paragraph.</p></article>"
        ),
    )

    items, diff_ok = await gather_raw_items(
        docs,
        doc_id="doc-1",
        minted_from_html="<article><h1>Title</h1><p>First paragraph.</p></article>",
        share_mode=ShareMode.external,
    )

    assert diff_ok is True
    assert items == []


async def test_gather_raw_items_internal_round_has_no_banner_to_drop():
    """An internal round never adds the banner in the first place — this is a no-op guard, not a
    behavior change, for the share mode that never triggers it."""
    docs = FakeDocsClient(
        comments=[],
        document_html="<article><h1>Title</h1><p>First paragraph.</p></article>",
    )

    items, diff_ok = await gather_raw_items(
        docs,
        doc_id="doc-1",
        minted_from_html="<article><h1>Title</h1><p>First paragraph.</p></article>",
        share_mode=ShareMode.internal,
    )

    assert diff_ok is True
    assert items == []
