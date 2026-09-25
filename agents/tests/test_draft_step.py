"""Draft step tests (engine/2-draft.md; cmw-context-assembly report §6).

Covers, per the acceptance criteria:
- context assembly reads the full verbatim transcript (never summarized), the voice pack in
  override order (lessons last → override the guide), and any partner fact files the piece touches;
- the Opus tier is requested through the tiering seam, never hardcoded;
- a committed ``draft.html`` Revision on success, with the open-GAP count mirrored onto the
  Piece's Mongo work-state, and the state machine advancing drafting → council;
- a refusal or an inline (non-editorial-block) GAP marker fails the step without committing;
- failure flags the piece (flag-not-rollback) via the real ``PieceMachine``/``JobRunner``.

Zero external deps: the LLM path runs on a small recording fake provider (no ``anthropic``
package, no key, no network); the Git suite uses the shared ``git_brain``/``content_store``
fixtures (a temp-repo copy of the fixture brain, ``agents/tests/fixtures/brain/``); the work-state store is
the in-memory ``store`` fixture.
"""

from __future__ import annotations

import pytest

from app.interview.transcript import strip_legacy_research_markers
from app.llm import MODEL_GLM5, MODEL_OPUS, LLMProvider, LLMResult, RunBudget, Usage
from app.models import (
    DistributionIntent,
    Job,
    JobStatus,
    JobType,
    Narrative,
    Piece,
    PieceStage,
    Spike,
    SpikeOrigin,
    SpikeOriginKind,
)
from app.orchestration import JobRunner, PieceMachine, StepRegistry
from app.orchestration.draft_step import DraftStep, _count_open_gaps, _split_editorial
from app.orchestration.retry import PermanentStepError, RefusalError
from app.orchestration.steps import StepContext
from app.orchestration.stub_step import StubStep

GOOD_DRAFT = """<!DOCTYPE html>
<html><head><title>t</title></head><body>
<article><h1>Title</h1><p>Some prose with a call-to-action link.</p></article>
<hr>
<section class="editorial" aria-label="Editorial annotations, not for publication">
<h3>Editorial annotations</h3>
<p><span class="tag">[GAP]</span> need X</p>
<p><span class="tag">[GAP: need Y]</span> need Y</p>
<p><span class="tag">[GAP CLOSED]</span> already resolved</p>
</section>
</body></html>"""

BAD_DRAFT_INLINE_GAP = (
    '<html><body><article><p>Some prose [GAP] leaked into the body.</p></article>'
    '<section class="editorial"></section></body></html>'
)

# A realistically-shaped model output: a well-formed, clearly-separated, non-published trailing
# block — the model followed "put GAPs in a block at the end, not inline" faithfully — but under
# a <div class="gaps"> the model invented itself, echoing engine/2-draft.md's own "[GAP: ...]"
# vocabulary, rather than the literal "editorial" class the guard's regex requires. Modeled on a
# real captured Opus response (live-reproduced 2026-08-08) that tripped this guard three times in
# a row in production. This is EXPECTED to still fail until engine/2-draft.md states the exact
# required tag/class — see the PR description for the brain-side fix this documents.
REALISTIC_DRAFT_DIFFERENT_BLOCK_NAME = """<!DOCTYPE html>
<html><head><title>t</title></head><body>
<article><h1>Title</h1><p>Some prose with a call-to-action link.</p></article>
<!-- ============ NON-PUBLISHED — GAPS FOR THE LOOP ============ -->
<div class="gaps">
  <h3>Open gaps — do not publish until resolved</h3>
  <ul>
    <li><strong>[GAP: send volume]</strong> — how many were sent?</li>
  </ul>
</div>
</body></html>"""

