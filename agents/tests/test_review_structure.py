"""Structural HTML block extraction tests (cmw-reviewer-can-edit-doc / decision-structure-
intake.md). Covers the two things established empirically against a real Google Doc (see the PR
description for the full transcript): headings survive as real ``<h1>``-``<h6>`` tags either way,
while bold/italic/underline round-trip through Docs as inline CSS on a ``<span>``, never as
``<b>``/``<i>``/``<u>`` — even for content this app itself uploaded using those tags.
"""

from __future__ import annotations

from app.review.structure import extract_blocks, heading_label


def test_extracts_headings_and_paragraphs_in_order():
    html = "<article><h1>Title</h1><p>First.</p><h2>Section</h2><p>Second.</p></article>"

    blocks = extract_blocks(html)

    assert [(b.kind, b.text) for b in blocks] == [
        ("h1", "Title"),
        ("p", "First."),
        ("h2", "Section"),
        ("p", "Second."),
    ]


def test_recognizes_semantic_emphasis_tags():
    html = "<p>Some <b>bold</b>, <i>italic</i>, and <u>underlined</u> words.</p>"

    block = extract_blocks(html)[0]

    assert ("bold", True, False, False) in block.emphasis
    assert ("italic", False, True, False) in block.emphasis
    assert ("underlined", False, False, True) in block.emphasis


def test_recognizes_strong_and_em_as_bold_and_italic():
    html = "<p><strong>strong</strong> and <em>em</em>.</p>"

    block = extract_blocks(html)[0]

    assert ("strong", True, False, False) in block.emphasis
    assert ("em", False, True, False) in block.emphasis


def test_recognizes_inline_style_based_emphasis():
    """Confirmed live: Google's Doc HTML export never uses <b>/<i>/<u> — it re-expresses emphasis
    as inline CSS on a <span>, even for content originally uploaded using the semantic tags."""
    html = (
        '<p><span style="font-weight:700">bold</span> '
        '<span style="font-style:italic">italic</span> '
        '<span style="text-decoration:underline">under</span>.</p>'
    )

    block = extract_blocks(html)[0]

    assert ("bold", True, False, False) in block.emphasis
    assert ("italic", False, True, False) in block.emphasis
    assert ("under", False, False, True) in block.emphasis


def test_font_weight_bold_keyword_and_numeric_both_count():
    html_keyword = '<p><span style="font-weight:bold">x</span></p>'
    html_400 = '<p><span style="font-weight:400">x</span></p>'
    html_600 = '<p><span style="font-weight:600">x</span></p>'

    assert extract_blocks(html_keyword)[0].emphasis == (("x", True, False, False),)
    assert extract_blocks(html_400)[0].emphasis == ()  # normal weight — not emphasis
    assert extract_blocks(html_600)[0].emphasis == (("x", True, False, False),)


def test_underline_detection_survives_a_real_captured_style_string():
    """The exact ``style`` value Google's export produced for an italic+underlined phrase in a
    live probe doc (see the PR description): several unrelated ``text-decoration...`` properties
    precede the real one, and the regex must not stop at the first, non-matching one."""
    html = (
        '<p><span style="text-decoration-skip-ink:none;-webkit-text-decoration-skip:none;'
        'font-style:italic;text-decoration:underline">phrase</span></p>'
    )

    block = extract_blocks(html)[0]

    assert ("phrase", False, True, True) in block.emphasis


def test_plain_text_carries_no_emphasis():
    block = extract_blocks("<p>Nothing special here.</p>")[0]
    assert block.emphasis == ()


def test_ignores_content_outside_recognized_blocks():
    """<style>/<figure>/SVG content and a bare <hr> separator never contribute text — only
    h1-h6/p are block-level here (deliberately scoped, see the module docstring)."""
    html = (
        "<head><style>h1{color:red}</style></head>"
        "<body><h1>Title</h1><figure><svg><text>chart label</text></svg>"
        "<figcaption>a caption</figcaption></figure><hr><p>Body.</p></body>"
    )

    blocks = extract_blocks(html)

    assert [(b.kind, b.text) for b in blocks] == [("h1", "Title"), ("p", "Body.")]


