"""The shared editorial-block strip routine (D11/D13, Item 5; domain model §1.11).

Exercised against the two *real* draft.html pieces in the brain — they intentionally differ in
shape (``token-vs-storage`` wraps content in ``<article>``; ``aws-gsi-faq`` writes directly under
``<body>``, and its editorial banner reads "NOT FOR SHARING" rather than "NOT FOR PUBLICATION") so
the routine is proven against real variation, not just one fixture.
"""

from __future__ import annotations

from app.git import GitContentStore
from app.render.editorial import has_editorial_block, strip_editorial_block


def test_strips_editorial_block_token_vs_storage(content_store: GitContentStore) -> None:
    raw = content_store.read_draft("token-vs-storage")
    assert has_editorial_block(raw)

    stripped = strip_editorial_block(raw)

    assert not has_editorial_block(stripped)
    assert 'class="editorial"' not in stripped
    # The actual editorial annotation body is gone (not just the head's documentation comment,
    # which legitimately mentions "[GAP]" as a naming convention).
    assert "Author's own witnessed instance" not in stripped
    # Semantic content survives untouched.
    assert "The cheapest line on your AWS bill" in stripped
    assert "</article>" in stripped
    assert stripped.rstrip().endswith("</html>")


def test_strips_editorial_block_aws_gsi_faq(content_store: GitContentStore) -> None:
    raw = content_store.read_draft("aws-gsi-faq")
    assert has_editorial_block(raw)

    stripped = strip_editorial_block(raw)

    assert not has_editorial_block(stripped)
    assert "NOT FOR SHARING" not in stripped
    assert "Hendo on AWS" in stripped  # title text survives
    assert "<h3" in stripped  # the Q&A headings survive


def test_strip_is_idempotent(content_store: GitContentStore) -> None:
    raw = content_store.read_draft("token-vs-storage")
    once = strip_editorial_block(raw)
    twice = strip_editorial_block(once)
    assert once == twice


def test_strip_is_a_noop_without_an_editorial_block() -> None:
    html = "<html><body><article><h1>Hi</h1><p>No editorial block here.</p></article></body></html>"
    assert strip_editorial_block(html) == html
    assert not has_editorial_block(html)


def test_does_not_touch_legitimate_mid_document_hr() -> None:
    """A stray ``<hr>`` used as a mid-document divider (not immediately before the editorial
    section) must survive — only the one directly scaffolding the editorial block is removed."""
    html = (
        "<body><p>Section one</p><hr><p>Section two</p><hr>"
        '<section class="editorial"><p>[GAP] example</p></section></body>'
    )
    stripped = strip_editorial_block(html)
    assert stripped.count("<hr>") == 1
    assert "Section one" in stripped and "Section two" in stripped
    assert not has_editorial_block(stripped)