# Same realistic shape, but using a tag other than <section> for the block — <section> was never
# a stated requirement anywhere (engine/2-draft.md, the sibling engine docs, or the domain
# model) — only the "editorial" class is the load-bearing convention.
REALISTIC_DRAFT_NON_SECTION_TAG = """<!DOCTYPE html>
<html><head><title>t</title></head><body>
<article><h1>Title</h1><p>Some prose with a call-to-action link.</p></article>
<div class="editorial" aria-label="Editorial annotations, not for publication">
  <h3>Editorial annotations</h3>
  <p><span class="tag">[GAP]</span> need X</p>
</div>
</body></html>"""


class RecordingProvider(LLMProvider):
    """A swappable double that queues canned :class:`LLMResult` values and records every call's
    kwargs, so tests can assert on the assembled prompt without any network/SDK dependency."""

    def __init__(self, results: list[LLMResult] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self._results = list(results) if results is not None else None

    async def complete(self, *, step, model, system, messages, max_tokens, effort=None, cache=False, budget=None):
        if budget is not None:
            budget.check()
        self.calls.append(
            {
                "step": step,
                "model": model,
                "system": system,
                "messages": messages,
                "max_tokens": max_tokens,
                "effort": effort,
            }
        )
        if self._results is not None:
            result = self._results.pop(0)
        else:
            result = LLMResult(
                text=GOOD_DRAFT, model=model, stop_reason="end_turn", usage=Usage(), cost_usd=0.0
            )
        if budget is not None:
            budget.charge(model, result.usage)
        return result

    def stream(self, *, step, model, system, messages, max_tokens, effort=None, budget=None):
        raise NotImplementedError("the draft step uses complete(), not stream()")

    async def count_tokens(self, *, model, system, messages):
        return 0


async def _noop_sleep(_seconds: float) -> None:
    """Injected into the runner so the retry-on-transient-error path doesn't really wait."""


async def _piece(store, stage: PieceStage, **extra) -> Piece:
    piece = Piece(
        slug=extra.pop("slug", "token-vs-storage"),
        voice=extra.pop("voice", "demo-mira"),
        stage=stage,
        **extra,
    )
    return await store.pieces.insert(piece)


async def _ctx(store, piece: Piece, provider: LLMProvider | None, budget=None) -> StepContext:
    job = await store.jobs.insert(
        Job(type=JobType.draft, piece_id=piece.id if piece else None, status=JobStatus.running)
    )
    return StepContext(job=job, store=store, budget=budget or RunBudget(), piece=piece, provider=provider)


# --- pure helpers: GAP-tag parsing (no editorial block, no closed-vs-open ambiguity) -------


def test_split_editorial_finds_the_boundary():
    html = '<p>body</p><section class="editorial">stuff</section>'
    body, editorial = _split_editorial(html)
    assert body == "<p>body</p>"
    assert editorial.startswith('<section class="editorial">')


def test_split_editorial_missing_section_is_all_body():
    body, editorial = _split_editorial("<p>no editorial block here</p>")
    assert body == "<p>no editorial block here</p>"
    assert editorial == ""


def test_count_open_gaps_excludes_closed_and_counts_both_tag_forms():
    html = (
        '<section class="editorial">'
        "[GAP] a [GAP: need b] [GAP CLOSED] already done"
        "</section>"
    )
    assert _count_open_gaps(html) == 2


# --- happy path: context assembly + commit + work-state mirror ----------------------------


async def test_draft_step_happy_path_commits_revision_and_mirrors_gaps(
    store, git_brain, content_store
):
    piece = await _piece(store, PieceStage.drafting, slug="token-vs-storage", voice="demo-mira", partners=["aws"])
    provider = RecordingProvider(
        results=[LLMResult(text=GOOD_DRAFT, model=MODEL_OPUS, stop_reason="end_turn", usage=Usage(input_tokens=1000, output_tokens=2000), cost_usd=0.0)]
    )
    step = DraftStep(brain=git_brain, content=content_store, max_tokens=4096)
    ctx = await _ctx(store, piece, provider)

    result = await step.run(ctx)

    assert result.usage.input_tokens == 1000
    assert result.notes and "committed" in result.notes[0]

    updated = await store.pieces.get(piece.id)
    assert updated.latest_revision
    assert updated.open_gaps == 2  # 2 open GAP tags, 1 GAP CLOSED excluded
    assert content_store.read_draft("token-vs-storage") == GOOD_DRAFT
    assert content_store.revision_history("token-vs-storage")

    # GLM5 tier requested via the seam (model_for_step) as the live default; never hardcoded in the step.
    call = provider.calls[0]
    assert call["model"] == MODEL_GLM5

    system_texts = call["system"]
    # the FULL verbatim transcript is present, not summarized (D16b) — with any legacy
    # [RESEARCH-DERIVED] answer marker stripped, so the annotation never reaches the model.
    transcript_text = strip_legacy_research_markers(
        content_store.read_transcript("token-vs-storage")
    )
    assert any(transcript_text in t for t in system_texts)
    # the engine prompt (verbatim) carries the GAP-in-editorial-block discipline straight from
    # engine/2-draft.md — the draft step never re-states these rules.
    engine_text = git_brain.read_engine("2-draft")
    assert any(engine_text in t for t in system_texts)
    # a partner fact file the piece names is hydrated.
    assert any(git_brain.read_partner("aws") in t for t in system_texts)
    # voice pack in override order — content-lessons LAST so they override the guide.
    voice = git_brain.read_voice("demo-mira")
    guide_idx = system_texts.index(voice.voice_guide)
    style_idx = system_texts.index(voice.style_guide)
    lessons_idx = system_texts.index(voice.content_lessons)
    assert guide_idx < style_idx < lessons_idx
    # single-call step: no cache breakpoint anywhere (§6e — below the Opus cache floor anyway).
    assert all("cache_control" not in b for b in call["system"])


# --- purpose block (cmw-draft-ignores-originating-narrative): the piece's PURPOSE, distinct ---
# --- from its EVIDENCE (the transcript) — the originating Spike/Narrative + intent must reach --
# --- the model, not just be stored on the Piece. This is exactly what the live bug missed. ----


async def test_purpose_block_includes_spike_narrative_rationale_and_intent(store):
    narrative = await store.narratives.insert(
        Narrative(
            author="hendo@example.com",
            seed_text="Customers insulate themselves from data-centre risk across geographies and vendors.",
            intent=DistributionIntent(audience="infra decision-makers", angle="deliberate multi-vendor resilience"),
        )
    )
    spike = await store.spikes.insert(
        Spike(
            headline="How infra teams insulate themselves from data-centre risk",
            creator="hendo@example.com",
            origin=SpikeOrigin(kind=SpikeOriginKind.narrative, ref=narrative.id),
            rank_rationale="Converges three customer conversations about multi-vendor resilience.",
            convergence_note="Strong recurring theme this quarter.",
        )
    )
    piece = Piece(
        slug="x",
        voice="demo-mira",
        stage=PieceStage.drafting,
        origin_spike_id=spike.id,
        intent=DistributionIntent(audience="infra decision-makers", angle="deliberate multi-vendor resilience"),
    )

    block = await DraftStep._purpose_block(store, piece)

    assert block is not None
    assert "infra decision-makers" in block
    assert "deliberate multi-vendor resilience" in block
    assert "How infra teams insulate themselves from data-centre risk" in block
    assert "Customers insulate themselves from data-centre risk across geographies and vendors" in block
    assert "Converges three customer conversations about multi-vendor resilience" in block
    assert "Strong recurring theme this quarter" in block
    # explicit purpose-vs-evidence framing, since engine/2-draft.md (out of this repo) never
    # states this relationship — the block must carry its own instruction.
    assert "evidentiary" in block.lower()
    assert "not itself the purpose" in block


async def test_purpose_block_coherent_for_narrative_spike_with_no_rank_rationale(store):
    """cmw-narrative-first-entry-point's fast path mints a Spike straight from a Narrative with
    no Oracle ranking run — `rank_rationale`/`convergence_note`/`convergence_score` are all
    legitimately null (nothing ranked it). The block must still be coherent: the narrative's own
    seed text carries the purpose, and the "why this was picked"/convergence lines must simply be
    absent rather than rendered with an empty/None value."""
    narrative = await store.narratives.insert(
        Narrative(
            author="hendo@example.com",
            seed_text="Customers insulate themselves from data-centre risk across geographies and vendors.",
            intent=DistributionIntent(audience="infra decision-makers", angle="deliberate multi-vendor resilience"),
        )
    )
    spike = await store.spikes.insert(
        Spike(
            headline="How infra teams insulate themselves from data-centre risk",
            creator="hendo@example.com",
            origin=SpikeOrigin(kind=SpikeOriginKind.narrative, ref=narrative.id),
            # No convergence_score/rank_rationale/convergence_note — the fast path never ranks.
        )
    )
    piece = Piece(
        slug="x",
        voice="demo-mira",
        stage=PieceStage.drafting,
        origin_spike_id=spike.id,
        intent=DistributionIntent(audience="infra decision-makers", angle="deliberate multi-vendor resilience"),
    )

    block = await DraftStep._purpose_block(store, piece)

    assert block is not None
    assert "infra decision-makers" in block
    assert "deliberate multi-vendor resilience" in block
    assert "How infra teams insulate themselves from data-centre risk" in block
    assert "Customers insulate themselves from data-centre risk across geographies and vendors" in block
    # No half-built lines for the data that genuinely doesn't exist on this path.
    assert "Why this idea was picked" not in block
    assert "Convergence note" not in block
    assert "None" not in block


async def test_purpose_block_is_none_when_piece_has_no_intent_or_spike(store):
    piece = Piece(slug="x", voice="demo-mira", stage=PieceStage.drafting)

    assert await DraftStep._purpose_block(store, piece) is None


async def test_purpose_block_is_best_effort_on_an_unresolvable_spike_id(store):
    """A piece can carry an ``origin_spike_id`` that doesn't resolve (e.g. a seed placeholder
    never persisted to Mongo, mirroring ``sources.py``/``spikes.py``'s existing "picking a seed
    spike 404s until Mongo holds it" limitation) — this must degrade, never raise."""
    piece = Piece(slug="x", voice="demo-mira", stage=PieceStage.drafting, origin_spike_id="not-a-real-id")

    assert await DraftStep._purpose_block(store, piece) is None


async def test_draft_step_prompt_includes_purpose_block_before_the_transcript(
    store, git_brain, content_store
):
    """The regression this ticket asks for: the spike and the angle must actually be present in
    the assembled prompt — not just stored on the Piece — and the purpose must be read BEFORE
    the transcript it frames, never concatenated into the transcript text itself."""
    narrative = await store.narratives.insert(
        Narrative(
            author="hendo@example.com",
            seed_text="Customers insulate themselves from data-centre risk across geographies and vendors.",
            intent=DistributionIntent(audience="infra decision-makers", angle="deliberate multi-vendor resilience"),
        )
    )
    spike = await store.spikes.insert(
        Spike(
            headline="How infra teams insulate themselves from data-centre risk",
            creator="hendo@example.com",
            origin=SpikeOrigin(kind=SpikeOriginKind.narrative, ref=narrative.id),
            rank_rationale="Converges three customer conversations about multi-vendor resilience.",
        )
    )
    piece = await _piece(
        store,
        PieceStage.drafting,
        slug="token-vs-storage",
        voice="demo-mira",
        origin_spike_id=spike.id,
        intent=DistributionIntent(audience="infra decision-makers", angle="deliberate multi-vendor resilience"),
    )
    provider = RecordingProvider(
        results=[LLMResult(text=GOOD_DRAFT, model=MODEL_OPUS, stop_reason="end_turn", usage=Usage(), cost_usd=0.0)]
    )
    step = DraftStep(brain=git_brain, content=content_store, max_example_pieces=0)
    ctx = await _ctx(store, piece, provider)

    await step.run(ctx)

    system_texts = provider.calls[0]["system"]
    purpose_idx = next(i for i, t in enumerate(system_texts) if "deliberate multi-vendor resilience" in t)
    transcript_text = strip_legacy_research_markers(
        content_store.read_transcript("token-vs-storage")
    )
    transcript_idx = next(i for i, t in enumerate(system_texts) if transcript_text in t)

    assert "infra decision-makers" in system_texts[purpose_idx]
    assert "How infra teams insulate themselves from data-centre risk" in system_texts[purpose_idx]
    assert "Customers insulate themselves from data-centre risk" in system_texts[purpose_idx]
    # never concatenated into the transcript block itself — a separate system block, read first.
    assert purpose_idx < transcript_idx
    assert system_texts[purpose_idx] != system_texts[transcript_idx]


async def test_legacy_research_marker_in_stored_transcript_never_reaches_the_prompt(
    store, git_brain, content_store
):
    """A ``[RESEARCH-DERIVED]`` marker left in stored data by the pre-fix transcript format is
    stripped at the assembler boundary — it must never appear in the draft prompt. Proven against
    a controlled transcript with no incidental prose mention of the marker, so the ``not in``
    assertion is a real proof, not an artifact of the fixture's preamble explaining it."""
    slug = "p-legacy-marker"
    content_store.commit_transcript(
        slug,
        "## Ferriss\n\n"
        "**Q — What's the real bill?**\n"
        f"<!-- turn:{'0' * 24} persona:ferriss research:true -->\n"
        "[RESEARCH-DERIVED] Anchor: ~$230/month.\n\n"
        "**Q — A live example?**\n"
        f"<!-- turn:{'1' * 24} persona:ferriss research:false -->\n"
        "From the author's own experience: yes.\n\n",
        message="test: seeded legacy-marker transcript",
    )
    piece = await _piece(store, PieceStage.drafting, slug=slug, voice="demo-mira")
    provider = RecordingProvider(
        results=[LLMResult(text=GOOD_DRAFT, model=MODEL_OPUS, stop_reason="end_turn", usage=Usage(), cost_usd=0.0)]
    )
    step = DraftStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, piece, provider)

    await step.run(ctx)

    system_texts = provider.calls[0]["system"]
    assert "[RESEARCH-DERIVED]" not in "".join(system_texts)
    # the answer content survives the strip — never dropped along with the marker.
    assert any("Anchor: ~$230/month." in t for t in system_texts)
    assert any("From the author's own experience: yes." in t for t in system_texts)


