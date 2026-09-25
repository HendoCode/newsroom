"""Tests for the per-piece evidence parse (claim-level citations + retrieval/source list).

Runs against both hand-built shapes and the REAL checked-in fixture brain drafts
(``agents/tests/fixtures/brain/drafts/``) — a fixture written to the parser's own assumptions
would prove nothing about what the brain actually authors (same discipline as
``test_transcript.py``'s round-trip rule).
"""

from __future__ import annotations

from pathlib import Path

from app.evidence import build_piece_evidence

FIXTURE_DRAFTS = Path(__file__).parent / "fixtures" / "brain" / "drafts"


def _fixture(slug: str, name: str) -> str:
    return (FIXTURE_DRAFTS / slug / name).read_text(encoding="utf-8")


# --- hand-built shapes ------------------------------------------------------------------------


DRAFT_WITH_CITES = """<html><body>
<p>Claim one.<sup class="fn"><a href="#src1" id="r1">1</a></sup></p>
<p>Claim two.<sup class="fn"><a id="r2" href="#src2">2</a></sup></p>
<p>An unlinked note<sup>not a chip</sup> stays prose.</p>
<section>
  <ol>
    <li id="src1">The origin call. <a href="#r1">&#8617;</a></li>
    <li id="src2">AWS docs. <a href="https://docs.aws.amazon.com/x">docs.aws.amazon.com/x</a>
      <a href="#r2">&#8617;</a></li>
    <li id="unrelated">Not a source — no src id, no chip.</li>
  </ol>
</section>
</body></html>"""


def test_parse_draft_chips_and_footnote_sources() -> None:
    evidence = build_piece_evidence(DRAFT_WITH_CITES, None)
    assert [(c.chip, c.source_id, c.anchor_id) for c in evidence.citations] == [
        ("1", "src1", "r1"),
        ("2", "src2", "r2"),
    ]
    footnotes = [s for s in evidence.sources if s.kind == "footnote"]
    assert [s.id for s in footnotes] == ["src1", "src2"]
    assert footnotes[0].chip == "1"
    assert footnotes[0].urls == []
    # Plain-text label: tags stripped, entities unescaped, back-link glyph gone.
    assert footnotes[0].label == "The origin call."
    assert footnotes[1].urls == ["https://docs.aws.amazon.com/x"]
    # A <li> that is neither src-prefixed nor chip-referenced is not a source entry.
    assert all(s.id != "unrelated" for s in evidence.sources)


def test_attribute_order_and_class_tolerances() -> None:
    html = (
        '<p>x<sup id="s" class="note fn small"><a id="r9" href="#srcbook">'
        'book</a></sup></p><ol><li id="srcbook">A book.</li></ol>'
    )
    evidence = build_piece_evidence(html, None)
    assert len(evidence.citations) == 1
    assert evidence.citations[0].chip == "book"
    assert evidence.citations[0].source_id == "srcbook"
    assert evidence.citations[0].anchor_id == "r9"
    assert [s.id for s in evidence.sources] == ["srcbook"]


def test_sup_without_fn_class_is_not_a_chip() -> None:
    html = '<p>10<sup>2</sup> math, not a citation.</p>'
    evidence = build_piece_evidence(html, None)
    assert evidence.citations == []
    assert evidence.sources == []


SOURCES_MD = """# Sources & Handoff — demo

## Provenance
Everything traces to the call.

## Research citations (2026-07-28)
- CloudWatch OTLP endpoints — https://docs.aws.amazon.com/otlp.html
- AgentCore Observability routes traces by default —
  https://docs.aws.amazon.com/observability.html · https://aws.amazon.com/whats-new/
- A note with no URL stays out of the source list.

## Open GAPs
- [A4] needs owner sign-off, no link here.
"""


def test_parse_sources_md_bullets_with_urls_only() -> None:
    evidence = build_piece_evidence(None, SOURCES_MD)
    assert [s.id for s in evidence.sources] == ["sources-md-1", "sources-md-2"]
    first, second = evidence.sources
    assert first.kind == "sources-md"
    assert first.section == "Research citations (2026-07-28)"
    assert first.urls == ["https://docs.aws.amazon.com/otlp.html"]
    assert "CloudWatch OTLP endpoints" in first.label
    assert "https://" not in first.label
    # Continuation lines fold into one bullet; both URLs survive; the · separator is cleaned.
    assert second.urls == [
        "https://docs.aws.amazon.com/observability.html",
        "https://aws.amazon.com/whats-new/",
    ]
    assert "AgentCore Observability routes traces by default" in second.label


def test_no_evidence_at_all_degrades_to_empty_lists() -> None:
    evidence = build_piece_evidence(None, None)
    assert evidence.sources == [] and evidence.citations == []
    evidence = build_piece_evidence("<html><body><p>plain</p></body></html>", "## nothing\n- no urls\n")
    assert evidence.sources == [] and evidence.citations == []


def test_draft_footnotes_come_before_sources_md_entries() -> None:
    evidence = build_piece_evidence(DRAFT_WITH_CITES, SOURCES_MD)
    kinds = [s.kind for s in evidence.sources]
    assert kinds == ["footnote", "footnote", "sources-md", "sources-md"]


# --- the real fixture brain drafts --------------------------------------------------------------


def test_real_fixture_aws_gsi_faq() -> None:
    evidence = build_piece_evidence(
        _fixture("aws-gsi-faq", "draft.html"), _fixture("aws-gsi-faq", "sources.md")
    )
    # The draft carries five footnote chips (1–5), each resolving to its src entry.
    assert [c.chip for c in evidence.citations] == ["1", "2", "3", "4", "5"]
    by_id = {c.source_id: c for c in evidence.citations}
    assert by_id["src1"].anchor_id == "r1"
    footnotes = [s for s in evidence.sources if s.kind == "footnote"]
    assert [s.id for s in footnotes] == ["src1", "src2", "src3", "src4", "src5"]
    # Chip labels round-trip onto the source entries.
    assert [s.chip for s in footnotes] == ["1", "2", "3", "4", "5"]
    # src2 is a public AWS doc link; src1 (the call) has no URL.
    src2 = next(s for s in footnotes if s.id == "src2")
    assert src2.urls == [
        "https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html"
    ]
    assert next(s for s in footnotes if s.id == "src1").urls == []
    # sources.md research citations land too, under their own section.
    md_entries = [s for s in evidence.sources if s.kind == "sources-md"]
    assert md_entries, "the real sources.md must yield research-citation entries"
    assert all(s.urls for s in md_entries)
    research = [s for s in md_entries if s.section and s.section.startswith("Research citations")]
    assert len(research) >= 5


def test_real_fixture_token_vs_storage_has_no_chips_but_has_sources() -> None:
    evidence = build_piece_evidence(
        _fixture("token-vs-storage", "draft.html"), _fixture("token-vs-storage", "sources.md")
    )
    # That draft authors no footnote chips — honestly no citations, but sources.md's
    # research-citation list still fills the drawer.
    assert evidence.citations == []
    assert all(s.kind == "sources-md" for s in evidence.sources)
    assert len(evidence.sources) >= 10
