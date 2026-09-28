"""APPLY (rewrite) tests (context report §8b; D14 Opus tier)."""

from __future__ import annotations

import pytest

from app.interview.transcript import strip_legacy_research_markers
from app.llm.pricing import Usage
from app.llm.provider import LLMProvider, LLMResult
from app.llm.tiering import MODEL_GLM5
from app.models import Piece
from app.orchestration.retry import PermanentStepError, RefusalError
from app.review.rewrite import _split_editorial, count_open_gaps, rewrite_revision

GOOD_REWRITE = """<!DOCTYPE html>
<html><head><title>t</title></head><body>
<article><h1>Title</h1><p>Some tightened prose.</p></article>
<hr>
<section class="editorial" aria-label="Editorial annotations, not for publication">
<h3>Editorial annotations</h3>
<p><span class="tag">[GAP]</span> still need X</p>
<p><span class="tag">[GAP CLOSED]</span> resolved this round</p>
</section>
</body></html>"""

BAD_INLINE_GAP = (
    '<html><body><article><p>Some prose [GAP] leaked into the body.</p></article>'
    '<section class="editorial"></section></body></html>'
)


class RecordingProvider(LLMProvider):
    def __init__(self, results: list[LLMResult]) -> None:
        self.calls: list[dict[str, object]] = []
        self._results = list(results)

    async def complete(self, *, step, model, system, messages, max_tokens, effort=None, tools=None, cache=False, budget=None):
        self.calls.append(
            {"step": step, "model": model, "system": system, "messages": messages, "max_tokens": max_tokens}
        )
        return self._results.pop(0)

    def stream(self, **kwargs):
        raise NotImplementedError

    async def count_tokens(self, *, model, system, messages):
        return 0


def test_split_editorial_and_count_open_gaps():
    body, editorial = _split_editorial(GOOD_REWRITE)
    assert "<article>" in body
    assert editorial.startswith('<section class="editorial"')
    assert count_open_gaps(GOOD_REWRITE) == 1  # 1 open [GAP], 1 [GAP CLOSED] excluded


async def test_rewrite_happy_path_assembles_context_and_returns_html(git_brain, content_store):
    piece = Piece(slug="the-board-on-the-wall", voice="demo-mira")
    provider = RecordingProvider(
        [LLMResult(text=GOOD_REWRITE, model=MODEL_GLM5, stop_reason="end_turn", usage=Usage(input_tokens=5, output_tokens=5), cost_usd=0.0)]
    )

    result = await rewrite_revision(
        provider,
        brain=git_brain,
        content=content_store,
        piece=piece,
        fixes=["tighten the opening sentence", "cut the redundant clause in paragraph two"],
        round_number=2,
    )

    assert result.draft_html == GOOD_REWRITE
    call = provider.calls[0]
    assert call["model"] == MODEL_GLM5  # REWRITE now GLM5 live default (superseded Opus assumption)

    system_texts = call["system"]
    assert any(git_brain.read_engine("feedback-intake") in t for t in system_texts)
    assert any(git_brain.read_engine("2-draft") in t for t in system_texts)
    voice = git_brain.read_voice("demo-mira")
    assert any(voice.voice_guide in t for t in system_texts)

    transcript_text = strip_legacy_research_markers(
        content_store.read_transcript("the-board-on-the-wall")
    )
    assert any(transcript_text in t for t in system_texts)
    revision_text = content_store.read_draft("the-board-on-the-wall")
    assert any(revision_text in t for t in system_texts)

    tail = call["messages"][0]["content"]
    assert "round 2" in tail
    assert "tighten the opening sentence" in tail
    assert "cut the redundant clause in paragraph two" in tail

    # single-call step: no cache breakpoint (§8b — little benefit, skip).
    assert all("cache_control" not in b for b in call["system"])


async def test_rewrite_raises_refusal_error(git_brain, content_store):
    piece = Piece(slug="the-board-on-the-wall", voice="demo-mira")
    provider = RecordingProvider(
        [LLMResult(text="", model=MODEL_GLM5, stop_reason="refusal", usage=Usage(), cost_usd=0.0)]
    )

    with pytest.raises(RefusalError):
        await rewrite_revision(provider, brain=git_brain, content=content_store, piece=piece, fixes=["x"], round_number=1)


async def test_rewrite_empty_response_is_permanent_error(git_brain, content_store):
    piece = Piece(slug="the-board-on-the-wall", voice="demo-mira")
    provider = RecordingProvider(
        [LLMResult(text="   ", model=MODEL_GLM5, stop_reason="end_turn", usage=Usage(), cost_usd=0.0)]
    )

    with pytest.raises(PermanentStepError):
        await rewrite_revision(provider, brain=git_brain, content=content_store, piece=piece, fixes=["x"], round_number=1)