async def test_draft_step_still_works_with_no_spike_or_intent(store, git_brain, content_store):
    """Backward-compat: a piece with no linked Spike and no intent (most existing tests, and any
    piece created outside the pick-spike flow) contributes no purpose block rather than failing
    or emitting a confusing empty section."""
    piece = await _piece(store, PieceStage.drafting, slug="token-vs-storage", voice="demo-mira")
    provider = RecordingProvider(
        results=[LLMResult(text=GOOD_DRAFT, model=MODEL_OPUS, stop_reason="end_turn", usage=Usage(), cost_usd=0.0)]
    )
    step = DraftStep(brain=git_brain, content=content_store, max_example_pieces=0)
    ctx = await _ctx(store, piece, provider)

    await step.run(ctx)  # does not raise

    system_texts = provider.calls[0]["system"]
    assert not any("This piece's purpose" in t for t in system_texts)


# --- inline-GAP / refusal / missing-seam failure paths -------------------------------------


async def test_draft_step_rejects_inline_gap_marker_and_does_not_commit(
    store, git_brain, content_store
):
    piece = await _piece(store, PieceStage.drafting, slug="aws-gsi-faq", voice="demo-dana")
    before = content_store.read_draft("aws-gsi-faq")
    provider = RecordingProvider(
        results=[LLMResult(text=BAD_DRAFT_INLINE_GAP, model=MODEL_OPUS, stop_reason="end_turn", usage=Usage(), cost_usd=0.0)]
    )
    step = DraftStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, piece, provider)

    with pytest.raises(PermanentStepError):
        await step.run(ctx)

    updated = await store.pieces.get(piece.id)
    assert updated.latest_revision is None
    assert updated.open_gaps == 0
    assert content_store.read_draft("aws-gsi-faq") == before  # untouched — no half-written revision


