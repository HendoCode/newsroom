"""Read-time interpretation of a piece folder's ``piece.md`` (cmw-brain-pieces-visibility).

``piece.md`` is the brain-authored metadata/status file at ``drafts/<slug>/piece.md``. The webapp
itself NEVER writes it (``GitContentStore`` commits only ``draft.html``/``sources.md``/assets) — it
is purely brain-authored, by hand or by brain-side agent tasks, and two shapes coexist:

1. **Metadata-only** (the engine-pipeline convention, e.g. the ``aws-gsi-faq`` fixture): the file
   is metadata + status, and the actual content lives in ``draft.html`` once drafting runs.
2. **Direct-authored** (brain agent tasks, e.g. the 2026-08-30/31 AWS×Hendo seller briefs): the
   file carries the metadata block, a standalone ``---`` divider, and then THE output content as
   markdown in the same file — there is no ``draft.html`` at all.

This module exists so shape 2 is readable through the exact same surface as shape 1:
:func:`piece_md_content_section` extracts the direct-authored content section (``None`` for
metadata-only files, so nothing changes for pipeline pieces), :func:`markdown_to_html` renders it,
and :func:`parse_piece_md_meta` lifts the identity fields (title/voice/target/partners) that the
brain-draft sync (``app.brain_sync``) needs to complete the Mongo half of such a piece.

``markdown_to_html`` is deliberately a SMALL, dependency-free renderer covering exactly the
constructs the brain briefs use (h1-h6, paragraphs, ul/ol, blockquotes, tables, hr, bold/italic,
plain http(s) links) — a full CommonMark implementation is not justified here. All input text is
HTML-escaped before any tag is emitted, so it cannot inject markup.
"""

from __future__ import annotations

import html as _html_mod
import re
from dataclasses import dataclass, field
from html import unescape as html_unescape
from textwrap import dedent

# --- metadata parsing ---------------------------------------------------------------------------

# One metadata bullet: `- Key:  value` (case-insensitive key).
_BULLET_RE = re.compile(r"^-\s*([A-Za-z][A-Za-z -]*):\s*(.*)$")
# Where the metadata block ends (a section heading) — everything after is prose/content anyway.
_HEADING_RE = re.compile(r"^#{1,6}\s")


@dataclass
class PieceMdMeta:
    """The identity fields a ``piece.md`` carries (all best-effort/optional)."""

    title: str | None = None
    voice: str | None = None
    target: str | None = None
    partners: list[str] = field(default_factory=list)


# Bullet keys that mark a real metadata block (the engine-pipeline convention) as opposed to a
# direct-content piece.md whose first lines are already the content itself.
_METADATA_BULLET_RE = re.compile(
    r"^-\s*(Slug|Title|Voice|Origin|Target|Audience|Partners|Stage|Status)\s*:", re.IGNORECASE
)


def has_metadata_block(piece_md: str) -> bool:
    """True when the file's pre-divider region is a metadata bullet list, not content.

    Scans only up to the first standalone ``---`` divider (a metadata file's divider separates
    metadata from content; a direct-content file's dividers sit inside the content, after the
    opening heading/prose).
    """
    for line in piece_md.splitlines():
        if line.strip() == "---":
            break
        if _METADATA_BULLET_RE.match(line.strip()):
            return True
    return False


def _split_outside_parens(text: str) -> list[str]:
    """Comma-split that treats parenthesized annotations as atomic — ``AWS (touches a partner →
    partner-advocate in scoping, partner-brand-steward in council)`` is ONE partner entry."""
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return parts