async def test_rewrite_rejects_inline_gap_marker(git_brain, content_store):
    piece = Piece(slug="the-board-on-the-wall", voice="demo-mira")
    provider = RecordingProvider(
        [LLMResult(text=BAD_INLINE_GAP, model=MODEL_GLM5, stop_reason="end_turn", usage=Usage(), cost_usd=0.0)]
    )

    with pytest.raises(PermanentStepError):
        await rewrite_revision(provider, brain=git_brain, content=content_store, piece=piece, fixes=["x"], round_number=1)


async def test_rewrite_without_transcript_grounds_in_revision_and_sources(git_brain, content_store):
    """cmw-lessons-loop Ship 1 regression: a brain-authored (brain_synced) piece legitimately
    has no transcript.md, and this guard used to raise a PermanentStepError that failed
    reviews-done — and therefore the whole doc-to-lessons loop — permanently for every such
    piece (all 11 minted pieces on live when this was found). The rewrite must instead ground in
    the existing revision + sources.md with the shared invent-nothing block."""
    content_store.commit_revision(
        "seeded-no-transcript",
        "<html><body><article><p>seeded straight into review</p></article></body></html>",
        sources_md="- [AWS blog](https://example.com/aws) — the cited figure",
        message="seed directly into review, no interview ever run",
    )
    piece = Piece(slug="seeded-no-transcript", voice="demo-mira")
    provider = RecordingProvider(
        [LLMResult(text=GOOD_REWRITE, model=MODEL_GLM5, stop_reason="end_turn", usage=Usage(input_tokens=5, output_tokens=5), cost_usd=0.0)]
    )

    result = await rewrite_revision(
        provider, brain=git_brain, content=content_store, piece=piece, fixes=["x"], round_number=1
    )

    assert result.draft_html == GOOD_REWRITE
    call = provider.calls[0]
    system_texts = call["system"]
    revision_text = content_store.read_draft("seeded-no-transcript")
    assert any(revision_text in t for t in system_texts)
    sources_text = content_store.read_sources("seeded-no-transcript")
    assert any(sources_text in t for t in system_texts)
    # The transcript really is absent — and the grounding block substitutes for it.
    with pytest.raises(OSError):
        content_store.read_transcript("seeded-no-transcript")
    grounding = [t for t in system_texts if "no interview transcript" in t.lower()]
    assert grounding, "the shared invent-nothing grounding block must be in the stable prefix"
    assert "invent nothing" in grounding[0].lower()
    assert "drafts/seeded-no-transcript/transcript.md is missing" in grounding[0]


async def test_rewrite_without_transcript_or_draft_html_falls_back_to_piece_md(git_brain, content_store):
    """The direct-authored brain-brief shape (no draft.html at all — content lives in piece.md's
    content section): the rewrite's revision read must fall back the same way mint does
    (``app.piece_detail.draft_content_from_files``), never crash on the missing draft.html."""
    slug = "amazon-quick-hendo"
    content_store.repo.write_text(
        f"drafts/{slug}/piece.md",
        "---\ntitle: Amazon Quick + Hendo\nvoice: demo-dana\n---\n\n# The seller playbook\n\nBody.\n",
    )
    content_store.repo.commit([f"drafts/{slug}/piece.md"], "brain authored piece", author_name="b", author_email="b@x")
    piece = Piece(slug=slug, voice="demo-dana")
    provider = RecordingProvider(
        [LLMResult(text=GOOD_REWRITE, model=MODEL_GLM5, stop_reason="end_turn", usage=Usage(input_tokens=5, output_tokens=5), cost_usd=0.0)]
    )

    result = await rewrite_revision(
        provider, brain=git_brain, content=content_store, piece=piece, fixes=["x"], round_number=1
    )

    assert result.draft_html == GOOD_REWRITE
    system_texts = provider.calls[0]["system"]
    # The piece.md content section, rendered to HTML, is the revision being edited.
    assert any("seller playbook" in t for t in system_texts)
    assert any("no interview transcript" in t.lower() for t in system_texts)


async def test_rewrite_without_transcript_or_any_content_is_legible_permanent_error(git_brain, content_store):
    """The surviving hard stop (narrowed by cmw-lessons-loop Ship 1): a piece with no transcript
    AND no readable revision content at all has nothing to ground in — a legible, non-leaking
    precondition failure naming the piece and what's missing (the surviving requirement of the
    original cmw-incorporate-missing-transcript fix: never a raw `FileNotFoundError` leaking
    through as the job's failure message), raised before ever calling the model."""
    piece = Piece(slug="empty-piece", voice="demo-mira")
    provider = RecordingProvider([])

    with pytest.raises(PermanentStepError) as exc_info:
        await rewrite_revision(
            provider, brain=git_brain, content=content_store, piece=piece, fixes=["x"], round_number=1
        )

    message = str(exc_info.value)
    assert "Errno" not in message and "FileNotFoundError" not in message
    assert "transcript" in message.lower()
    assert "empty-piece" in message
    assert provider.calls == []