def test_editorial_regex_accepts_any_tag_not_just_section():
    """The <section>-only match was an overfit to the two existing example drafts — nothing
    requires that specific element, only the "editorial" class (engine/feedback-intake.md's
    external-share strip keys off the class too)."""
    body, editorial = _split_editorial(REALISTIC_DRAFT_NON_SECTION_TAG)
    assert editorial.startswith('<div class="editorial"')
    assert "[GAP]" not in body


async def test_draft_step_accepts_a_realistic_non_section_editorial_tag(
    store, git_brain, content_store
):
    piece = await _piece(store, PieceStage.drafting, slug="token-vs-storage", voice="demo-mira")
    provider = RecordingProvider(
        results=[
            LLMResult(
                text=REALISTIC_DRAFT_NON_SECTION_TAG,
                model=MODEL_OPUS,
                stop_reason="end_turn",
                usage=Usage(),
                cost_usd=0.0,
            )
        ]
    )
    step = DraftStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, piece, provider)

    await step.run(ctx)  # does not raise

    updated = await store.pieces.get(piece.id)
    assert updated.latest_revision


async def test_draft_step_still_rejects_a_differently_named_gap_block(
    store, git_brain, content_store
):
    """Documents the residual gap a webapp-only fix cannot close: a model that invents its own
    (still well-formed, still clearly non-published) block name instead of "editorial" — e.g.
    matching engine/2-draft.md's own "[GAP: ...]" vocabulary rather than a class name that
    document never states — is correctly rejected today. Closing this needs engine/2-draft.md to
    state the exact required class (see this ticket's PR description); this test is a live
    tripwire that will start failing, on purpose, once that brain change ships and a follow-up
    widens the regex to match it.
    """
    piece = await _piece(store, PieceStage.drafting, slug="aws-gsi-faq", voice="demo-dana")
    before = content_store.read_draft("aws-gsi-faq")
    provider = RecordingProvider(
        results=[
            LLMResult(
                text=REALISTIC_DRAFT_DIFFERENT_BLOCK_NAME,
                model=MODEL_OPUS,
                stop_reason="end_turn",
                usage=Usage(),
                cost_usd=0.0,
            )
        ]
    )
    step = DraftStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, piece, provider)

    with pytest.raises(PermanentStepError):
        await step.run(ctx)

    assert content_store.read_draft("aws-gsi-faq") == before  # untouched — no half-written revision


