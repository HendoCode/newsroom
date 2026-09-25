"""Unit tests for ``app.piece_md`` — read-time interpretation of brain-authored ``piece.md``
files (cmw-brain-pieces-visibility): metadata parsing, the direct-content section rule, and the
small dependency-free markdown renderer.
"""

from __future__ import annotations

from app.piece_md import (
    first_h1,
    has_metadata_block,
    html_document_title,
    markdown_to_html,
    parse_piece_md_meta,
    piece_md_content_section,
)

# The engine-pipeline metadata shape (as in the fixture brain's aws-gsi-faq/token-vs-storage).
_METADATA_PIECE_MD = """\
# Piece: sample-brief

Metadata + status for this content target.

## Metadata
- Slug:        sample-brief
- Voice:       demo-dana (partner enablement register)
- Title:       Sample Brief: A Title With Colons
- Origin:      Firstmate autonomous task, 2026-08-30
               (direct-authored; no interview transcript)
- Target:      seller enablement brief (2-page guide)
- Partners:    AWS (touches a partner → partner-advocate in scoping, partner-brand-steward)

## Files in this folder
- draft.html      — THE output content

## Status
- Stage:          drafting

---

# Sample Brief: A Title With Colons

Body content here.
"""


def test_parse_metadata_bullets() -> None:
    meta = parse_piece_md_meta(_METADATA_PIECE_MD)
    assert meta.title == "Sample Brief: A Title With Colons"
    # The voice SLUG is the first token — parenthetical register notes never bleed in.
    assert meta.voice == "demo-dana"
    assert meta.target == "seller enablement brief (2-page guide)"
    # Parenthesized annotations are atomic (they contain commas): AWS is ONE partner entry.
    assert meta.partners == ["aws"]


def test_parse_metadata_tolerates_missing_or_empty() -> None:
    assert parse_piece_md_meta(None).title is None
    assert parse_piece_md_meta("").partners == []
    meta = parse_piece_md_meta("# Just a heading\n\nSome prose.\n")
    assert meta.voice is None
    assert meta.title is None  # the H1 fallback belongs to the sync merge, not raw parsing


def test_first_h1() -> None:
    assert first_h1("# The Brief\n\nProse.") == "The Brief"
    assert first_h1("## sub only") is None
    assert first_h1(None) is None


def test_html_document_title() -> None:
    doc = "<html><head><title>The Real Headline</title></head><body><h1>Ignored</h1></body></html>"
    assert html_document_title(doc) == "The Real Headline"
    assert html_document_title("<body><h1>Only an <em>H1</em></h1></body>") == "Only an H1"
    assert html_document_title("<title>   </title><h1>Fallback</h1>") == "Fallback"
    assert html_document_title("no title anywhere") is None
    assert html_document_title(None) is None


def test_has_metadata_block() -> None:
    assert has_metadata_block(_METADATA_PIECE_MD)
    assert not has_metadata_block("# A title\n\nProse, then a divider:\n\n---\n\nMore.\n")


def test_content_section_metadata_file_with_divider() -> None:
    section = piece_md_content_section(_METADATA_PIECE_MD)
    assert section is not None
    assert section.startswith("# Sample Brief")
    assert "Metadata + status" not in section


def test_content_section_metadata_only_file_is_none() -> None:
    no_divider = _METADATA_PIECE_MD.split("---")[0]
    assert piece_md_content_section(no_divider) is None


def test_content_section_direct_content_file_is_the_whole_file() -> None:
    direct = "# The Brief\n\nExecutive summary.\n\n---\n\n## Section one\n\nBody.\n"
    assert piece_md_content_section(direct) == direct.strip()


# --- markdown renderer ---------------------------------------------------------------------------


def test_markdown_headings_paragraphs_hr() -> None:
    html = markdown_to_html("# One\n\n## Two\n\nA paragraph that\nwraps lines.\n\n---\n\n### Three\n")
    assert "<h1>One</h1>" in html
    assert "<h2>Two</h2>" in html
    assert "<h3>Three</h3>" in html
    assert "<p>A paragraph that wraps lines.</p>" in html
    assert "<hr>" in html


