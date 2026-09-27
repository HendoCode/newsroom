"""Regression guard for cmw-phantom-edits-from-doc-roundtrip, built from REAL Google Docs.

A green test suite never caught any of the three prior defects in this exact area (see
'newsroom' CLAUDE.md's draft-step/heading-bold/banner sharp-edge entries) — each was
invisible until someone actually round-tripped a real Doc. So this file's fixtures are not
hand-written assumptions about what Google's export looks like; they are byte-for-byte captures
from a real throwaway mint against a real Google account, done once while diagnosing/fixing this
ticket (via `createDocFromHTML` + a real `text/html` export — the exact calls
`ReviewMintService`/`HttpReviewDocsClient` make in production), then deleted from Drive:

- `fixtures/review/draft.html` — a `draft.html`-shaped revision with three heading levels, an
  editorial block, and no emphasis anywhere (mirrors a fresh, never-reviewed piece).
- `fixtures/review/doc_export_{internal,external}_untouched.html` — that revision minted via
  `render_for_share_mode`, then exported immediately with ZERO human edits. This is Hendo's exact
  repro ("the minted doc has not been touched by me in any way, shape, or form") and reproduced,
  pre-fix, the reported phantom emphasis edits (headings) and, on the external side, the phantom
  "reviewer added the DRAFT banner" item.
- `fixtures/review/doc_export_internal_edited.html` — the SAME internal Doc after real edits made
  through the live Docs API: bolding a mid-sentence phrase, italicizing another, adding a new
  plain paragraph, and adding a new Heading 2 — the anti-over-normalization proof: a fix that
  silences the phantom heading-bold noise must not also silence these.

These fixtures pin real, previously-verified Google behavior so this can't regress silently; they
are not a substitute for re-running the live round trip if this area changes again.
"""

from __future__ import annotations

from pathlib import Path

from app.models import ShareMode
from app.review.collect import _drop_draft_banner, diff_blocks
from app.review.mint import render_for_share_mode
from app.review.structure import extract_blocks

_FIXTURES = Path(__file__).parent / "fixtures" / "review"


def _read(name: str) -> str:
    return (_FIXTURES / name).read_text()


def _diff_against_export(raw_draft: str, export_html: str, share_mode: ShareMode) -> list:
    original = render_for_share_mode(raw_draft, share_mode)
    original_blocks = _drop_draft_banner(extract_blocks(original))
    current_blocks = _drop_draft_banner(extract_blocks(export_html))
    return diff_blocks(original_blocks, current_blocks)


def test_untouched_internal_doc_reports_zero_edits():
    """Hendo's exact repro: mint, never touch it, collect. Must report zero — before this fix, a
    real internal-round Doc like this one reported one phantom "emphasized as bold" item per
    heading (three, in this fixture)."""
    raw_draft = _read("draft.html")
    export = _read("doc_export_internal_untouched.html")

    assert _diff_against_export(raw_draft, export, ShareMode.internal) == []


def test_untouched_external_doc_reports_zero_edits():
    """Same repro on an external round — before this fix this also carried a phantom "reviewer
    added the DRAFT banner" item, since Drive's HTML-to-Docs conversion turns that banner's
    non-block <div> into a real <p> on export."""
    raw_draft = _read("draft.html")
    export = _read("doc_export_external_untouched.html")

    assert _diff_against_export(raw_draft, export, ShareMode.external) == []


def test_real_edits_on_a_real_doc_are_still_detected():
    """The anti-over-normalization proof: a bolded mid-sentence phrase, an italicized phrase, a
    brand new paragraph, and a brand new heading — all made through the live Docs API on the same
    Doc the untouched-internal fixture above came from — must all still register. A fix that
    stripped all emphasis before comparing would pass the two tests above while silently failing
    this one."""
    raw_draft = _read("draft.html")
    export = _read("doc_export_internal_edited.html")

    items = _diff_against_export(raw_draft, export, ShareMode.internal)
    asks = [i.ask for i in items]

    assert len(items) == 3
    assert any("emphasized 'a lot' as bold" in a for a in asks)
    assert any("emphasized 'cheap for the first 50 TB' as italic" in a for a in asks)
    assert any(
        "[paragraph] 'A brand new paragraph the reviewer added by hand.'" in a
        and "[Heading 2] 'A New Reviewer Heading'" in a
        for a in asks
    )


def test_diffing_the_same_export_twice_is_stable():
    """Confirms the diff itself is deterministic over identical input (independent re-exports of
    the same untouched Doc were separately confirmed byte-identical against the real API while
    diagnosing this ticket — see the PR description)."""
    raw_draft = _read("draft.html")
    export = _read("doc_export_external_untouched.html")

    first = _diff_against_export(raw_draft, export, ShareMode.external)
    second = _diff_against_export(raw_draft, export, ShareMode.external)

    assert first == second == []