def test_build_t2_states_the_response_must_be_raw_html_only():
    """A real Opus call (live-reproduced 2026-08-08) replied with a markdown document containing
    THREE separate fenced code blocks (piece.md, draft.html, sources.md) plus narration, instead
    of the single self-contained HTML document ``DraftStep`` treats ``result.text`` as being —
    because nothing told it its entire response IS draft.html verbatim. This is the primary
    defect the T2 tail below fixes; guard it against regressing back to silence."""
    piece = Piece(slug="x", voice="demo-mira", stage=PieceStage.drafting)
    tail = DraftStep._build_t2(piece, [])
    assert "single, self-contained HTML document" in tail
    assert "markdown code fence" in tail


async def test_draft_step_raises_refusal_error_on_model_refusal(store, git_brain, content_store):
    piece = await _piece(store, PieceStage.drafting)
    provider = RecordingProvider(
        results=[LLMResult(text="", model=MODEL_OPUS, stop_reason="refusal", usage=Usage(), cost_usd=0.0)]
    )
    step = DraftStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, piece, provider)

    with pytest.raises(RefusalError):
        await step.run(ctx)


async def test_draft_step_empty_response_is_a_permanent_error(store, git_brain, content_store):
    piece = await _piece(store, PieceStage.drafting)
    provider = RecordingProvider(
        results=[LLMResult(text="   ", model=MODEL_OPUS, stop_reason="end_turn", usage=Usage(), cost_usd=0.0)]
    )
    step = DraftStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, piece, provider)

    with pytest.raises(PermanentStepError):
        await step.run(ctx)