def parse_piece_md_meta(piece_md: str | None) -> PieceMdMeta:
    """Lift Title/Voice/Target/Partners from the metadata bullet list of a ``piece.md``.

    Tolerant by design: brain files are hand-maintained; a missing/garbled field degrades to
    ``None``/empty rather than failing. The metadata block is read only up to the first markdown
    heading (``## Files in this folder`` etc.), never into the content section a direct-authored
    piece carries after the ``---`` divider.
    """
    meta = PieceMdMeta()
    if not piece_md:
        return meta
    fields: dict[str, list[str]] = {}
    current: str | None = None
    for line in piece_md.splitlines():
        if _HEADING_RE.match(line) and current is not None and not line.startswith("- "):
            # A heading ends the bullet-list metadata region (only after at least one bullet, so
            # the very first `# Piece: <slug>` line does not stop the scan).
            if fields:
                break
            continue
        bullet = _BULLET_RE.match(line.strip()) if line.lstrip().startswith("- ") else None
        if bullet:
            current = bullet.group(1).strip().lower()
            fields.setdefault(current, [])
            if bullet.group(2).strip():
                fields[current].append(bullet.group(2).strip())
        elif current and line.strip() and line.startswith((" ", "\t")):
            # Indented continuation of the previous bullet (multi-line Origin/Target values).
            fields[current].append(line.strip())
    if "title" in fields:
        title = " ".join(fields["title"]).strip()
        meta.title = title or None
    if "voice" in fields:
        # `- Voice: demo-dana (partner enablement register)` → the voice SLUG is the first token.
        raw = " ".join(fields["voice"]).strip()
        meta.voice = raw.split()[0] if raw else None
    if "target" in fields:
        target = " ".join(fields["target"]).strip()
        meta.target = target or None
    if "partners" in fields:
        # `- Partners: AWS (partner-brand-steward)` → ["aws"]:
        # the first word of each comma-separated entry (parenthesized annotations are atomic —
        # they can contain commas), lowercased to the brain's partner-file slugs (partners/aws.md,
        # partners/<partner>.md, ...). Duplicates dropped, order preserved.
        raw = " ".join(fields["partners"])
        seen: set[str] = set()
        for entry in _split_outside_parens(raw):
            word = entry.strip().split()[0].strip("()") if entry.strip() else ""
            slug = word.lower()
            if slug and slug not in seen:
                seen.add(slug)
                meta.partners.append(slug)
    return meta


def first_h1(piece_md: str | None) -> str | None:
    """The first H1 heading of a markdown document — the title a direct-content piece.md (no
    metadata bullets, no meta.json title) carries as its own first line."""
    if not piece_md:
        return None
    for line in piece_md.splitlines():
        m = re.match(r"^#\s+(.*)$", line.strip())
        if m:
            return m.group(1).strip() or None
    return None


_TITLE_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_H1_TAG_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_ANY_TAG_RE = re.compile(r"<[^>]+>")


def html_document_title(draft_html: str | None) -> str | None:
    """Last-resort title for a piece folder with no piece.md identity at all (older pipeline-
    shaped drafts: ``draft.html`` + sources + transcript only): the document's ``<title>``, then
    its first ``<h1>``, tags stripped and whitespace collapsed. Regex-only (no parser needed) —
    trusted internal content, one document shape."""
    if not draft_html:
        return None
    for regex in (_TITLE_TAG_RE, _H1_TAG_RE):
        m = regex.search(draft_html)
        if m:
            text = _ANY_TAG_RE.sub("", m.group(1))
            text = html_unescape(" ".join(text.split())).strip()
            if text:
                return text
    return None


# --- direct-authored content section ------------------------------------------------------------


def piece_md_content_section(piece_md: str | None) -> str | None:
    """The direct-authored content of a ``piece.md``, or ``None`` for a metadata-only one.

    Two brain shapes (see module docstring): a metadata-block file yields everything after its
    first standalone ``---`` divider (``None`` when it has no divider — metadata-only, e.g. the
    ``aws-gsi-faq`` fixture — which keeps today's "no draft.html → no revision yet" behavior);
    a file with no metadata block IS itself content and yields the whole file.
    """
    if not piece_md or not piece_md.strip():
        return None
    if not has_metadata_block(piece_md):
        return piece_md.strip()
    lines = piece_md.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "---":
            section = "\n".join(lines[i + 1 :]).strip()
            return section or None
    return None


# --- minimal markdown → HTML ---------------------------------------------------------------------
#
# Deliberately small: the constructs the brain briefs actually use (verified against the 2026-08-31
# drafts: headings, paragraphs, ul/ol, blockquotes, one table family, hr, bold/italic, one plain
# link). All text is escaped before tagging; emitted markup is a fixed, safe vocabulary.

