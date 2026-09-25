"""Per-piece evidence: claim-level citations + the full retrieval/source list.

A piece's semantic ``draft.html`` annotates its factual claims with footnote-style citation
chips — ``<sup class="fn"><a href="#src1" id="r1">1</a></sup>`` — whose targets are the
``<li id="src1">…</li>`` entries of the draft's own Sources section. Alongside the draft, the
brain keeps ``sources.md``: the full provenance document (research citations with URLs, GAP
status, clearances). Together those two files ARE the piece's evidence trail — no new store is
needed, only a read-time parse (same "derived view over existing records" discipline
``app.piece_detail``'s activity log follows).

Everything here is pure, dependency-free (regex + ``html.unescape`` — the same tradeoff
``app.piece_md`` and ``web/lib/pieces/draft-html.ts`` already make) and directly unit-testable;
``build_piece_detail`` (``app.piece_detail``) calls :func:`build_piece_evidence` and carries the
result onto ``PieceDetailResponse`` (``app.schemas``) for the piece-detail screen's citation
chips + expandable sources drawer.

Deliberately read-only and lenient: an unparseable draft or absent ``sources.md`` degrades to
empty lists, never an error — a piece without evidence annotations simply shows no drawer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import unescape

from app.schemas import EvidenceCitationOut, EvidenceSourceOut

# A claim-level citation chip: <sup class="fn"><a href="#src1" id="r1">1</a></sup>. Tolerant of
# attribute order on both tags (class before/after other attrs, id before/after href) — the
# brain-authored drafts follow one shape today, but a hand edit shouldn't silently drop chips.
_CITE_CHIP_RE = re.compile(
    r"<sup\b(?P<supattrs>[^>]*)>(?P<inner>.*?)</sup>",
    re.IGNORECASE | re.DOTALL,
)
_CLASS_RE = re.compile(r'class="[^"]*\bfn\b[^"]*"', re.IGNORECASE)
_HREF_ANCHOR_RE = re.compile(r'href="#([^"]+)"', re.IGNORECASE)
_ID_RE = re.compile(r'id="([^"]+)"', re.IGNORECASE)
_A_RE = re.compile(r"<a\b[^>]*>(?P<chip>.*?)</a>", re.IGNORECASE | re.DOTALL)

# Source list entries: <li id="src1">…</li> (no nested lists in the brain's source sections).
_LI_RE = re.compile(r"<li\b(?P<attrs>[^>]*)>(?P<body>.*?)</li>", re.IGNORECASE | re.DOTALL)
_URL_RE = re.compile(r'href="(https?://[^"]+)"', re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]*>")
_WS_RE = re.compile(r"\s+")

# sources.md bullets (with indented continuation lines) carrying at least one URL.
_MD_BULLET_RE = re.compile(r"^[-*]\s+(?P<text>.*)$")
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(?P<title>.*?)\s*$")
_MD_URL_RE = re.compile(r"https?://[^\s)\]>,;]+")

# The footnote back-link glyph (&#8617; / ↩) is navigation chrome, not source text.
_BACKLINK_RE = re.compile(r"[\u21a9]")


@dataclass(frozen=True)
class PieceEvidence:
    """The parsed evidence trail for one piece — both lists empty when nothing is annotated."""

    sources: list[EvidenceSourceOut] = field(default_factory=list)
    citations: list[EvidenceCitationOut] = field(default_factory=list)


def build_piece_evidence(draft_html: str | None, sources_md: str | None) -> PieceEvidence:
    """Parse both evidence carriers for one piece into structured drawer/chip data.

    ``draft_html`` yields the claim-level citations (chips) plus the footnote source entries
    they reference; ``sources_md`` yields the full research-citation list. Footnote sources come
    first (they're the ones the visible chips point at), sources.md entries after.
    """
    sources: list[EvidenceSourceOut] = []
    citations: list[EvidenceCitationOut] = []
    if draft_html:
        footnotes, citations = _parse_draft(draft_html)
        sources.extend(footnotes)
    if sources_md:
        sources.extend(_parse_sources_md(sources_md))
    return PieceEvidence(sources=sources, citations=citations)


def _plain_text(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    text = unescape(text)
    text = _BACKLINK_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def _parse_draft(draft_html: str) -> tuple[list[EvidenceSourceOut], list[EvidenceCitationOut]]:
    """The draft's claim chips + the footnote source entries behind them.

    A ``<li id="…">`` counts as a source entry when a chip references it (``href="#id"``) or its
    id follows the brain's ``src…`` convention — union, in document order, deduped.
    """
    citations: list[EvidenceCitationOut] = []
    referenced: set[str] = set()
    for chip_match in _CITE_CHIP_RE.finditer(draft_html):
        if not _CLASS_RE.search(chip_match.group("supattrs")):
            continue
        anchor = _A_RE.search(chip_match.group("inner"))
        if anchor is None:
            continue
        href = _HREF_ANCHOR_RE.search(anchor.group(0))
        if href is None:
            continue
        source_id = href.group(1)
        anchor_id_match = _ID_RE.search(anchor.group(0))
        chip_label = _plain_text(anchor.group("chip"))
        if not chip_label:
            chip_label = _plain_text(chip_match.group("inner"))
        referenced.add(source_id)
        citations.append(
            EvidenceCitationOut(
                chip=chip_label,
                source_id=source_id,
                anchor_id=anchor_id_match.group(1) if anchor_id_match else None,
            )
        )

    sources: list[EvidenceSourceOut] = []
    seen: set[str] = set()
    for li in _LI_RE.finditer(draft_html):
        id_match = _ID_RE.search(li.group("attrs"))
        if id_match is None:
            continue
        source_id = id_match.group(1)
        is_source = source_id in referenced or source_id.lower().startswith("src")
        if not is_source or source_id in seen:
            continue
        seen.add(source_id)
        urls = _URL_RE.findall(li.group("body"))
        label = _plain_text(li.group("body"))
        if not label and not urls:
            continue
        chip = next(
            (c.chip for c in citations if c.source_id == source_id), None
        )
        sources.append(
            EvidenceSourceOut(
                id=source_id,
                kind="footnote",
                chip=chip,
                label=label,
                urls=urls,
                section=None,
            )
        )
    return sources, citations


def _parse_sources_md(sources_md: str) -> list[EvidenceSourceOut]:
    """The research-citation list out of ``sources.md``: every bullet carrying at least one
    URL, grouped under its nearest heading (the file's own section names — "Research
    citations", "Provenance", …). URL-less bullets (GAP notes, checklists, council records) are
    annotations, not retrieval sources, and are deliberately left out of the drawer's list."""
    entries: list[EvidenceSourceOut] = []
    section: str | None = None
    bullet: list[str] | None = None
    index = 0

    def flush() -> None:
        nonlocal bullet, index
        if bullet is None:
            return
        text = _WS_RE.sub(" ", " ".join(bullet)).strip()
        bullet = None
        urls = _MD_URL_RE.findall(text)
        if not urls:
            return
        label = _MD_URL_RE.sub(" ", text)
        label = _WS_RE.sub(" ", label).strip(" \t-—·•:;")
        if not label:
            label = urls[0]
        index += 1
        entries.append(
            EvidenceSourceOut(
                id=f"sources-md-{index}",
                kind="sources-md",
                chip=None,
                label=label,
                urls=urls,
                section=section,
            )
        )

    for line in sources_md.splitlines():
        heading = _MD_HEADING_RE.match(line)
        if heading:
            flush()
            section = heading.group("title").strip() or None
            continue
        bullet_match = _MD_BULLET_RE.match(line)
        if bullet_match:
            flush()
            bullet = [bullet_match.group("text")]
            continue
        if bullet is not None:
            if line.strip():
                bullet.append(line.strip())
            else:
                flush()
    flush()
    return entries