async def test_draft_step_requires_a_piece(store, git_brain, content_store):
    step = DraftStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, None, RecordingProvider())

    with pytest.raises(PermanentStepError):
        await step.run(ctx)


async def test_draft_step_requires_a_provider(store, git_brain, content_store):
    piece = await _piece(store, PieceStage.drafting)
    step = DraftStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, piece, None)

    with pytest.raises(PermanentStepError):
        await step.run(ctx)


# --- example-piece enrichment (§6d③): same-voice, already-drafted, best-effort ------------


async def test_draft_step_includes_same_voice_example_pieces_and_skips_missing(
    store, git_brain, content_store
):
    piece = await _piece(store, PieceStage.drafting, slug="token-vs-storage", voice="demo-mira")
    await _piece(store, PieceStage.finalized, slug="aws-gsi-faq", voice="demo-mira")  # exists on disk
    await _piece(store, PieceStage.finalized, slug="ghost-piece", voice="demo-mira")  # no folder
    await _piece(store, PieceStage.finalized, slug="aws-gsi-faq", voice="demo-dana")  # wrong voice

    provider = RecordingProvider(
        results=[LLMResult(text=GOOD_DRAFT, model=MODEL_OPUS, stop_reason="end_turn", usage=Usage(), cost_usd=0.0)]
    )
    step = DraftStep(brain=git_brain, content=content_store, max_example_pieces=2)
    ctx = await _ctx(store, piece, provider)

    await step.run(ctx)

    tail = provider.calls[0]["messages"][0]["content"]
    assert "aws-gsi-faq" in tail  # same-voice, on-disk example included
    assert "ghost-piece" not in tail  # missing draft.html — skipped, not a crash