def test_markdown_bold_italic_links() -> None:
    html = markdown_to_html("Position **Amazon Quick** and *AWS* — see [the site](https://example.com).")
    assert "<strong>Amazon Quick</strong>" in html
    assert "<em>AWS</em>" in html
    assert '<a href="https://example.com">the site</a>' in html


def test_markdown_escapes_html_and_rejects_unsafe_links() -> None:
    html = markdown_to_html('Raw <script>alert("x")</script> and [evil](javascript:alert(1)).')
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    # A non-http(s) scheme never becomes an href — the markdown stays literal.
    assert "javascript:" in html
    assert "<a " not in html


def test_markdown_lists() -> None:
    html = markdown_to_html("- one\n- two\n\n1. first\n2. second\n")
    assert "<ul><li>one</li><li>two</li></ul>" in html
    assert "<ol><li>first</li><li>second</li></ol>" in html


def test_markdown_blockquote_multiple_paragraphs() -> None:
    html = markdown_to_html('> **Customer:** "Can it?"\n>\n> **Seller:** "Yes."\n')
    assert "<blockquote>" in html
    assert html.count("<p>") == 2
    assert "<strong>Customer:</strong>" in html


def test_markdown_table() -> None:
    md = (
        "| Signal | Move |\n"
        "| --- | --- |\n"
        "| A stalled POC. | Schedule a session. |\n"
        "| Behind EDP. | Model usage. |\n"
    )
    html = markdown_to_html(md)
    assert "<table>" in html
    assert "<thead><tr><th>Signal</th><th>Move</th></tr></thead>" in html
    assert "<td>A stalled POC.</td>" in html
    assert html.count("<tr>") == 3  # one header row + two body rows


def test_markdown_pipe_in_paragraph_is_not_a_table() -> None:
    html = markdown_to_html("A sentence with a | pipe but no divider row follows.\n")
    assert "<table>" not in html
    assert "|" in html


# --- ensure_doc_html ----------------------------------------------------------------------------

from app.piece_md import ensure_doc_html


def test_ensure_doc_html_wraps_fragment_in_full_document() -> None:
    fragment = "<h1>Title</h1>\n<p>Body text.</p>"
    result = ensure_doc_html(fragment)
    assert "<!DOCTYPE html>" in result
    assert "<html lang=" in result
    assert "<style>" in result
    assert "</style>" in result
    assert "<body>" in result
    assert "</body>" in result
    assert "<h1>Title</h1>" in result
    assert "<p>Body text.</p>" in result
    # The CSS block includes table and blockquote styling, confirming it's our wrapper not
    # a different one.
    assert "border-collapse" in result
    assert "border-left" in result


def test_ensure_doc_html_passes_full_document_through_unchanged() -> None:
    doc = (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<style>.custom { color: red; }</style>\n</head>\n"
        "<body>\n<h1>Original</h1>\n</body>\n</html>"
    )
    assert ensure_doc_html(doc) == doc


def test_ensure_doc_html_passes_html_with_body_tag_through_unchanged() -> None:
    # A pipeline piece's draft.html always has <body> — never double-wrap.
    body_only = "<body><h1>Just a body</h1></body>"
    assert ensure_doc_html(body_only) == body_only


def test_ensure_doc_html_styles_are_professional_print_oriented() -> None:
    """The wrapper CSS uses pt units and conservative fonts (no webfont imports) so Drive
    import does not strip or degrade it."""
    fragment = "<h2>A heading</h2>"
    result = ensure_doc_html(fragment)
    assert "font-family: 'Helvetica Neue', Arial, sans-serif" in result
    assert "font-size: 11pt" in result
    assert "font-size: 14pt" in result  # h2 size
    assert "max-width: 7.0in" in result
    # No webfont @import — Drive strips them and the Doc looks blank.
    assert "@import" not in result
