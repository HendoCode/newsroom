"""Semantic-content extraction (D13, Item 5) — title + injectable body, real-shape tolerant.

``token-vs-storage`` wraps its content in ``<article>``; ``aws-gsi-faq`` does not. Both must
extract cleanly, and in both cases the extracted body must no longer carry the editorial block
(callers are expected to strip first).
"""

from __future__ import annotations

from app.git import GitContentStore
from app.render.editorial import strip_editorial_block
from app.render.semantic import extract_semantic_body, extract_title


def test_extracts_title_and_article_when_present(content_store: GitContentStore) -> None:
    stripped = strip_editorial_block(content_store.read_draft("token-vs-storage"))

    title = extract_title(stripped)
    body = extract_semantic_body(stripped)

    assert title == "The cheapest line on your AWS bill is the one you're arguing about"
    assert body.startswith("<article")
    assert body.endswith("</article>")
    assert "<h1>" in body and "<figure>" in body and "<svg" in body
    assert "editorial" not in body.lower()


def test_falls_back_to_body_when_no_article_tag(content_store: GitContentStore) -> None:
    stripped = strip_editorial_block(content_store.read_draft("aws-gsi-faq"))

    title = extract_title(stripped)
    body = extract_semantic_body(stripped)

    assert title == "Hendo on AWS — Technical Evaluation FAQ"
    assert "<article" not in body  # this piece never wraps in <article>
    assert "<h1>" in body or "<h2>" in body
    assert 'class="editorial"' not in body


def test_extract_title_missing_returns_none() -> None:
    assert extract_title("<html><body><p>no title here</p></body></html>") is None


def test_extract_semantic_body_without_body_tag_falls_back_to_whole_input() -> None:
    fragment = "<article><h1>Standalone fragment</h1></article>"
    assert extract_semantic_body(fragment) == fragment