async def test_draft_step_max_example_pieces_zero_disables_enrichment(
    store, git_brain, content_store
):
    piece = await _piece(store, PieceStage.drafting, slug="token-vs-storage", voice="demo-mira")
    await _piece(store, PieceStage.finalized, slug="aws-gsi-faq", voice="demo-mira")

    provider = RecordingProvider(
        results=[LLMResult(text=GOOD_DRAFT, model=MODEL_OPUS, stop_reason="end_turn", usage=Usage(), cost_usd=0.0)]
    )
    step = DraftStep(brain=git_brain, content=content_store, max_example_pieces=0)
    ctx = await _ctx(store, piece, provider)

    await step.run(ctx)

    tail = provider.calls[0]["messages"][0]["content"]
    assert "Example of an on-brand finished piece" not in tail


# --- plugged into the real state-machine seam (dispatch -> run -> commit -> advance) -------


async def test_draft_step_plugs_into_state_machine_and_advances_to_council(
    store, git_brain, content_store
):
    provider = RecordingProvider(
        results=[LLMResult(text=GOOD_DRAFT, model=MODEL_OPUS, stop_reason="end_turn", usage=Usage(input_tokens=10, output_tokens=10), cost_usd=0.0)]
    )
    registry = StepRegistry()
    registry.register(DraftStep(brain=git_brain, content=content_store))
    registry.register(StubStep(JobType.council))  # council is a separate ticket; stub stands in
    runner = JobRunner(store, registry, provider=provider, sleep=_noop_sleep)
    machine = PieceMachine(store, runner)
    piece = await _piece(store, PieceStage.interviewing, slug="token-vs-storage", voice="demo-mira")

    updated = await machine.enough_input(piece.id, actor="demo-mira@x")

    assert updated.stage == PieceStage.review
    assert updated.latest_revision
    assert updated.open_gaps == 2


