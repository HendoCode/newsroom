"""Council step tests (engine/3-revision-loop.md; cmw-context-assembly report §7).

Covers, per the acceptance criteria:
- editor selection: mandatory editors always, one partner-brand-steward per external partner
  (Hendo excluded — the home company is never an external partner), the round's
  explicit ``Job.council_fit_editors`` (unknown names dropped, not rejected);
- context assembly: the shared cached prefix (framing + voice pack + partner files + the exact
  revision scored + the full transcript), one cache breakpoint, reused by every editor;
- the aggregate honors hard caps (slop-allergist / technical-reviewer only) and ignores a
  hard-cap claim from any other editor;
- machine-safe editorial fixes + new information gaps land in a new Revision; a clean round (no
  fixes, no gaps) still mirrors a sources.md summary without an extra LLM call;
- structured per-editor scores land in Mongo (Council/EditorScore) and a human-readable summary
  lands in ``sources.md``;
- a malformed editor response / a refusal on the apply call fails the step without committing
  anything (flag-not-rollback via the real PieceMachine/JobRunner);
- the real state machine advances council → review on success.

Zero external deps: the LLM path runs on a small scripted fake provider (no ``anthropic`` package,
no key, no network) that resolves each call to a canned response by matching a marker string
against the message content — lets every editor (and the apply-fixes call) get its own answer.
"""

from __future__ import annotations

import json
from typing import Self

import pytest

from app.interview.transcript import strip_legacy_research_markers
from app.llm import MODEL_OPUS, LLMProvider, LLMResult, LLMStream, RunBudget, Usage
from app.models import (
    Council,
    DistributionIntent,
    EditorScore,
    Job,
    JobStatus,
    JobType,
    Narrative,
    Piece,
    PieceRole,
    PieceStage,
    Spike,
    SpikeOrigin,
    QUALITY_BAR,
    SpikeOriginKind,
)
from app.orchestration import JobRunner, PieceMachine, StepRegistry
from app.orchestration.council_step import (
    HARD_CAP_CEILING,
    CouncilParseError,
    CouncilStep,
    _append_section,
    _dedup,
    _external_partners,
    _parse_editor_response,
    _select_editors,
    compute_aggregate,
)
from app.orchestration.retry import PermanentStepError, RefusalError
from app.orchestration.steps import BatchStep, StepContext, StepResult

# --- a scripted provider: resolves each call by a marker string in the message content -----


def _content(messages: list[dict[str, object]]) -> str:
    text = messages[0]["content"] if messages else ""
    return text if isinstance(text, str) else ""


class ScriptedStream(LLMStream):
    def __init__(self, provider: ScriptedProvider, model: str, messages, budget) -> None:
        self.provider = provider
        self.model = model
        self.messages = messages
        self.budget = budget

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def wait_first_token(self) -> None:
        return None

    async def final(self) -> LLMResult:
        result = self.provider._resolve(self.messages)
        if self.budget is not None:
            self.budget.charge(self.model, result.usage)
        self.provider.calls.append(self.messages)
        return result


class ScriptedProvider(LLMProvider):
    """Routes a call to a canned :class:`LLMResult` by matching a marker substring against the
    first message's content. Raises ``AssertionError`` for an unscripted call (a test bug), not a
    silent default, so a missing marker fails loudly."""

    def __init__(self, by_marker: dict[str, LLMResult]) -> None:
        self.by_marker = dict(by_marker)
        self.calls: list[list[dict[str, object]]] = []
        self.max_tokens: list[int] = []

    def _resolve(self, messages) -> LLMResult:
        text = _content(messages)
        for marker, result in self.by_marker.items():
            if marker in text:
                return result
        raise AssertionError(f"no scripted response matches call: {text[:300]!r}")

    def stream(
        self, *, step, model, system, messages, max_tokens, effort=None, cache=False, budget=None
    ):
        if budget is not None:
            budget.check()
        self.max_tokens.append(max_tokens)
        return ScriptedStream(self, model, messages, budget)

    async def complete(self, *, step, model, system, messages, max_tokens, effort=None, cache=False, budget=None):
        if budget is not None:
            budget.check()
        self.max_tokens.append(max_tokens)
        result = self._resolve(messages)
        if budget is not None:
            budget.charge(model, result.usage)
        self.calls.append(messages)
        return result

    async def count_tokens(self, *, model, system, messages):
        return 0


def _score(
    score: float,
    *,
    hard_cap: bool = False,
    fixes: list[str] | None = None,
    gaps: list[str] | None = None,
    usage: Usage | None = None,
) -> LLMResult:
    payload = {
        "score": score,
        "hard_cap_applied": hard_cap,
        "editorial_fixes": fixes or [],
        "information_gaps": gaps or [],
    }
    return LLMResult(
        text=json.dumps(payload),
        model=MODEL_OPUS,
        stop_reason="end_turn",
        usage=usage or Usage(input_tokens=100, output_tokens=50),
        cost_usd=0.01,
    )


APPLY_MARKER = "Apply the following council-approved changes"