_TABLE_DIVIDER_CELL_RE = re.compile(r"^\s*:?-{3,}:?\s*$")
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_UNORDERED_RE = re.compile(r"^[-*]\s+(.*)$")
_ORDERED_RE = re.compile(r"^\d+[.)]\s+(.*)$")


def _inline(text: str) -> str:
    """Escape, then apply the inline constructs (link → bold → italic) to already-safe text."""
    escaped = _html_mod.escape(text, quote=False)
    escaped = _LINK_RE.sub(
        lambda m: f'<a href="{_html_mod.escape(m.group(2), quote=True)}">{m.group(1)}</a>', escaped
    )
    escaped = _BOLD_RE.sub(r"<strong>\1</strong>", escaped)
    escaped = _ITALIC_RE.sub(r"<em>\1</em>", escaped)
    return escaped


def _is_table_divider(line: str) -> bool:
    """`| --- | --- |` (dashes-only cells, optional colons/pipes) — a markdown table separator."""
    stripped = line.strip()
    if "|" not in stripped and "-" not in stripped:
        return False
    cells = [c for c in stripped.strip("|").split("|")]
    return bool(cells) and all(_TABLE_DIVIDER_CELL_RE.match(c) for c in cells)


def _split_table_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def markdown_to_html(markdown: str) -> str:
    """Render the small markdown subset the brain briefs use into safe HTML.

    Output is an HTML fragment (no ``<html>``/``<body>`` wrapper) — ``web/lib/pieces/draft-html.ts``
    accepts fragments (its body regex falls back to the whole string).
    """
    lines = markdown.splitlines()
    out: list[str] = []
    i = 0
    n = len(lines)
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            out.append(f"<p>{_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            i += 1
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            i += 1
            continue

        if stripped in {"---", "***", "___"}:
            flush_paragraph()
            out.append("<hr>")
            i += 1
            continue

        # Table: a `|`-row immediately followed by the dashes divider row.
        if "|" in stripped and i + 1 < n and _is_table_divider(lines[i + 1]):
            flush_paragraph()
            header = _split_table_row(stripped)
            i += 2
            rows: list[list[str]] = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(_split_table_row(lines[i]))
                i += 1
            thead = "".join(f"<th>{_inline(c)}</th>" for c in header)
            body = "".join(
                "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in row) + "</tr>" for row in rows
            )
            out.append(f"<table><thead><tr>{thead}</tr></thead><tbody>{body}</tbody></table>")
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            quote_lines: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            # A blank quoted line splits paragraphs inside the blockquote.
            parts = "\n".join(quote_lines).split("\n\n")
            inner = "".join(
                f"<p>{_inline(' '.join(p for p in part.splitlines() if p))}</p>"
                for part in parts
                if part.strip()
            )
            out.append(f"<blockquote>{inner}</blockquote>")
            continue

        unordered = _UNORDERED_RE.match(stripped)
        if unordered:
            flush_paragraph()
            items: list[str] = []
            while i < n:
                m = _UNORDERED_RE.match(lines[i].strip())
                if not m:
                    break
                items.append(m.group(1))
                i += 1
            lis = "".join(f"<li>{_inline(item)}</li>" for item in items)
            out.append(f"<ul>{lis}</ul>")
            continue

        ordered = _ORDERED_RE.match(stripped)
        if ordered:
            flush_paragraph()
            items = []
            while i < n:
                m = _ORDERED_RE.match(lines[i].strip())
                if not m:
                    break
                items.append(m.group(1))
                i += 1
            lis = "".join(f"<li>{_inline(item)}</li>" for item in items)
            out.append(f"<ol>{lis}</ol>")
            continue

        paragraph.append(stripped)
        i += 1

    flush_paragraph()
    return "\n".join(out)


# --- Drive-friendly document wrapper -------------------------------------------------------------
#
# Google Drive's HTML-to-Docs conversion maps <h1>–<h6> to "Heading 1"–"Heading 6" paragraph
# styles and <ul>/<ol>/<table> to their Doc equivalents, but a bare HTML fragment with no styling
# renders as a plain, default-styled document. This wrapper surrounds a markdown-to-HTML fragment
# with a minimal, professional, print-oriented document so the converted Google Doc looks polished
# — proper heading sizes and weights, table borders, callout styling on blockquotes, and clean
# list indentation — without depending on any external CSS framework.

# The CSS below is deliberately inline-friendly (pt units, conservative font stack, no webfont
# imports) so Drive import does not strip or degrade it. It targets the exact elements
# markdown_to_html emits: h1–h6, p, ul, ol, li, table/thead/tbody/tr/th/td, blockquote/p,
# a, strong, em, hr, code.

_DOC_STYLE = dedent("""\
    body {
      font-family: 'Helvetica Neue', Arial, sans-serif;
      font-size: 11pt;
      line-height: 1.5;
      color: #222222;
      max-width: 7.0in;
      padding: 0.6in 0.75in;
      margin: 0 auto;
    }
    h1 { font-size: 18pt; font-weight: 700; color: #1a1a1a; margin: 24pt 0 10pt 0; }
    h2 { font-size: 14pt; font-weight: 600; color: #2d2d2d; margin: 18pt 0 8pt 0;
         padding-bottom: 4pt; border-bottom: 1pt solid #e0e0e0; }
    h3 { font-size: 12pt; font-weight: 600; color: #3d3d3d; margin: 14pt 0 6pt 0; }
    h4 { font-size: 11pt; font-weight: 600; color: #4d4d4d; margin: 12pt 0 4pt 0; }
    h5, h6 { font-size: 11pt; font-weight: 600; color: #5d5d5d; margin: 10pt 0 4pt 0; }
    p { margin: 0 0 8pt 0; }
    ul, ol { margin: 0 0 8pt 0; padding-left: 24pt; }
    li { margin: 0 0 4pt 0; }
    table { border-collapse: collapse; width: 100%; margin: 12pt 0; }
    th { background: #f5f5f5; font-weight: 600; text-align: left;
         padding: 6pt 8pt; border: 1pt solid #d0d0d0; }
    td { padding: 4pt 8pt; border: 1pt solid #d0d0d0; vertical-align: top; }
    blockquote { margin: 12pt 0; padding: 8pt 16pt;
                 border-left: 4pt solid #e8e8e8; background: #fafafa; color: #3d3d3d; }
    blockquote p { margin: 0; }
    blockquote strong { color: #2d2d2d; }
    a { color: #1a73e8; }
    strong { font-weight: 700; }
    em { font-style: italic; }
    hr { border: none; border-top: 1pt solid #e0e0e0; margin: 16pt 0; }
    code { font-family: 'SF Mono', 'Consolas', 'Courier New', monospace;
           font-size: 10pt; background: #f0f0f0; padding: 1pt 4pt; border-radius: 2pt; }
""")

_DOC_TEMPLATE = dedent("""\
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="utf-8">
    <style>
    {style}
    </style>
    </head>
    <body>
    {content}
    </body>
    </html>
""")

# Any opening <html> or <body> tag — the presence of either means the HTML is already a full
# document (or at least wrapped), so we leave it alone.
_HAS_DOC_TAG_RE = re.compile(r"<(html|body)\b", re.IGNORECASE)


def ensure_doc_html(html_fragment: str) -> str:
    """Wrap a bare HTML fragment in a full, styled document suitable for Google Drive import.

    Drive's HTML-to-Docs conversion respects document-level CSS; a fragment without a ``<style>``
    block renders with only default Doc styles. This function detects whether the input already
    carries ``<html>`` or ``<body>`` tags (i.e. it is a pipeline piece's ``draft.html``) or is a
    raw fragment (from :func:`markdown_to_html` for brain-authored pieces), wrapping only the
    latter while passing full documents through unchanged.
    """
    if _HAS_DOC_TAG_RE.search(html_fragment):
        return html_fragment
    return _DOC_TEMPLATE.format(style=_DOC_STYLE, content=html_fragment)