async def test_draft_step_missing_transcript_raises_legible_precondition_error(
    store, git_brain, content_store
):
    """Reproduces the live defect (cmw-unguarded-transcript-reads): Hendo pressed "enough input"
    on a piece with no interview transcript and got a raw filesystem error. PR #82 fixed the
    identical unguarded read in incorporate's rewrite and flagged this exact call site as "not
    reachable in practice" — wrong, since a real "enough input" press reaches it directly. Must
    fail with a legible `PermanentStepError` naming the piece/file, before the model is ever
    called (`draft is built directly from the transcript, so its absence is more fundamental
    here than for a later editing step)."""
    piece = await _piece(
        store, PieceStage.drafting, slug="seeded-no-transcript-draft", voice="demo-mira"
    )
    provider = RecordingProvider([])
    step = DraftStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, piece, provider)

    with pytest.raises(PermanentStepError) as exc_info:
        await step.run(ctx)

    message = str(exc_info.value)
    assert "Errno" not in message and "FileNotFoundError" not in message
    assert "transcript" in message.lower()
    assert "seeded-no-transcript-draft" in message
    assert provider.calls == []


async def test_draft_step_missing_transcript_flags_piece_back_to_interviewing(
    store, git_brain, content_store
):
    """End-to-end reproduction through the real `PieceMachine`/`JobRunner` (mirrors PR #82's
    incorporate end-to-end test): a piece that reaches `drafting` with no transcript must flag
    back to `interviewing` — draft's own "batch fail" edge — not wedge in `drafting`, with a
    legible message and `retryable=False` (retrying unchanged fails identically every time).
    Unlike incorporate (which flags back to `review` and needs a manual `route_to_interview`
    call), draft's failure edge already lands the piece exactly where a human needs to fix it:
    pressing "enough input" again after a real interview is the entire recovery path."""
    registry = StepRegistry()
    registry.register(DraftStep(brain=git_brain, content=content_store))
    provider = RecordingProvider([])
    runner = JobRunner(store, registry, provider=provider, sleep=_noop_sleep)
    machine = PieceMachine(store, runner)
    piece = await _piece(
        store, PieceStage.interviewing, slug="seeded-no-transcript-draft-e2e", voice="demo-mira"
    )

    updated = await machine.enough_input(piece.id, actor="demo-mira@x")

    assert updated.stage == PieceStage.interviewing  # flagged back, not wedged in drafting
    failures = await machine.open_failures(updated.id)
    assert len(failures) == 1
    error = failures[0].error
    assert error is not None
    assert error.retryable is False  # correct: nothing changes between retries without a human
    assert "Errno" not in error.message and "FileNotFoundError" not in error.message
    assert "transcript" in error.message.lower()
    assert "seeded-no-transcript-draft-e2e" in error.message


async def test_draft_step_failure_flags_piece_without_rolling_back_content(
    store, git_brain, content_store
):
    provider = RecordingProvider(
        results=[LLMResult(text="", model=MODEL_OPUS, stop_reason="refusal", usage=Usage(), cost_usd=0.0)]
    )
    registry = StepRegistry()
    registry.register(DraftStep(brain=git_brain, content=content_store))
    runner = JobRunner(store, registry, provider=provider, sleep=_noop_sleep)
    machine = PieceMachine(store, runner)
    piece = await _piece(
        store,
        PieceStage.interviewing,
        slug="token-vs-storage",
        voice="demo-mira",
        latest_revision="prior-sha",
    )

    updated = await machine.enough_input(piece.id, actor="demo-mira@x")

    assert updated.stage == PieceStage.interviewing  # flagged back, not stuck in drafting
    assert updated.latest_revision == "prior-sha"  # committed content untouched (D4/D16b)
    failures = await machine.open_failures(updated.id)
    assert len(failures) == 1
    assert failures[0].error is not None and failures[0].error.code == "refusal"