def _apply(html: str, *, stop_reason: str = "end_turn") -> LLMResult:
    return LLMResult(
        text=html,
        model=MODEL_OPUS,
        stop_reason=stop_reason,
        usage=Usage(input_tokens=200, output_tokens=300),
        cost_usd=0.02,
    )


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


async def _ctx(
    store, piece: Piece, provider: LLMProvider | None, *, council_fit_editors=None, budget=None
) -> StepContext:
    job = await store.jobs.insert(
        Job(
            type=JobType.council,
            piece_id=piece.id if piece else None,
            status=JobStatus.running,
            council_fit_editors=council_fit_editors,
        )
    )
    return StepContext(
        job=job, store=store, budget=budget or RunBudget(), piece=piece, provider=provider
    )


def _seed_revision(content_store, slug: str = "token-vs-storage") -> str:
    """The real fixture pieces already have a committed ``draft.html`` in the seed-brain commit —
    reuse that sha as ``latest_revision`` rather than authoring a redundant new commit."""
    return content_store.revision_history(slug)[0].sha


# A synthetic, known-clean draft — the fixture brain's draft.html carries an
# explanatory HTML *comment* mentioning "[GAP]/[NOTE]" ahead of its editorial block (documentation
# text, not an inline marker), which would otherwise trip `_assert_no_inline_gaps` on any test that
# round-trips that real content back through the apply-fixes path. Tests that exercise the apply
# call use this instead; tests that only read the real fixture's revision/transcript verbatim (to
# assert on context assembly) are unaffected and keep using the real "token-vs-storage" piece.
GOOD_COUNCIL_DRAFT = (
    "<!DOCTYPE html><html><head><title>t</title></head><body>"
    "<article><h1>Title</h1><p>Some prose about the topic.</p></article>"
    "<hr>"
    '<section class="editorial" aria-label="Editorial annotations, not for publication">'
    "<h3>Editorial annotations</h3>"
    '<p><span class="tag">[GAP]</span> need X</p>'
    "</section>"
    "</body></html>"
)


def _seed_synthetic_piece(content_store, slug: str, html: str = GOOD_COUNCIL_DRAFT) -> str:
    """Commit a fresh synthetic transcript + draft for ``slug`` and return the draft's sha."""
    content_store.commit_transcript(
        slug, "# Transcript\n\nQ: what happened?\nA: it happened.\n", message="seed transcript"
    )
    return content_store.commit_revision(slug, html, message="seed draft")


# --- pure helpers: aggregate / hard caps ----------------------------------------------------


def test_compute_aggregate_is_the_plain_mean_without_a_hard_cap():
    scores = [
        EditorScore(editor="slop-allergist", score=9.0),
        EditorScore(editor="voice-guardian", score=8.0),
    ]
    assert compute_aggregate(scores) == pytest.approx(8.5)


def test_compute_aggregate_caps_at_six_when_slop_allergist_hard_caps():
    scores = [
        EditorScore(editor="slop-allergist", score=9.0, hard_cap_applied=True),
        EditorScore(editor="voice-guardian", score=9.5),
    ]
    assert compute_aggregate(scores) == HARD_CAP_CEILING


def test_compute_aggregate_ignores_hard_cap_claim_from_non_eligible_editor():
    scores = [
        EditorScore(editor="slop-allergist", score=9.0),
        EditorScore(editor="voice-guardian", score=9.0, hard_cap_applied=True),
    ]
    # voice-guardian has no hard-cap authority (only slop-allergist/technical-reviewer do) — the
    # claim is recorded on its own EditorScore but must not depress the aggregate.
    assert compute_aggregate(scores) == pytest.approx(9.0)


def test_compute_aggregate_empty_is_zero():
    assert compute_aggregate([]) == 0.0


# --- pure helpers: editor-response parsing --------------------------------------------------


def test_parse_editor_response_happy_path():
    text = '{"score": 8.5, "hard_cap_applied": false, "editorial_fixes": ["fix a"], "information_gaps": []}'
    result = _parse_editor_response("voice-guardian", text)
    assert result.editor == "voice-guardian"
    assert result.score == 8.5
    assert result.editorial_fixes == ["fix a"]
    assert result.information_gaps == []
    assert result.hard_cap_applied is False


def test_parse_editor_response_tolerates_surrounding_prose_and_clamps_score():
    text = 'Sure thing!\n```json\n{"score": 15, "hard_cap_applied": true}\n```\nHope that helps.'
    result = _parse_editor_response("slop-allergist", text)
    assert result.score == 10.0  # clamped into [0, 10]
    assert result.hard_cap_applied is True


def test_parse_editor_response_raises_on_malformed_json():
    with pytest.raises(CouncilParseError):
        _parse_editor_response("slop-allergist", "not json at all")


def test_parse_editor_response_raises_on_non_numeric_score():
    with pytest.raises(CouncilParseError):
        _parse_editor_response("slop-allergist", '{"score": "high"}')


# --- pure helpers: editor selection ---------------------------------------------------------