def test_void_tags_never_unbalance_the_emphasis_stack():
    """A bare <img> (no closing tag — never pushed) must not corrupt bold/italic tracking for
    whatever styled span follows it."""
    html = (
        '<p><span style="font-weight:700">bold</span>'
        '<img src="x.png">'
        '<span style="font-style:italic">italic</span></p>'
    )

    block = extract_blocks(html)[0]

    assert block.text == "bolditalic"
    assert ("bold", True, False, False) in block.emphasis
    assert ("italic", False, True, False) in block.emphasis


def test_normalizes_nbsp_and_collapses_whitespace():
    html = "<p>Word with nbsp   and   spaces.</p>"

    block = extract_blocks(html)[0]

    assert block.text == "Word with nbsp and spaces."


def test_heading_label():
    assert heading_label("p") == "paragraph"
    assert heading_label("h1") == "Heading 1"
    assert heading_label("h6") == "Heading 6"


# --- cmw-phantom-edits-from-doc-roundtrip: Google always wraps a heading's ENTIRE text in a bold
# span on export, whether or not anyone touched it — that must never register as an emphasis edit,
# while a genuine partial-bold (or any italic/underline) within a heading still must ---------------


def test_heading_wide_bold_is_suppressed_as_googles_own_rendering_artifact():
    """A real captured shape: both the h1 tag and its inner span carry font-weight:700 across the
    entire heading text — Google's own doing, confirmed live, not a reviewer action."""
    html = (
        '<h1 style="font-weight:700">'
        '<span style="font-weight:700">The Cheapest Line</span>'
        "</h1>"
    )

    block = extract_blocks(html)[0]

    assert block.emphasis == ()


def test_heading_partial_bold_still_registers():
    """Only whole-heading bold is baseline noise — a reviewer bolding one word within a heading
    that is not otherwise bold must still be detected."""
    html = '<h2>Some <span style="font-weight:700">important</span> words</h2>'

    block = extract_blocks(html)[0]

    assert ("important", True, False, False) in block.emphasis


def test_heading_wide_italic_and_underline_are_never_suppressed():
    """Google does not auto-apply italic/underline to headings (only bold) — both must still be
    reported even when they cover the entire heading."""
    html = (
        '<h2><span style="font-style:italic;text-decoration:underline">'
        "Whole Heading</span></h2>"
    )

    block = extract_blocks(html)[0]

    assert ("Whole Heading", False, True, True) in block.emphasis


def test_paragraph_wide_bold_is_never_suppressed():
    """The suppression is heading-only — Google never auto-bolds a <p>, and a reviewer genuinely
    bolding an entire paragraph must still be detected (fixed 400 weight, never 700, on an
    untouched paragraph per structure.py's docstring)."""
    html = '<p><span style="font-weight:700">Whole paragraph, deliberately bolded.</span></p>'

    block = extract_blocks(html)[0]

    assert ("Whole paragraph, deliberately bolded.", True, False, False) in block.emphasis


def test_extract_blocks_is_lenient_on_real_googles_export_shape():
    """A trimmed real fragment captured from Drive's text/html export (see the PR description) —
    inline styles, an id on a reviewer-added heading, an &nbsp; artifact — must parse cleanly. Both
    headings here carry Google's own whole-heading bold wrapping (cmw-phantom-edits-from-doc-
    roundtrip) — confirming the emphasis suppression fires on this exact real shape, not just the
    synthetic fixtures above."""
    html = (
        '<html><body class="doc-content" style="background-color:#ffffff">'
        '<h1 style="color:#0000ff;font-weight:700">'
        '<span style="color:#0000ff;font-weight:700">The cheapest line</span></h1>'
        '<p style="margin:0"><span>One app costs about </span>'
        '<span style="font-weight:700">$29,800 a month</span>'
        '<span>&nbsp;in tokens.</span></p>'
        '<h2 id="h.d86uhpdhcn6v" style="color:#008000;font-weight:700">'
        '<span style="color:#008000;font-weight:700">A reviewer-added heading</span></h2>'
        "</body></html>"
    )

    blocks = extract_blocks(html)

    assert blocks[0].kind == "h1"
    assert blocks[0].text == "The cheapest line"
    assert blocks[0].emphasis == ()  # whole-heading bold suppressed — Google's own rendering
    assert blocks[1].kind == "p"
    assert blocks[1].text == "One app costs about $29,800 a month in tokens."
    assert ("$29,800 a month", True, False, False) in blocks[1].emphasis
    assert blocks[2].kind == "h2"
    assert blocks[2].text == "A reviewer-added heading"
    assert blocks[2].emphasis == ()  # same suppression on a reviewer-added heading
