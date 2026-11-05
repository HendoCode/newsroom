"""The shared editorial-block strip routine (D11/D13, Item 5; domain model §1.11).

Exercised against the two *real* drafted pieces in the brain — they differ in exactly the ways that
used to break a naive strip: ``the-board-on-the-wall`` quotes the literal
``<section class="editorial">`` convention inside its ``<head>`` comment and closes with no open
gaps, while ``rehearse-the-rollback`` carries an open ``[GAP: ...]`` annotation and Q&A ``<h3>``
headings. So the routine is proven against real variation, not one fixture.
"""

from __future__ import annotations

from app.git import GitContentStore
from app.render.editorial import has_editorial_block, strip_editorial_block


def test_strips_editorial_block_the_board_on_the_wall(content_store: GitContentStore) -> None:
    raw = content_store.read_draft("the-board-on-the-wall")
    assert has_editorial_block(raw)

    stripped = strip_editorial_block(raw)

    assert not has_editorial_block(stripped)
    # The annotation body is gone…
    assert "NO OPEN GAPS" not in stripped and "[NOTE" not in stripped
    # …but the piece's own <head> comment quotes the `<section class="editorial">` convention by
    # name, and that literal is PROSE inside a comment, not markup. Matching it used to consume the
    # entire document — comment to closing </section> — leaving a 700-character stump.
    assert 'class="editorial"' in stripped
    # Semantic content survives untouched: the article's closing paragraph is still there.
    assert "Some things in a workplace are not storage" in stripped
    assert "The board on the wall" in stripped
    assert "</article>" in stripped
    assert stripped.rstrip().endswith("</html>")


def test_strips_editorial_block_rehearse_the_rollback(content_store: GitContentStore) -> None:
    raw = content_store.read_draft("rehearse-the-rollback")
    assert has_editorial_block(raw)

    stripped = strip_editorial_block(raw)

    assert not has_editorial_block(stripped)
    assert "[GAP: need the incident artifact]" not in stripped
    assert "Rehearse the rollback" in stripped  # title text survives
    assert "<h3" in stripped  # the Q&A headings survive


def test_a_comment_quoting_the_convention_is_not_an_editorial_block() -> None:
    """The strip must not mistake documentation for markup."""
    html = (
        "<html><head><!-- the convention is a literal <section class=\"editorial\"> block --></head>"
        "<body><article><p>Keep me.</p></article></body></html>"
    )

    assert not has_editorial_block(html)
    assert strip_editorial_block(html) == html


def test_strip_is_idempotent(content_store: GitContentStore) -> None:
    raw = content_store.read_draft("the-board-on-the-wall")
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