def test_select_editors_mandatory_only_by_default(git_brain):
    piece = Piece(slug="p", voice="demo-mira", stage=PieceStage.council)
    job = Job(type=JobType.council)
    assert _select_editors(piece, job, git_brain) == [
        "slop-allergist",
        "voice-guardian",
    ]


def test_select_editors_adds_partner_steward_for_named_partner(git_brain):
    piece = Piece(slug="p", voice="demo-mira", stage=PieceStage.council, partners=["AWS"])
    job = Job(type=JobType.council)
    selected = _select_editors(piece, job, git_brain)
    assert "partner-brand-steward/aws" in selected


def test_select_editors_adds_known_fit_editors_and_drops_unknown(git_brain):
    piece = Piece(slug="p", voice="demo-mira", stage=PieceStage.council)
    job = Job(
        type=JobType.council,
        council_fit_editors=["technical-reviewer", "not-a-real-editor", "SLOP-ALLERGIST"],
    )
    selected = _select_editors(piece, job, git_brain)
    assert selected.count("slop-allergist") == 1  # already mandatory — not duplicated
    assert "technical-reviewer" in selected
    assert "not-a-real-editor" not in selected


def test_select_editors_derivative_piece_gets_destination_specific_council(git_brain):
    """Derivative quality bar: a derivative piece's own council adds the destination-specific
    judgment + the universal facts-gate editor on top of the mandatory editors."""
    piece = Piece(
        slug="anchor-linkedin-post",
        voice="demo-mira",
        stage=PieceStage.council,
        role=PieceRole.derivative,
        target="linkedin-post",
    )
    job = Job(type=JobType.council)
    selected = _select_editors(piece, job, git_brain)
    assert selected[:2] == ["slop-allergist", "voice-guardian"]
    assert "technical-reviewer" in selected  # universal facts gate
    assert "puri" in selected and "cold-reader" in selected and "closer" in selected
    assert len(selected) == len(set(selected))


def test_select_editors_derivative_whitepaper_gets_different_judgment(git_brain):
    linkedin = _select_editors(
        Piece(slug="a", voice="s", stage=PieceStage.council, role=PieceRole.derivative, target="linkedin-post"),
        Job(type=JobType.council),
        git_brain,
    )
    whitepaper = _select_editors(
        Piece(slug="b", voice="s", stage=PieceStage.council, role=PieceRole.derivative, target="whitepaper"),
        Job(type=JobType.council),
        git_brain,
    )
    assert linkedin != whitepaper
    assert "housel" in whitepaper and "housel" not in linkedin


def test_select_editors_derivative_unknown_destination_still_gets_generic_judgment(git_brain):
    piece = Piece(
        slug="p",
        voice="demo-mira",
        stage=PieceStage.council,
        role=PieceRole.derivative,
        target="carrier-pigeon",
    )
    selected = _select_editors(piece, Job(type=JobType.council), git_brain)
    assert "cold-reader" in selected and "structure-editor" in selected


def test_select_editors_anchor_role_ignores_derivative_lineup(git_brain):
    piece = Piece(
        slug="p",
        voice="demo-mira",
        stage=PieceStage.council,
        role=PieceRole.anchor,
        target="linkedin-post",
    )
    assert _select_editors(piece, Job(type=JobType.council), git_brain) == [
        "slop-allergist",
        "voice-guardian",
    ]


def test_external_partners_normalizes_dedupes():
    piece = Piece(slug="p", voice="demo-mira", stage=PieceStage.council, partners=["AWS", "aws", "Azure"])
    assert _external_partners(piece) == ["aws", "azure"]


# --- pure helpers: dedup / sources.md section append ----------------------------------------


def test_dedup_preserves_first_occurrence_order_and_strips_blanks():
    assert _dedup([" a ", "b", "a", "", "  ", "c"]) == ["a", "b", "c"]


def test_append_section_on_empty_existing_returns_section_only():
    assert _append_section("", "## New") == "## New"


def test_append_section_separates_with_one_blank_line():
    result = _append_section("existing content\n", "## New section")
    assert result == "existing content\n\n## New section"


# --- integration: happy path (mandatory editors only, fixes + gaps applied) -----------------


@pytest.mark.parametrize(
    ("step_kwargs", "expected_max_tokens"),
    [({}, 2048), ({"editor_max_tokens": 777}, 777)],
)
async def test_council_step_passes_editor_token_limit_to_every_fanout_call(
    store, git_brain, content_store, step_kwargs, expected_max_tokens
):
    slug = f"council-token-limit-{expected_max_tokens}"
    sha = _seed_synthetic_piece(content_store, slug)
    piece = await _piece(store, PieceStage.council, slug=slug, latest_revision=sha)
    provider = ScriptedProvider(
        {
            "**slop-allergist**": _score(9.5),
            "**voice-guardian**": _score(9.5),
        }
    )

    await CouncilStep(brain=git_brain, content=content_store, **step_kwargs).run(
        await _ctx(store, piece, provider)
    )

    assert provider.max_tokens == [expected_max_tokens] * 2


