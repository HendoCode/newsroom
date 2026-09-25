"""Structural HTML block extraction for review-round edits (cmw-reviewer-can-edit-doc /
decision-structure-intake.md).

Hendo, having actually reviewed a real Doc: "The review-edits should intake new paragraph breaks
as relevant, and major things like adding a new header or section; and also using of bold,
underline, italics, etc. The styling of the review doc is not important — however stating that a
new paragraph is a header and then some body text follows it is important."

Plain-text diffing (the previous implementation of :mod:`app.review.collect`'s ``diff_edits``)
destroys every one of those signals before the diff ever runs: Drive's ``text/plain`` export has
no headings, no emphasis, and a paragraph split survives only by accident (a real newline
happening to land where the split occurred). This module extracts a normalized block structure
from HTML instead — Drive's ``text/html`` export preserves paragraph/heading boundaries and
emphasis, and the source side is already HTML (``draft.html``) — so :mod:`app.review.collect` can
diff blocks against blocks instead of flattened lines against flattened lines.

Established empirically (a real Doc created via this app's own ``createDocFromHTML`` push, then
edited via the real Docs API, then re-exported — see the PR description for the full transcript),
not assumed:

- ``<h1>``-``<h6>`` round-trip as real ``<h1>``-``<h6>`` tags on **both** sides — an app-uploaded
  heading and a heading a reviewer adds via Format > Paragraph styles are indistinguishable in the
  export: both are Google's native paragraph ``namedStyleType`` (``HEADING_1``..``HEADING_6``),
  surfaced as the same tag either way. Hendo's "looked different than the gdoc defaults"
  observation is explained by inline CSS from the uploaded HTML surviving *on* those real heading
  tags, not by them being fake/styled-paragraph headings.
- Bold/italic/underline do **not** round-trip as ``<b>``/``<i>``/``<u>`` (or ``<strong>``/``<em>``)
  on the Docs-exported side, even for content this app itself uploaded using those tags — Google
  re-expresses emphasis as inline CSS on a ``<span>`` (``font-weight:700`` or ``bold``,
  ``font-style:italic``, ``text-decoration:underline``). A normalizer that only recognized the
  semantic tags would see every one of *our own* emphasized phrases as freshly plain the moment a
  round mints a Doc — :class:`_BlockExtractor` recognizes both spellings for exactly this reason.
- A real paragraph split (an Enter keypress) becomes two sibling ``<p>`` elements — confirmed by
  inserting a bare newline via the Docs API and re-exporting.
- Google's HTML export inserts its own ``&nbsp;`` at some span boundaries as a round-trip
  artifact, even for content nobody touched (confirmed: an untouched paragraph's leading space
  became ``&nbsp;`` purely from being re-exported) — :func:`_normalize_text` collapses any
  whitespace (including NBSP) so an untouched block still compares equal to itself.
- The editorial block's wrapping ``<section class="editorial">`` does not survive the round trip
  at all — Google flattens it away, keeping only its child heading/paragraph elements with no
  marker left to find them by. This is why the diff base for an internal round (whose Doc
  genuinely keeps those child elements) cannot be produced by a class-based strip on the exported
  side — :mod:`app.review.collect` instead reconstructs the correct diff base on the *Git* side
  via :func:`app.review.mint.render_for_share_mode` (cmw-internal-round-editorial-diff-asymmetry).
- **Every ``<h1>``-``<h6>`` comes back from a round trip with its entire text wrapped in a bold
  span that Google's own renderer adds — on every heading, touched or not** (cmw-phantom-edits-
  from-doc-roundtrip). Confirmed live against a fresh, never-opened Doc: both the heading tag
  itself and an inner ``<span>`` around its full text carry ``font-weight:700``, while sibling
  ``<p>`` blocks come back ``font-weight:400`` (never bold) unless something genuinely bolded
  them. This made a plain, untouched mint report one phantom "reviewer emphasized as bold" item
  per heading, scaling with the piece — Hendo's exact repro (a Doc "not touched in any way"
  reporting nine inline edits, every one emphasis-related). :meth:`Block.emphasis` suppresses the
  ``bold`` flag for a heading block specifically when its *entire* text is uniformly bold (the
  shape Google's own rendering always produces) — a real kind change (paragraph → heading) is
  still detected regardless, since that comparison never depends on emphasis; only bold coverage
  that is already 100% of the heading is treated as baseline noise. A *partial* bold span within a
  heading (some but not all of its text) is never uniform, so it is never suppressed and still
  registers as a real edit — the risk this project's brief called out twice: normalizing away a
  genuine "the reviewer bolded a phrase" signal would trade a visible bug for an invisible one.
  Italic/underline on a heading are never suppressed either — Google does not auto-apply either to
  headings, so both remain full signal.

Scope, deliberately: block kinds are ``h1``-``h6`` and ``p`` only — matching what Hendo actually
named (headings, paragraphs, emphasis). Lists/tables/blockquotes are not block-level here; that is
a real but separate extension, not folded into this ticket (see the PR description).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

_BLOCK_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6", "p"})
_VOID_TAGS = frozenset(
    {"br", "hr", "img", "meta", "link", "input", "wbr", "area", "base", "col", "embed", "source", "track"}
)
_BOLD_TAGS = frozenset({"b", "strong"})
_ITALIC_TAGS = frozenset({"i", "em"})
_UNDERLINE_TAGS = frozenset({"u"})

_WEIGHT_RE = re.compile(r"font-weight\s*:\s*(bold|[0-9]+)", re.IGNORECASE)
_ITALIC_STYLE_RE = re.compile(r"font-style\s*:\s*italic", re.IGNORECASE)
_UNDERLINE_STYLE_RE = re.compile(r"text-decoration(?:-line)?\s*:\s*[^;]*\bunderline\b", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")  # Python's \s already matches NBSP (U+00A0), verified


def _normalize_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def _style_is_bold(style: str) -> bool:
    match = _WEIGHT_RE.search(style)
    if not match:
        return False
    value = match.group(1).lower()
    return value == "bold" or (value.isdigit() and int(value) >= 600)


@dataclass(frozen=True)
class _Run:
    text: str
    bold: bool
    italic: bool
    underline: bool


EmphasisSpan = tuple[str, bool, bool, bool]  # (normalized text, bold, italic, underline)


@dataclass(frozen=True)
class Block:
    """One heading/paragraph-level block, normalized so an untouched round-trip through Google
    Docs compares equal to itself (see the module docstring)."""

    kind: str  # "h1".."h6" or "p"
    runs: tuple[_Run, ...]

    @property
    def text(self) -> str:
        return _normalize_text("".join(r.text for r in self.runs))

    @property
    def emphasis(self) -> tuple[EmphasisSpan, ...]:
        """Only the runs that carry emphasis — the comparison key that lets "same text, newly
        bold" register as a real change even though `.text` alone would not.

        A heading's ``bold`` is dropped when it covers the block's *entire* text — that shape is
        indistinguishable from Google's own always-bold heading rendering (see the module
        docstring), so it carries no signal either way. Partial bold within a heading, and
        italic/underline at any coverage, are never touched — only whole-heading bold is ever
        baseline noise."""
        suppress_bold = self.kind != "p" and self._entirely_bold()
        spans: list[EmphasisSpan] = []
        for r in self.runs:
            t = _normalize_text(r.text)
            bold = r.bold and not suppress_bold
            if t and (bold or r.italic or r.underline):
                spans.append((t, bold, r.italic, r.underline))
        return tuple(spans)

    def _entirely_bold(self) -> bool:
        non_empty = [r for r in self.runs if _normalize_text(r.text)]
        return bool(non_empty) and all(r.bold for r in non_empty)


def heading_label(kind: str) -> str:
    return "paragraph" if kind == "p" else f"Heading {kind[1]}"


class _BlockExtractor(HTMLParser):
    """Flattens an HTML document into its heading/paragraph blocks. Lenient by construction
    (``HTMLParser`` tolerates real-world markup); anything outside a recognized block tag
    (``<style>``, SVG figure content, figcaptions, the editorial section's own wrapper, etc.) is
    simply never inside a block and so never contributes text — no explicit skip-list needed."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self._kind: str | None = None
        self._runs: list[_Run] = []
        self._stack: list[tuple[bool, bool, bool]] = []
        self._bold = 0
        self._italic = 0
        self._underline = 0

    def flush(self) -> None:
        if self._kind is not None and any(r.text.strip() for r in self._runs):
            self.blocks.append(Block(kind=self._kind, runs=tuple(self._runs)))
        self._kind = None
        self._runs = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _VOID_TAGS:
            if tag == "hr":
                self.flush()  # matches draft.html's own use of <hr> as an article/editorial break
            return
        if tag in _BLOCK_TAGS:
            self.flush()
            self._kind = tag
        style = dict(attrs).get("style") or ""
        adds_bold = tag in _BOLD_TAGS or _style_is_bold(style)
        adds_italic = tag in _ITALIC_TAGS or bool(_ITALIC_STYLE_RE.search(style))
        adds_underline = tag in _UNDERLINE_TAGS or bool(_UNDERLINE_STYLE_RE.search(style))
        self._stack.append((adds_bold, adds_italic, adds_underline))
        self._bold += adds_bold
        self._italic += adds_italic
        self._underline += adds_underline

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID_TAGS:
            return
        if self._stack:
            adds_bold, adds_italic, adds_underline = self._stack.pop()
            self._bold -= adds_bold
            self._italic -= adds_italic
            self._underline -= adds_underline
        if tag in _BLOCK_TAGS:
            self.flush()

    def handle_data(self, data: str) -> None:
        if self._kind is None:
            return  # outside any recognized block — e.g. <style>/<svg>/figcaption content
        self._runs.append(
            _Run(
                text=data,
                bold=self._bold > 0,
                italic=self._italic > 0,
                underline=self._underline > 0,
            )
        )


def extract_blocks(html: str) -> list[Block]:
    """Flatten ``html`` — our own ``draft.html`` OR a Doc's ``text/html`` export, both parse
    through the identical rules above — into its ordered heading/paragraph blocks."""
    extractor = _BlockExtractor()
    extractor.feed(html)
    extractor.close()
    extractor.flush()
    return extractor.blocks
