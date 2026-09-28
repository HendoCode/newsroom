"""Semantic-content extraction (D13, Item 5) — title + injectable body, real-shape tolerant.

Both real fixture pieces wrap their content in ``<article>`` and both must extract cleanly with the
editorial block gone; the shapes still differ enough to catch regressions (``the-board-on-the-wall``
is a narrative essay with a figure/SVG and no open gaps, ``rehearse-the-rollback`` carries the
``<h3>`` Q&A headings and an open ``[GAP]`` annotation). The no-``<article>`` branch has no real
piece to exercise it today, so it is covered by the hand-built case at the bottom.
"""

from __future__ import annotations

from app.git import GitContentStore
from app.render.editorial import strip_editorial_block
from app.render.semantic import extract_semantic_body, extract_title


def test_extracts_title_and_article_when_present(content_store: GitContentStore) -> None:
    stripped = strip_editorial_block(content_store.read_draft("the-board-on-the-wall"))

    title = extract_title(stripped)
    body = extract_semantic_body(stripped)

    assert title == "The board on the wall"
    assert body.startswith("<article")
    assert body.endswith("</article>")
    assert "<h1>" in body and "<figure>" in body and "<svg" in body
    assert "editorial" not in body.lower()


def test_extracts_a_qa_shaped_draft_without_losing_its_headings(content_store: GitContentStore) -> None:
    stripped = strip_editorial_block(content_store.read_draft("rehearse-the-rollback"))

    title = extract_title(stripped)
    body = extract_semantic_body(stripped)

    assert title == "Rehearse the rollback"
    assert body.startswith("<article") and body.endswith("</article>")
    assert "<h3" in body  # the drill-log Q&A headings survive extraction
    assert 'class="editorial"' not in body


def test_falls_back_to_body_content_when_no_article_tag() -> None:
    """A draft written straight under ``<body>`` still yields its body, not the whole document."""
    html = (
        "<!DOCTYPE html><html><head><title>Plain</title></head>"
        "<body><h1>Plain</h1><p>Body copy.</p></body></html>"
    )

    body = extract_semantic_body(html)

    assert "<p>Body copy.</p>" in body
    assert "<!DOCTYPE" not in body


def test_extract_title_missing_returns_none() -> None:
    assert extract_title("<html><body><p>no title here</p></body></html>") is None


def test_extract_semantic_body_without_body_tag_falls_back_to_whole_input() -> None:
    fragment = "<article><h1>Standalone fragment</h1></article>"
    assert extract_semantic_body(fragment) == fragment