async def test_council_step_happy_path_scores_and_stops_at_quality_bar(
    store, git_brain, content_store
):
    """When the first scoring iteration already clears the quality bar, no fixes are applied
    and the loop stops immediately with stop_reason=quality_bar_met."""
    slug = "council-happy-path"
    sha = _seed_synthetic_piece(content_store, slug)
    piece = await _piece(store, PieceStage.council, slug=slug, voice="demo-mira", latest_revision=sha)

    provider = ScriptedProvider(
        {
            "**slop-allergist**": _score(9.0, fixes=["tighten paragraph 2"]),
            "**voice-guardian**": _score(9.0),
        }
    )
    step = CouncilStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, piece, provider)

    result = await step.run(ctx)

    assert "council round 1 scored" in result.notes[0]
    assert "stopped: quality_bar_met" in result.notes[0]
    councils = await store.councils.by_piece(piece.id)
    assert len(councils) == 1
    council = councils[0]
    assert council.round_number == 1
    assert council.iteration == 1
    assert council.revision == sha  # the INPUT revision that was scored
    assert council.aggregate == pytest.approx(9.0)
    assert council.stop_reason == "quality_bar_met"
    mandatory_present = {s.editor for s in council.editor_scores}
    assert {"slop-allergist", "voice-guardian"} <= mandatory_present

    updated = await store.pieces.get(piece.id)
    assert updated.latest_council_id == council.id
    # No fixes applied, so the semantic draft is unchanged; sources.md still commits a summary,
    # so latest_revision may advance even though draft.html is identical.
    assert content_store.read_draft(slug) == GOOD_COUNCIL_DRAFT

    sources = content_store.read_sources(slug)
    assert "## Council record — round 1" in sources
    assert "slop-allergist 9" in sources

    # 2 editor calls only; no apply call because the loop stopped at the quality bar.
    assert len(provider.calls) == 2


async def test_council_step_no_fixes_or_gaps_skips_apply_call_but_still_updates_sources(
    store, git_brain, content_store
):
    sha = _seed_revision(content_store)
    piece = await _piece(
        store, PieceStage.council, slug="token-vs-storage", voice="demo-mira", latest_revision=sha
    )
    provider = ScriptedProvider(
        {
            "**slop-allergist**": _score(9.5),
            "**voice-guardian**": _score(9.5),
        }
    )
    step = CouncilStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, piece, provider)

    await step.run(ctx)

    assert len(provider.calls) == 2  # 2 editor calls; no apply call (no fixes, no gaps)
    updated = await store.pieces.get(piece.id)
    assert updated.latest_revision != sha  # sources.md changed -> a new revision commit still lands
    assert content_store.read_draft("token-vs-storage") == content_store.read_revision(
        "token-vs-storage", sha
    )  # draft.html itself is untouched


async def test_council_step_aggregate_below_bar_is_recorded_honestly(
    store, git_brain, content_store
):
    sha = _seed_revision(content_store)
    piece = await _piece(
        store, PieceStage.council, slug="token-vs-storage", voice="demo-mira", latest_revision=sha
    )
    provider = ScriptedProvider(
        {
            "**slop-allergist**": _score(7.0, hard_cap=True),
            "**voice-guardian**": _score(9.0),
        }
    )
    step = CouncilStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, piece, provider)

    await step.run(ctx)

    councils = await store.councils.by_piece(piece.id)
    assert councils[0].aggregate == HARD_CAP_CEILING
    assert councils[0].meets_bar() is False


async def test_council_step_prior_round_feedback_is_passed_to_the_same_editor(
    store, git_brain, content_store
):
    sha = _seed_revision(content_store)
    piece = await _piece(
        store, PieceStage.council, slug="token-vs-storage", voice="demo-mira", latest_revision=sha
    )
    await store.councils.insert(
        Council(
            piece_id=piece.id,
            revision=sha,
            round_number=1,
            editor_scores=[
                EditorScore(
                    editor="slop-allergist",
                    score=7.0,
                    editorial_fixes=["cut the empty adjective in para 3"],
                ),
                EditorScore(editor="voice-guardian", score=9.0),
            ],
            aggregate=8.3,
        )
    )
    provider = ScriptedProvider(
        {
            "**slop-allergist**": _score(9.5),
            "**voice-guardian**": _score(9.5),
        }
    )
    step = CouncilStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, piece, provider)

    await step.run(ctx)

    councils = await store.councils.by_piece(piece.id)
    assert len(councils) == 2
    assert councils[1].round_number == 2

    all_seen = "\n".join(_content(m) for m in provider.calls)
    assert "cut the empty adjective in para 3" in all_seen


# --- integration: shared cached prefix assembly ---------------------------------------------


async def test_council_step_shared_prefix_has_one_cache_breakpoint_and_full_transcript(
    store, git_brain, content_store
):
    sha = _seed_revision(content_store)
    piece = await _piece(
        store, PieceStage.council, slug="token-vs-storage", voice="demo-mira", latest_revision=sha
    )
    provider = ScriptedProvider(
        {
            "**slop-allergist**": _score(9.5),
            "**voice-guardian**": _score(9.5),
        }
    )

    captured_system: list[dict[str, object]] = []

    orig_stream = provider.stream

    def spying_stream(
        *, step, model, system, messages, max_tokens, effort=None, cache=False, budget=None
    ):
        captured_system.extend(system)
        return orig_stream(
            step=step, model=model, system=system, messages=messages, max_tokens=max_tokens,
            effort=effort, cache=cache, budget=budget,
        )

    provider.stream = spying_stream  # type: ignore[method-assign]
    step = CouncilStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, piece, provider)

    await step.run(ctx)

    system_texts = captured_system
    engine_text = git_brain.read_engine("3-revision-loop")
    assert any(engine_text in t for t in system_texts)
    transcript_text = strip_legacy_research_markers(
        content_store.read_transcript("token-vs-storage")
    )
    assert any(transcript_text in t for t in system_texts)
    revision_text = content_store.read_revision("token-vs-storage", sha)
    assert any(revision_text in t for t in system_texts)
    # cache flag exercised via spying_stream (neutral seam)


async def test_council_step_without_transcript_grounds_in_revision_and_sources(
    store, git_brain, content_store
):
    """cmw-lessons-loop Ship 1 regression: a brain-authored (brain_synced) piece has no
    transcript by design, and this guard used to raise a PermanentStepError that failed the
    re-council chained after every reviews-done — permanently, for every brain-authored piece.
    The council shared prefix must instead carry the shared invent-nothing grounding block
    (revision already in T1 + sources.md), the same block the incorporate rewrite grounds in."""
    sha = content_store.commit_revision(
        "brain-authored-no-transcript",
        GOOD_COUNCIL_DRAFT,
        sources_md="- [AWS blog](https://example.com/aws) — the cited figure",
        message="seed brain-authored draft, no interview ever run",
    )
    piece = await _piece(
        store,
        PieceStage.council,
        slug="brain-authored-no-transcript",
        voice="demo-mira",
        latest_revision=sha,
    )
    # The sources.md bytes as they were at seed time — the council run APPENDS its round
    # summary to sources.md, so reading after run() would not match what was embedded.
    sources_at_seed = content_store.read_sources("brain-authored-no-transcript")
    provider = ScriptedProvider(
        {
            "**slop-allergist**": _score(9.5),
            "**voice-guardian**": _score(9.5),
        }
    )

    captured_system: list[dict[str, object]] = []
    orig_stream = provider.stream

    def spying_stream(*, step, model, system, messages, max_tokens, effort=None, cache=False, budget=None):
        captured_system.extend(system)
        return orig_stream(
            step=step, model=model, system=system, messages=messages, max_tokens=max_tokens,
            effort=effort, cache=cache, budget=budget,
        )

    provider.stream = spying_stream  # type: ignore[method-assign]
    step = CouncilStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, piece, provider)

    await step.run(ctx)

    system_texts = captured_system
    with pytest.raises(OSError):
        content_store.read_transcript("brain-authored-no-transcript")
    grounding = [t for t in system_texts if isinstance(t, str) and "no interview transcript" in t.lower()]
    assert grounding, "the shared invent-nothing grounding block must be in the cached prefix"
    assert "invent nothing" in grounding[0].lower()
    assert any(sources_at_seed in t for t in system_texts)
    revision_text = content_store.read_revision("brain-authored-no-transcript", sha)
    assert any(revision_text in t for t in system_texts)


async def test_council_step_shared_prefix_includes_the_purpose_block(store, git_brain, content_store):
    """Sibling check to the draft step's fix (cmw-draft-ignores-originating-narrative): a council
    that only ever saw the transcript would score a confidently-written wrong-subject draft as
    perfectly good, since it has no way to know what the piece was supposed to be about. Reuses
    ``DraftStep._purpose_block`` verbatim (not reimplemented) — see council_step.py's module
    docstring."""
    sha = _seed_revision(content_store)
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
        )
    )
    piece = await _piece(
        store,
        PieceStage.council,
        slug="token-vs-storage",
        voice="demo-mira",
        latest_revision=sha,
        origin_spike_id=spike.id,
        intent=DistributionIntent(audience="infra decision-makers", angle="deliberate multi-vendor resilience"),
    )
    provider = ScriptedProvider(
        {
            "**slop-allergist**": _score(9.5),
            "**voice-guardian**": _score(9.5),
        }
    )
    captured_system: list[dict[str, object]] = []
    orig_stream = provider.stream

    def spying_stream(
        *, step, model, system, messages, max_tokens, effort=None, cache=False, budget=None
    ):
        captured_system.extend(system)
        return orig_stream(
            step=step, model=model, system=system, messages=messages, max_tokens=max_tokens,
            effort=effort, cache=cache, budget=budget,
        )

    provider.stream = spying_stream  # type: ignore[method-assign]
    step = CouncilStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, piece, provider)

    await step.run(ctx)

    system_texts = captured_system
    assert any("deliberate multi-vendor resilience" in t for t in system_texts)
    assert any("How infra teams insulate themselves from data-centre risk" in t for t in system_texts)


# --- failure paths: malformed response / refusal --------------------------------------------


async def test_council_step_malformed_editor_response_raises_and_commits_nothing(
    store, git_brain, content_store
):
    sha = _seed_revision(content_store)
    piece = await _piece(
        store, PieceStage.council, slug="token-vs-storage", voice="demo-mira", latest_revision=sha
    )
    before_sources = content_store.read_sources("token-vs-storage")
    bad_result = LLMResult(
        text="not json", model=MODEL_OPUS, stop_reason="end_turn", usage=Usage(), cost_usd=0.0
    )
    provider = ScriptedProvider(
        {
            "**slop-allergist**": _score(9.5),
            "**voice-guardian**": bad_result,
        }
    )
    step = CouncilStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, piece, provider)

    with pytest.raises(CouncilParseError):
        await step.run(ctx)

    assert await store.councils.by_piece(piece.id) == []
    updated = await store.pieces.get(piece.id)
    assert updated.latest_revision == sha
    assert content_store.read_sources("token-vs-storage") == before_sources


async def test_council_step_apply_refusal_raises_and_commits_nothing(store, git_brain, content_store):
    sha = _seed_revision(content_store)
    piece = await _piece(
        store, PieceStage.council, slug="token-vs-storage", voice="demo-mira", latest_revision=sha
    )
    provider = ScriptedProvider(
        {
            "**slop-allergist**": _score(8.0, fixes=["fix it"]),
            "**voice-guardian**": _score(9.0),
            APPLY_MARKER: _apply("", stop_reason="refusal"),
        }
    )
    step = CouncilStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, piece, provider)

    with pytest.raises(RefusalError):
        await step.run(ctx)

    assert await store.councils.by_piece(piece.id) == []
    updated = await store.pieces.get(piece.id)
    assert updated.latest_revision == sha


async def test_council_step_requires_a_piece(store, git_brain, content_store):
    step = CouncilStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, None, ScriptedProvider({}))

    with pytest.raises(PermanentStepError):
        await step.run(ctx)


async def test_council_step_requires_a_provider(store, git_brain, content_store):
    sha = _seed_revision(content_store)
    piece = await _piece(store, PieceStage.council, latest_revision=sha)
    step = CouncilStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, piece, None)

    with pytest.raises(PermanentStepError):
        await step.run(ctx)


async def test_council_step_requires_a_committed_revision(store, git_brain, content_store):
    piece = await _piece(store, PieceStage.council)
    step = CouncilStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, piece, ScriptedProvider({}))

    with pytest.raises(PermanentStepError):
        await step.run(ctx)


async def test_council_step_without_transcript_no_longer_raises(
    store, git_brain, content_store
):
    """cmw-lessons-loop Ship 1 regression: this used to raise a legible `PermanentStepError` for
    a piece with a committed draft revision but no transcript.md (the cmw-unguarded-transcript-
    reads fix added that raise when the state looked impossible). Since cmw-brain-pieces-
    visibility made brain-authored pieces first-class, a review-stage piece LEGITIMATELY has no
    transcript, and that raise permanently wedged reviews-done (and the re-council chained after
    it) for every brain-authored piece — all 11 minted pieces on live. The council must now
    score via the shared grounding block (detailed prefix assertions live in
    test_council_step_without_transcript_grounds_in_revision_and_sources) and complete normally."""
    slug = "seeded-no-transcript-council-unit"
    sha = content_store.commit_revision(
        slug, GOOD_COUNCIL_DRAFT, message="seed draft directly, no interview ever run"
    )
    piece = await _piece(store, PieceStage.council, slug=slug, voice="demo-mira", latest_revision=sha)
    provider = ScriptedProvider(
        {
            "**slop-allergist**": _score(9.5),
            "**voice-guardian**": _score(9.5),
        }
    )
    step = CouncilStep(brain=git_brain, content=content_store)
    ctx = await _ctx(store, piece, provider)

    result = await step.run(ctx)  # must NOT raise PermanentStepError

    assert result.notes
    assert provider.calls  # editors ran — the missing transcript no longer blocks the scoring
    councils = await store.councils.by_piece(piece.id)
    assert len(councils) == 1
    assert councils[0].aggregate >= QUALITY_BAR


# --- plugged into the real state-machine seam (dispatch -> run -> commit -> advance) --------


class _SeedDraftStep(BatchStep):
    """Test-only stand-in for the real DraftStep: points ``latest_revision`` at the fixture
    piece's already-committed seed revision so the chain reaches CouncilStep with something to
    score, without re-implementing draft-step context assembly in this test module."""

    job_type = JobType.draft

    def __init__(self, content_store, slug: str) -> None:
        self._content_store = content_store
        self._slug = slug

    async def run(self, ctx: StepContext) -> StepResult:
        sha = self._content_store.revision_history(self._slug)[0].sha
        await ctx.store.pieces.update(ctx.piece.id, {"latest_revision": sha})
        return StepResult()


class _SeedDraftNoTranscriptStep(BatchStep):
    """Test-only stand-in for DraftStep that commits a fresh draft revision but deliberately
    never calls ``commit_transcript`` — reproducing the real defect's shape: a piece whose
    ``latest_revision`` came from somewhere other than a real interview-grounded draft (the
    deployed incorporate incident's own piece was seeded directly with draft prose, no interview
    ever run). With the draft-step guard in place, a genuine draft→council chain can no longer
    produce this state — this stand-in is what lets the test reach council with it anyway."""

    job_type = JobType.draft

    def __init__(self, content_store, slug: str, html: str) -> None:
        self._content_store = content_store
        self._slug = slug
        self._html = html

    async def run(self, ctx: StepContext) -> StepResult:
        sha = self._content_store.commit_revision(
            self._slug, self._html, message="seed draft directly, no interview ever run"
        )
        await ctx.store.pieces.update(ctx.piece.id, {"latest_revision": sha})
        return StepResult()


async def test_council_step_without_transcript_completes_chain_to_review(
    store, git_brain, content_store
):
    """End-to-end (cmw-lessons-loop Ship 1) through the real PieceMachine/JobRunner: a piece that
    reaches council with a committed draft revision but NO transcript (the brain-authored
    shape — this test's own `_SeedDraftNoTranscriptStep` stand-in reproduces it) must complete the
    chain and advance to `review`, not flag back to `interviewing`. The old raise here was exactly
    what permanently wedged reviews-done for every brain-authored piece on live."""
    slug = "seeded-no-transcript-council-e2e"
    registry = StepRegistry()
    registry.register(_SeedDraftNoTranscriptStep(content_store, slug, GOOD_COUNCIL_DRAFT))
    registry.register(CouncilStep(brain=git_brain, content=content_store))
    provider = ScriptedProvider(
        {
            "**slop-allergist**": _score(9.5),
            "**voice-guardian**": _score(9.5),
        }
    )
    runner = JobRunner(store, registry, provider=provider, sleep=_noop_sleep)
    machine = PieceMachine(store, runner)
    piece = await _piece(store, PieceStage.interviewing, slug=slug, voice="demo-mira")

    updated = await machine.enough_input(piece.id, actor="demo-mira@x")

    assert updated.stage == PieceStage.review  # the chain completes — no flag back
    assert updated.latest_revision is not None
    assert updated.latest_council_id is not None
    assert await machine.open_failures(updated.id) == []
    assert provider.calls  # editors ran — the missing transcript no longer blocks the scoring


async def test_council_step_plugs_into_state_machine_and_advances_to_review(
    store, git_brain, content_store
):
    provider = ScriptedProvider(
        {
            "**slop-allergist**": _score(9.5),
            "**voice-guardian**": _score(9.5),
        }
    )
    registry = StepRegistry()
    registry.register(_SeedDraftStep(content_store, "token-vs-storage"))
    registry.register(CouncilStep(brain=git_brain, content=content_store))
    runner = JobRunner(store, registry, provider=provider, sleep=_noop_sleep)
    machine = PieceMachine(store, runner)
    piece = await _piece(store, PieceStage.interviewing, slug="token-vs-storage", voice="demo-mira")

    updated = await machine.enough_input(piece.id, actor="demo-mira@x")

    assert updated.stage == PieceStage.review
    assert updated.latest_council_id is not None
    councils = await store.councils.by_piece(piece.id)
    assert len(councils) == 1


async def test_council_step_failure_flags_piece_without_rolling_back_content(
    store, git_brain, content_store
):
    provider = ScriptedProvider(
        {
            "**slop-allergist**": _score(9.5),
            "**voice-guardian**": LLMResult(
                text="not json", model=MODEL_OPUS, stop_reason="end_turn", usage=Usage(), cost_usd=0.0
            ),
        }
    )
    registry = StepRegistry()
    registry.register(_SeedDraftStep(content_store, "token-vs-storage"))
    registry.register(CouncilStep(brain=git_brain, content=content_store))
    runner = JobRunner(store, registry, provider=provider, sleep=_noop_sleep)
    machine = PieceMachine(store, runner)
    piece = await _piece(store, PieceStage.interviewing, slug="token-vs-storage", voice="demo-mira")

    updated = await machine.enough_input(piece.id, actor="demo-mira@x")

    assert updated.stage == PieceStage.interviewing  # flagged back — no review round exists yet
    assert updated.latest_revision is not None  # the draft revision itself is untouched
    assert await store.councils.by_piece(piece.id) == []  # no half-written Council record
    failures = await machine.open_failures(updated.id)
    assert len(failures) == 1
    assert failures[0].error is not None and failures[0].error.code == "council_parse_error"


# --- quality-waiver policy overrides (cmw-authority-model-impl) -----------------------------


class _FakeWorkflowState:
    """Minimal WorkflowState stand-in for unit-testing ``CouncilStep._effective_policy``."""

    def __init__(
        self,
        project: "ContentProject | None" = None,
        waiver: "QualityWaiver | None" = None,
    ) -> None:
        self.project = project
        self.waiver = waiver

    async def load_project(self, project_id: str) -> "ContentProject | None":
        return self.project

    async def latest_quality_waiver(self, project_id: str) -> "QualityWaiver | None":
        return self.waiver


def _content_project(*, policy: "CouncilPolicy") -> "ContentProject":
    from app.content_workflow.models import (
        ActorRef,
        AuthorityAssignment,
        AuthorityKind,
        ContentProject,
        PurposeBrief,
        ResearchPolicy,
    )
    from app.models.common import utcnow

    actor = ActorRef(subject_id="a@example.com", email="a@example.com")
    return ContentProject(
        id="proj-effective-policy",
        title="Test Project",
        originating_idea_id="idea-1",
        purpose_brief=PurposeBrief(
            proposition="p",
            audience="a",
            angle="a",
            desired_outcome="o",
            why_now="n",
            constraints=[],
        ),
        authorities=[
            AuthorityAssignment(
                kind=AuthorityKind.direction,
                assignee=actor,
                assigned_by=actor,
                assigned_at=utcnow(),
            )
        ],
        default_voice_id="demo-dana",
        evidence_base_id="eb-1",
        council_policy=policy,
        research_policy=ResearchPolicy(),
    )


@pytest.mark.asyncio
async def test_effective_policy_uses_project_council_policy() -> None:
    from app.config import Settings
    from app.content_workflow.models import CouncilPolicy

    policy = CouncilPolicy(quality_bar=7.0, iteration_ceiling=5, cost_ceiling_usd=1.0)
    state = _FakeWorkflowState(project=_content_project(policy=policy))
    step = CouncilStep(workflow_state=state, settings=Settings())
    piece = Piece(
        slug="p", voice="demo-mira", stage=PieceStage.council, content_project_id="proj-effective-policy"
    )

    effective = await step._effective_policy(piece)

    assert effective.quality_bar == pytest.approx(7.0)
    assert effective.iteration_ceiling == 5
    assert effective.cost_ceiling_usd == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_effective_policy_applies_quality_waiver_overrides() -> None:
    from app.config import Settings
    from app.content_workflow.models import ActorRef, CouncilPolicy, QualityWaiver
    from app.models.common import utcnow

    policy = CouncilPolicy(quality_bar=7.0, iteration_ceiling=5, cost_ceiling_usd=1.0)
    waiver = QualityWaiver(
        content_project_id="proj-effective-policy",
        actor=ActorRef(subject_id="a@example.com", email="a@example.com"),
        reason="test override",
        quality_bar=6.0,
        iteration_ceiling=2,
        cost_ceiling_usd=0.5,
        recorded_at=utcnow(),
    )
    state = _FakeWorkflowState(project=_content_project(policy=policy), waiver=waiver)
    step = CouncilStep(workflow_state=state, settings=Settings())
    piece = Piece(
        slug="p", voice="demo-mira", stage=PieceStage.council, content_project_id="proj-effective-policy"
    )

    effective = await step._effective_policy(piece)

    assert effective.quality_bar == pytest.approx(6.0)
    assert effective.iteration_ceiling == 2
    assert effective.cost_ceiling_usd == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_effective_policy_keeps_unset_waiver_fields_at_base_value() -> None:
    from app.config import Settings
    from app.content_workflow.models import ActorRef, CouncilPolicy, QualityWaiver
    from app.models.common import utcnow

    policy = CouncilPolicy(quality_bar=7.0, iteration_ceiling=5, cost_ceiling_usd=1.0)
    waiver = QualityWaiver(
        content_project_id="proj-effective-policy",
        actor=ActorRef(subject_id="a@example.com", email="a@example.com"),
        reason="only iteration",
        iteration_ceiling=2,
        recorded_at=utcnow(),
    )
    state = _FakeWorkflowState(project=_content_project(policy=policy), waiver=waiver)
    step = CouncilStep(workflow_state=state, settings=Settings())
    piece = Piece(
        slug="p", voice="demo-mira", stage=PieceStage.council, content_project_id="proj-effective-policy"
    )

    effective = await step._effective_policy(piece)

    assert effective.quality_bar == pytest.approx(7.0)
    assert effective.iteration_ceiling == 2
    assert effective.cost_ceiling_usd == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_effective_policy_falls_back_to_settings_when_no_project() -> None:
    from app.config import Settings

    settings = Settings()
    state = _FakeWorkflowState(project=None)
    step = CouncilStep(workflow_state=state, settings=settings)
    piece = Piece(
        slug="p", voice="demo-mira", stage=PieceStage.council, content_project_id="missing-project"
    )

    effective = await step._effective_policy(piece)

    assert effective == settings.default_council_policy()


@pytest.mark.asyncio
async def test_effective_policy_falls_back_to_settings_for_legacy_piece() -> None:
    from app.config import Settings

    settings = Settings()
    state = _FakeWorkflowState(project=None)
    step = CouncilStep(workflow_state=state, settings=settings)
    piece = Piece(slug="p", voice="demo-mira", stage=PieceStage.council, content_project_id=None)

    effective = await step._effective_policy(piece)

    assert effective == settings.default_council_policy()
