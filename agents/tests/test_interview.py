"""Interview engine tests (D5-context-assembly §5; domain model §1.12; D16a/D16b).

Covers, per the acceptance criteria:
- serial personas, one question per turn, the transcript re-hydrated (whole, verbatim) every
  turn, including cross-persona coverage once the roster advances;
- the sacred transcript stored verbatim and interviewee-editable (D16b), never overwritten by a
  recap;
- D6 classification routing into the bounded op set with no silent drops (answer / research-this
  / meta-command incl. an unhandled-but-recorded case / tangent-to-Vault);
- mark-complete as a signal only (never touches the Piece stage);
- correct tiering via the provider (Opus question-gen; Sonnet classify/recap; Sonnet + web_search
  for the sidecar).

Zero external deps: the LLM path runs on a fake provider (no ``anthropic`` package, no key, no
network); Git runs against the real brain copied into a temp repo (``git_brain``/``content_store``
fixtures); Mongo runs on the in-memory ``store`` fixture. All from ``tests/conftest.py``.
"""

from __future__ import annotations

import json

import pytest

from app.interview import (
    AnsweredTurn,
    ClassificationParseError,
    IllegalInterviewOp,
    InterviewEngine,
    InterviewNotFound,
    MetaCommand,
    MetaCommandResult,
    NoPendingQuestionError,
    PendingQuestionError,
    ResearchResult,
    RosterExhausted,
    TangentResult,
    UnknownPersona,
    UnknownTurn,
)
from app.interview.classify import classify_input
from app.interview.research import WEB_SEARCH_TOOL
from app.llm.budget import RunBudget, RunBudgetExceeded
from app.llm.pricing import Usage, cost_usd
from app.llm.provider import LLMProvider, LLMResult
from app.llm.tiering import MODEL_GLM5, MODEL_SONNET, PipelineStep
from app.models import Piece, PieceStage
from app.orchestration import JobRunner, PieceMachine, build_stub_registry
from app.repositories import WorkStateStore

# --- test double: a scriptable provider, one canned-response queue per PipelineStep --------


class FakeInterviewProvider(LLMProvider):
    """Satisfies the swappable :class:`LLMProvider` seam. Each ``queue`` call enqueues one canned
    response for that step; ``complete`` pops the next queued response (or "" if none queued) and
    records every call for assertions — no ``anthropic`` package, no key, no network."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self._queues: dict[PipelineStep, list[str]] = {}

    def queue(self, step: PipelineStep, text: str) -> None:
        self._queues.setdefault(step, []).append(text)

    async def complete(
        self, *, step, model, system, messages, max_tokens, effort=None, thinking=None, tools=None, cache=False, budget=None
    ):
        if budget is not None:
            budget.check()
        queue = self._queues.get(step, [])
        text = queue.pop(0) if queue else ""
        self.calls.append(
            {
                "step": step,
                "model": model,
                "system": system,
                "messages": messages,
                "max_tokens": max_tokens,
                "thinking": thinking,
                "tools": tools,
            }
        )
        usage = Usage(input_tokens=100, output_tokens=20)
        if budget is not None:
            budget.charge(model, usage)
        return LLMResult(text=text, model=model, stop_reason="end_turn", usage=usage, cost_usd=cost_usd(model, usage))

    def stream(self, **kwargs):
        raise NotImplementedError("the interview engine never streams")

    async def count_tokens(self, *, model, system, messages):
        return 0


def _system_text(call: dict[str, object]) -> str:
    sys = call["system"]
    return " ".join(sys) if isinstance(sys, list) else str(sys)


def _classify(op: str, meta_command: str | None = None, note: str | None = None) -> str:
    return json.dumps({"op": op, "meta_command": meta_command, "note": note})


def _engine(store, content_store, git_brain, provider, *, lake=None, machine=None) -> InterviewEngine:
    return InterviewEngine(store, content_store, git_brain, provider, lake=lake, machine=machine)


async def _piece(store: WorkStateStore, *, slug: str, voice: str = "demo-mira") -> Piece:
    piece = Piece(slug=slug, voice=voice, stage=PieceStage.interviewing)
    return await store.pieces.insert(piece)


# --- 5a: serial personas, one question per turn, growing verbatim transcript ---------------


async def test_open_interview_rejects_unknown_persona(store, content_store, git_brain):
    engine = _engine(store, content_store, git_brain, FakeInterviewProvider())
    piece = await _piece(store, slug="p-unknown-persona")
    with pytest.raises(UnknownPersona):
        await engine.open_interview(piece.id, interviewer_personas=["not-a-real-persona"])


async def test_next_question_is_opus_reads_persona_and_style_guide_and_transcript_grows(
    store, content_store, git_brain
):
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-serial")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss", "skeptic"])

    provider.queue(PipelineStep.INTERVIEW_QUESTION, "What's the real storage workload?")
    interview = await engine.next_question(interview.id)
    assert interview.current_question == "What's the real storage workload?"

    call = provider.calls[-1]
    assert call["step"] == PipelineStep.INTERVIEW_QUESTION
    assert call["model"] == MODEL_GLM5  # INTERVIEW_QUESTION now routes to GLM5 live default
    system_text = _system_text(call)
    assert "Ferriss" in system_text  # the interviewer persona rubric (T0)

    # one question per turn — asking again while one is pending is illegal.
    with pytest.raises(PendingQuestionError):
        await engine.next_question(interview.id)

    # answer it: classify → answer, appends a transcript turn, clears the pending question.
    provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("answer"))
    provider.queue(PipelineStep.RECAP, "You said the workload is about 10TB at $230/month.")
    result = await engine.respond(interview.id, "About 10TB, roughly $230/month")
    assert isinstance(result, AnsweredTurn)
    assert result.turn.persona == "ferriss"
    assert result.turn.question == "What's the real storage workload?"
    assert result.turn.answer == "About 10TB, roughly $230/month"
    assert result.recap == "You said the workload is about 10TB at $230/month."

    classify_call = next(c for c in provider.calls if c["step"] == PipelineStep.INTERVIEW_CLASSIFY)
    assert classify_call["model"] == MODEL_GLM5  # classify now GLM5 live default
    # Sonnet 5 runs adaptive thinking by default even with no `thinking` field at all — every
    # Sonnet-tier call here must disable it explicitly, or its bounded budget can be spent
    # entirely on invisible thinking tokens before any visible output.
    assert classify_call["thinking"] == {"type": "disabled"}
    recap_call = next(c for c in provider.calls if c["step"] == PipelineStep.RECAP)
    assert recap_call["model"] == MODEL_GLM5  # recap now GLM5 live default
    assert recap_call["thinking"] == {"type": "disabled"}

    interview = await engine.get(interview.id)
    assert interview.current_question is None

    # the NEXT question re-hydrates the growing transcript verbatim (§5a's biggest lever).
    provider.queue(PipelineStep.INTERVIEW_QUESTION, "What's the failure version of that?")
    interview = await engine.next_question(interview.id)
    call2 = provider.calls[-1]
    assert "About 10TB, roughly $230/month" in _system_text(call2)
    assert interview.current_persona_index == 0  # still Ferriss — a persona isn't auto-advanced


async def test_second_persona_sees_first_personas_turns_verbatim(store, content_store, git_brain):
    """Cross-persona coverage (§5a enrichment #2) — free once the whole transcript is sent."""
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-cross-persona")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss", "skeptic"])

    provider.queue(PipelineStep.INTERVIEW_QUESTION, "Ferriss Q1")
    interview = await engine.next_question(interview.id)
    provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("answer"))
    provider.queue(PipelineStep.RECAP, "recap")
    await engine.respond(interview.id, "Ferriss answer one, a specific number")

    provider.queue(PipelineStep.INTERVIEW_QUESTION, "Ferriss Q2")
    interview = await engine.next_question(interview.id)
    provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("meta-command", "skip"))
    skip_result = await engine.respond(interview.id, "let's move to the next interviewer")
    assert isinstance(skip_result, MetaCommandResult) and skip_result.handled
    interview = await engine.get(interview.id)
    assert interview.current_persona_index == 1  # now Skeptic
    assert interview.current_question is None

    provider.queue(PipelineStep.INTERVIEW_QUESTION, "Skeptic Q1")
    interview = await engine.next_question(interview.id)
    call = provider.calls[-1]
    assert "Skeptic" in _system_text(call)
    assert "Ferriss answer one, a specific number" in _system_text(call)  # coverage carries over


async def test_next_question_roster_exhausted_after_skipping_past_last_persona(
    store, content_store, git_brain
):
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-roster-exhausted")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])

    provider.queue(PipelineStep.INTERVIEW_QUESTION, "Q1")
    interview = await engine.next_question(interview.id)
    provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("meta-command", "skip"))
    await engine.respond(interview.id, "move on")

    with pytest.raises(RosterExhausted):
        await engine.next_question(interview.id)


async def test_go_back_returns_to_the_previous_persona(store, content_store, git_brain):
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-go-back")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss", "skeptic"])

    provider.queue(PipelineStep.INTERVIEW_QUESTION, "Ferriss Q1")
    interview = await engine.next_question(interview.id)
    provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("meta-command", "skip"))
    await engine.respond(interview.id, "skip")
    interview = await engine.get(interview.id)
    assert interview.current_persona_index == 1

    provider.queue(PipelineStep.INTERVIEW_QUESTION, "Skeptic Q1")
    interview = await engine.next_question(interview.id)
    provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("meta-command", "go-back"))
    await engine.respond(interview.id, "actually go back")
    interview = await engine.get(interview.id)
    assert interview.current_persona_index == 0


# --- advance_persona: skip/go-back with no classifier call and no pending-question gate ------
# The real complaint this closes (Hendo, 2026-08-10): skipping to the next persona used to force
# generating a throwaway question first, because `respond()` requires one pending before any
# meta-command — including skip/go-back, which are pure index arithmetic and never needed it.


async def test_advance_persona_skip_with_no_pending_question_and_no_classifier_call(
    store, content_store, git_brain
):
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-advance-skip-no-question")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss", "skeptic"])
    assert interview.current_question is None  # never asked — the exact scenario Hendo hit

    result = await engine.advance_persona(interview.id, MetaCommand.skip)
    assert isinstance(result, MetaCommandResult)
    assert result.command == MetaCommand.skip
    assert result.handled

    interview = await engine.get(interview.id)
    assert interview.current_persona_index == 1
    assert interview.current_question is None
    assert provider.calls == []  # no classifier (or any model) call was made


async def test_advance_persona_go_back_with_no_pending_question(store, content_store, git_brain):
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-advance-go-back-no-question")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss", "skeptic"])
    await engine.advance_persona(interview.id, MetaCommand.skip)

    result = await engine.advance_persona(interview.id, MetaCommand.go_back)
    assert result.command == MetaCommand.go_back and result.handled

    interview = await engine.get(interview.id)
    assert interview.current_persona_index == 0
    assert provider.calls == []


async def test_advance_persona_discards_a_pending_question_without_calling_the_classifier(
    store, content_store, git_brain
):
    """Skipping mid-question (one already asked, unanswered) must not route through `respond`'s
    classifier either — the pending question is simply discarded, not answered or classified."""
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-advance-skip-pending-question")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss", "skeptic"])

    provider.queue(PipelineStep.INTERVIEW_QUESTION, "Ferriss Q1")
    interview = await engine.next_question(interview.id)
    assert interview.current_question == "Ferriss Q1"
    calls_before = len(provider.calls)

    await engine.advance_persona(interview.id, MetaCommand.skip)

    interview = await engine.get(interview.id)
    assert interview.current_persona_index == 1
    assert interview.current_question is None
    assert len(provider.calls) == calls_before  # no classify call was added


async def test_advance_persona_skip_clamps_at_roster_length(store, content_store, git_brain):
    engine = _engine(store, content_store, git_brain, FakeInterviewProvider())
    piece = await _piece(store, slug="p-advance-skip-clamp")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])

    await engine.advance_persona(interview.id, MetaCommand.skip)
    await engine.advance_persona(interview.id, MetaCommand.skip)  # already exhausted — re-skip

    interview = await engine.get(interview.id)
    assert interview.current_persona_index == 1  # clamped, never past len(personas)


async def test_advance_persona_go_back_clamps_at_zero(store, content_store, git_brain):
    engine = _engine(store, content_store, git_brain, FakeInterviewProvider())
    piece = await _piece(store, slug="p-advance-go-back-clamp")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss", "skeptic"])

    await engine.advance_persona(interview.id, MetaCommand.go_back)  # already at 0

    interview = await engine.get(interview.id)
    assert interview.current_persona_index == 0


async def test_advance_persona_rejects_a_non_navigation_direction(store, content_store, git_brain):
    engine = _engine(store, content_store, git_brain, FakeInterviewProvider())
    piece = await _piece(store, slug="p-advance-bad-direction")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])
    with pytest.raises(ValueError):
        await engine.advance_persona(interview.id, MetaCommand.restart)


async def test_advance_persona_unknown_interview_raises(store, content_store, git_brain):
    engine = _engine(store, content_store, git_brain, FakeInterviewProvider())
    with pytest.raises(InterviewNotFound):
        await engine.advance_persona("does-not-exist", MetaCommand.skip)


# --- 5b/D6: classification + routing, no silent drops ---------------------------------------


async def test_respond_without_pending_question_raises(store, content_store, git_brain):
    engine = _engine(store, content_store, git_brain, FakeInterviewProvider())
    piece = await _piece(store, slug="p-no-pending")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])
    with pytest.raises(NoPendingQuestionError):
        await engine.respond(interview.id, "hello")


async def test_respond_research_this_is_sonnet_plus_web_search_and_preserves_pending_question(
    store, content_store, git_brain
):
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-research")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])

    provider.queue(PipelineStep.INTERVIEW_QUESTION, "What's the S3 bill?")
    interview = await engine.next_question(interview.id)

    provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("research-this"))
    provider.queue(PipelineStep.RESEARCH, "10TB in S3 Standard is about $230/month.")
    result = await engine.respond(interview.id, "/research the S3 pricing")

    assert isinstance(result, ResearchResult)
    assert result.answer == "10TB in S3 Standard is about $230/month."
    assert result.resume_question == "What's the S3 bill?"  # the announced return point

    research_call = next(c for c in provider.calls if c["step"] == PipelineStep.RESEARCH)
    assert research_call["model"] == MODEL_SONNET
    assert research_call["tools"] == WEB_SEARCH_TOOL
    assert research_call["thinking"] == {"type": "disabled"}

    interview = await engine.get(interview.id)
    assert interview.current_question == "What's the S3 bill?"  # borrowed time, then returned


async def test_research_folds_in_content_lake_candidates(store, content_store, git_brain, lake):
    from app.lake import ContentLakeItem, ContentMetadata
    from app.models.source import SourceClassification

    await lake.ingest(
        ContentLakeItem(
            raw_content="S3 pricing is $0.023/GB-month for the standard tier.",
            source_id="src1",
            classification=SourceClassification.scraped_periodically,
            metadata=ContentMetadata(tags=["pricing"]),
        )
    )
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider, lake=lake)
    piece = await _piece(store, slug="p-research-lake")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])

    provider.queue(PipelineStep.INTERVIEW_QUESTION, "Q1")
    interview = await engine.next_question(interview.id)
    provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("research-this"))
    provider.queue(PipelineStep.RESEARCH, "Confirmed: $0.023/GB-month.")
    await engine.respond(interview.id, "verify the S3 pricing")

    research_call = next(c for c in provider.calls if c["step"] == PipelineStep.RESEARCH)
    tail = research_call["messages"][0]["content"]
    assert "S3 pricing is $0.023/GB-month" in tail


async def test_research_sidecar_degrades_when_anthropic_key_is_missing(
    content_store, git_brain, monkeypatch
):
    """F5 (cmw-local-stack-gap-audit): a blank/misconfigured ANTHROPIC_API_KEY for the research
    sidecar's own direct-Anthropic carve-out (research.py:51-52) must degrade to a clear,
    user-facing message — never raise a RuntimeError that would otherwise fall through
    InterviewEngine._route_research / respond() / the /respond route as a raw 500."""
    from app.interview.research import RESEARCH_UNAVAILABLE_MESSAGE, research
    from app.llm import AnthropicLLMProvider
    from app.llm.assembler import PromptAssembler

    def _raise_no_key() -> AnthropicLLMProvider:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not configured; the LLM layer needs the single "
            "server-side company key (D14)."
        )

    monkeypatch.setattr(AnthropicLLMProvider, "from_settings", staticmethod(_raise_no_key))

    assembler = PromptAssembler(git_brain, content_store)
    answer = await research(None, assembler, query="what does this cost?")

    assert answer == RESEARCH_UNAVAILABLE_MESSAGE


async def test_meta_command_add_and_drop_interviewer(store, content_store, git_brain):
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-add-drop")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])

    provider.queue(PipelineStep.INTERVIEW_QUESTION, "Q1")
    interview = await engine.next_question(interview.id)

    provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("meta-command", "add-interviewer", "skeptic"))
    result = await engine.respond(interview.id, "add the skeptic")
    assert isinstance(result, MetaCommandResult) and result.handled and result.note == "skeptic"
    interview = await engine.get(interview.id)
    assert interview.interviewer_personas == ["ferriss", "skeptic"]
    assert interview.current_question == "Q1"  # add doesn't disturb the pending question

    provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("meta-command", "drop-interviewer", "skeptic"))
    result2 = await engine.respond(interview.id, "actually drop the skeptic")
    assert result2.handled
    interview = await engine.get(interview.id)
    assert interview.interviewer_personas == ["ferriss"]


async def test_meta_command_add_unknown_persona_is_not_silently_dropped(store, content_store, git_brain):
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-add-unknown")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])
    provider.queue(PipelineStep.INTERVIEW_QUESTION, "Q1")
    interview = await engine.next_question(interview.id)

    provider.queue(
        PipelineStep.INTERVIEW_CLASSIFY, _classify("meta-command", "add-interviewer", "not-a-real-persona")
    )
    result = await engine.respond(interview.id, "add nonsense")
    assert isinstance(result, MetaCommandResult)
    assert result.handled is False
    assert result.note == "not-a-real-persona"  # recorded, never a silent no-op (D6)


async def test_meta_command_switch_piece_is_recorded_not_enacted(store, content_store, git_brain):
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-switch-piece")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])
    provider.queue(PipelineStep.INTERVIEW_QUESTION, "Q1")
    interview = await engine.next_question(interview.id)

    provider.queue(
        PipelineStep.INTERVIEW_CLASSIFY, _classify("meta-command", "switch-piece", "aws-gsi-faq")
    )
    result = await engine.respond(interview.id, "switch to the aws piece")
    assert isinstance(result, MetaCommandResult)
    assert result.command == MetaCommand.switch_piece
    assert result.handled is False
    assert result.note == "aws-gsi-faq"  # no silent drop — the caller sees exactly what to do

    interview = await engine.get(interview.id)
    assert interview.current_question == "Q1"  # unhandled op never disturbs local state


async def test_meta_command_novel_move_is_recorded_as_other(store, content_store, git_brain):
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-novel-move")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])
    provider.queue(PipelineStep.INTERVIEW_QUESTION, "Q1")
    interview = await engine.next_question(interview.id)

    provider.queue(
        PipelineStep.INTERVIEW_CLASSIFY,
        _classify("meta-command", "other", "reorder the personas alphabetically"),
    )
    result = await engine.respond(interview.id, "shuffle the roster around")
    assert isinstance(result, MetaCommandResult)
    assert result.command == MetaCommand.other
    assert result.handled is False
    assert result.note == "reorder the personas alphabetically"


async def test_meta_command_stop_for_the_day_pauses_the_piece_via_machine(store, content_store, git_brain):
    registry = build_stub_registry()
    runner = JobRunner(store, registry)
    machine = PieceMachine(store, runner)
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider, machine=machine)
    piece = await _piece(store, slug="p-stop-for-day")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])
    provider.queue(PipelineStep.INTERVIEW_QUESTION, "Q1")
    interview = await engine.next_question(interview.id)

    provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("meta-command", "stop-for-the-day"))
    result = await engine.respond(interview.id, "let's stop for today")
    assert isinstance(result, MetaCommandResult) and result.handled

    updated_piece = await store.pieces.get(piece.id)
    assert updated_piece.stage == PieceStage.paused


async def test_meta_command_stop_for_the_day_without_machine_is_recorded_not_enacted(
    store, content_store, git_brain
):
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)  # no machine wired
    piece = await _piece(store, slug="p-stop-no-machine")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])
    provider.queue(PipelineStep.INTERVIEW_QUESTION, "Q1")
    interview = await engine.next_question(interview.id)

    provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("meta-command", "stop-for-the-day"))
    result = await engine.respond(interview.id, "stop for today")
    assert isinstance(result, MetaCommandResult)
    assert result.handled is False


async def test_respond_tangent_parks_to_vault_as_spike_never_dropped(store, content_store, git_brain):
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-tangent")
    interview = await engine.open_interview(
        piece.id, interviewer_personas=["ferriss"], assigned_expert="demo-mira@x"
    )
    provider.queue(PipelineStep.INTERVIEW_QUESTION, "Q1")
    interview = await engine.next_question(interview.id)

    provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("tangent"))
    result = await engine.respond(interview.id, "unrelated: we should write about pricing tiers too")
    assert isinstance(result, TangentResult)

    spike = await store.spikes.get(result.spike_id)
    assert spike is not None
    assert spike.origin.kind == "tangent"
    assert spike.status == "vaulted"
    assert spike.creator == "demo-mira@x"
    assert spike.convergence_score is None

    interview = await engine.get(interview.id)
    assert interview.current_question == "Q1"  # the tangent never disturbs the pending question


async def test_classification_parse_error_on_malformed_output(store, content_store, git_brain):
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-parse-error")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])
    provider.queue(PipelineStep.INTERVIEW_QUESTION, "Q1")
    interview = await engine.next_question(interview.id)

    provider.queue(PipelineStep.INTERVIEW_CLASSIFY, "not json at all")
    with pytest.raises(ClassificationParseError):
        await engine.respond(interview.id, "whatever")


class _SequencedProvider(LLMProvider):
    """Returns one (text, stop_reason) pair per call, in order — for exercising
    classify_input's stop_reason == "max_tokens" retry path directly, without a real call."""

    def __init__(self, responses: list[tuple[str, str]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    async def complete(
        self, *, step, model, system, messages, max_tokens, effort=None, thinking=None, tools=None, cache=False, budget=None
    ):
        text, stop_reason = self.responses[len(self.calls)]
        self.calls.append({"max_tokens": max_tokens, "thinking": thinking})
        return LLMResult(text=text, model=model, stop_reason=stop_reason, usage=Usage(), cost_usd=0.0)

    def stream(self, **kwargs):
        raise NotImplementedError

    async def count_tokens(self, *, model, system, messages):
        return 0


async def test_classify_input_retries_once_after_hitting_the_token_ceiling():
    """A stop_reason of "max_tokens" is a truncated response, not a malformed one — mirrors the
    same fix in app/review/classify.py for the sibling Sonnet-tier classify call."""
    provider = _SequencedProvider(
        responses=[
            ("", "max_tokens"),
            (_classify("answer"), "end_turn"),
        ]
    )
    result = await classify_input(
        provider, text="hi", active_piece="p", active_persona="ferriss", current_question="Q?"
    )

    assert result.op.value == "answer"
    assert len(provider.calls) == 2
    assert provider.calls[1]["max_tokens"] > provider.calls[0]["max_tokens"]
    assert provider.calls[0]["thinking"] == {"type": "disabled"}


async def test_classify_input_raises_a_distinct_error_when_the_ceiling_is_hit_twice():
    provider = _SequencedProvider(responses=[("", "max_tokens"), ("", "max_tokens")])
    with pytest.raises(ClassificationParseError, match="stop_reason=max_tokens"):
        await classify_input(
            provider, text="hi", active_piece="p", active_persona="ferriss", current_question="Q?"
        )
    assert len(provider.calls) == 2


# --- mark-complete: a signal only (D16a) -----------------------------------------------------


async def test_mark_complete_is_a_signal_only(store, content_store, git_brain):
    engine = _engine(store, content_store, git_brain, FakeInterviewProvider())
    piece = await _piece(store, slug="p-mark-complete")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])

    updated = await engine.mark_complete(interview.id)
    assert updated.status == "complete"

    piece_after = await store.pieces.get(piece.id)
    assert piece_after.stage == PieceStage.interviewing  # untouched — only a human trigger advances


async def test_mark_complete_unknown_interview_raises(store, content_store, git_brain):
    engine = _engine(store, content_store, git_brain, FakeInterviewProvider())
    with pytest.raises(InterviewNotFound):
        await engine.mark_complete("not-a-real-id")


# --- the sacred transcript: verbatim, interviewee-editable, recap never overwrites it (D16b) --


async def test_edit_answer_splices_verbatim_and_recap_can_regenerate(store, content_store, git_brain):
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-edit-answer")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])

    provider.queue(PipelineStep.INTERVIEW_QUESTION, "How much storage?")
    interview = await engine.next_question(interview.id)
    provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("answer"))
    provider.queue(PipelineStep.RECAP, "You said 10TB.")
    result = await engine.respond(interview.id, "About 10TB")
    turn_id = result.turn.id

    edited = await engine.edit_answer(
        piece.id, turn_id, "Actually more like 12TB, I checked the console.", interview_id=interview.id
    )
    assert edited.answer == "Actually more like 12TB, I checked the console."
    assert edited.question == "How much storage?"

    transcript_text = await engine.transcript(piece.id)
    assert "Actually more like 12TB, I checked the console." in transcript_text
    assert "About 10TB" not in transcript_text  # spliced in place, not appended alongside the old

    provider.queue(PipelineStep.RECAP, "You said 12TB.")
    recap_text = await engine.recap_turn(piece.id, turn_id)
    assert recap_text == "You said 12TB."  # regenerated over the new text — never auto-written back

    with pytest.raises(UnknownTurn):
        await engine.edit_answer(piece.id, "0" * 24, "x", interview_id=interview.id)


async def test_edit_answer_refused_once_its_interview_is_complete(store, content_store, git_brain):
    """Once *this* interview is complete, its transcript surface is read-only (Hendo, 2026-08-08) —
    even though the underlying transcript file is piece-scoped, not interview-scoped."""
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-edit-after-complete")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])

    provider.queue(PipelineStep.INTERVIEW_QUESTION, "How much storage?")
    interview = await engine.next_question(interview.id)
    provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("answer"))
    provider.queue(PipelineStep.RECAP, "You said 10TB.")
    result = await engine.respond(interview.id, "About 10TB")
    turn_id = result.turn.id

    await engine.mark_complete(interview.id)

    with pytest.raises(IllegalInterviewOp):
        await engine.edit_answer(piece.id, turn_id, "Actually 12TB", interview_id=interview.id)

    # unchanged — the rejected edit never touched the transcript.
    transcript_text = await engine.transcript(piece.id)
    assert "About 10TB" in transcript_text
    assert "Actually 12TB" not in transcript_text

    # recap stays available — it never writes back over the stored answer (D16b), so completion
    # doesn't need to gate it.
    provider.queue(PipelineStep.RECAP, "You said 10TB, still.")
    recap_text = await engine.recap_turn(piece.id, turn_id)
    assert recap_text == "You said 10TB, still."


async def test_edit_answer_on_a_sibling_open_interview_does_not_reopen_a_completed_one(
    store, content_store, git_brain
):
    """Multiple interviews can feed one piece (domain model §1.12) — a sibling interview being
    open must not let an edit through *on behalf of* a different, completed interview's id."""
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-edit-sibling")
    complete_interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])
    open_interview = await engine.open_interview(piece.id, interviewer_personas=["skeptic"])

    provider.queue(PipelineStep.INTERVIEW_QUESTION, "Q1")
    complete_interview = await engine.next_question(complete_interview.id)
    provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("answer"))
    provider.queue(PipelineStep.RECAP, "recap")
    result = await engine.respond(complete_interview.id, "A1")
    turn_id = result.turn.id
    await engine.mark_complete(complete_interview.id)

    # the completed interview's own id still refuses, regardless of the sibling's open status.
    with pytest.raises(IllegalInterviewOp):
        await engine.edit_answer(piece.id, turn_id, "edited", interview_id=complete_interview.id)

    # a real edit against the open sibling's id succeeds (it doesn't own turn_id, but the engine
    # has no per-turn interview attribution to check against — see transcript.py's turn anchor).
    edited = await engine.edit_answer(
        piece.id, turn_id, "edited via the open sibling", interview_id=open_interview.id
    )
    assert edited.answer == "edited via the open sibling"


async def test_edit_answer_rejects_an_interview_id_from_a_different_piece(
    store, content_store, git_brain
):
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece_a = await _piece(store, slug="p-cross-a")
    piece_b = await _piece(store, slug="p-cross-b")
    interview_b = await engine.open_interview(piece_b.id, interviewer_personas=["ferriss"])

    with pytest.raises(InterviewNotFound):
        await engine.edit_answer(piece_a.id, "0" * 24, "x", interview_id=interview_b.id)


# --- provider requirement + budget ceiling ----------------------------------------------------


async def test_engine_without_provider_raises_a_clear_error(store, content_store, git_brain):
    engine = _engine(store, content_store, git_brain, None)
    piece = await _piece(store, slug="p-no-provider")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])
    with pytest.raises(RuntimeError):
        await engine.next_question(interview.id)


async def test_budget_ceiling_blocks_next_question(store, content_store, git_brain):
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-budget")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])
    with pytest.raises(RunBudgetExceeded):
        await engine.next_question(interview.id, budget=RunBudget(max_calls=0))



# --- the REST surface (the engine is FastAPI-hosted) ------------------------------------------


def _wire_app(store, content_store, git_brain, provider, *, machine=None):
    from app.main import app

    app.state.interview_engine = InterviewEngine(
        store, content_store, git_brain, provider, machine=machine
    )
    return app


async def _http(app):
    from httpx import ASGITransport, AsyncClient

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_http_open_next_question_respond_transcript_mark_complete(store, content_store, git_brain):
    provider = FakeInterviewProvider()
    app = _wire_app(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-http-flow")

    async with await _http(app) as client:
        opened = await client.post(
            f"/api/pieces/{piece.id}/interviews", json={"interviewer_personas": ["ferriss"]}
        )
        assert opened.status_code == 200
        interview_id = opened.json()["id"]
        assert opened.json()["interviewer_personas"] == ["ferriss"]

        provider.queue(PipelineStep.INTERVIEW_QUESTION, "What's the workload?")
        asked = await client.post(f"/api/interviews/{interview_id}/next-question")
        assert asked.status_code == 200
        assert asked.json()["current_question"] == "What's the workload?"

        provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("answer"))
        provider.queue(PipelineStep.RECAP, "recap text")
        responded = await client.post(f"/api/interviews/{interview_id}/respond", json={"text": "10TB"})
        assert responded.status_code == 200
        body = responded.json()
        assert body["op"] == "answer"
        assert body["turn"]["answer"] == "10TB"

        transcript = await client.get(f"/api/pieces/{piece.id}/transcript")
        assert transcript.status_code == 200
        assert "10TB" in transcript.json()["transcript_md"]

        completed = await client.post(f"/api/interviews/{interview_id}/mark-complete")
        assert completed.status_code == 200
        assert completed.json()["status"] == "complete"


async def test_http_advance_persona_skip_needs_no_pending_question(store, content_store, git_brain):
    """The real hole this fix closes at the HTTP surface: skip must succeed with zero questions
    ever asked — reproducing, then closing, the exact live complaint."""
    provider = FakeInterviewProvider()
    app = _wire_app(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-http-advance-skip")

    async with await _http(app) as client:
        opened = await client.post(
            f"/api/pieces/{piece.id}/interviews",
            json={"interviewer_personas": ["ferriss", "skeptic"]},
        )
        interview_id = opened.json()["id"]
        assert opened.json()["current_question"] is None

        skipped = await client.post(
            f"/api/interviews/{interview_id}/advance-persona", json={"direction": "skip"}
        )
        assert skipped.status_code == 200
        body = skipped.json()
        assert body["op"] == "meta-command"
        assert body["command"] == "skip"
        assert body["handled"] is True
        assert provider.calls == []

        after = await client.get(f"/api/interviews/{interview_id}")
        assert after.json()["current_persona_index"] == 1

        went_back = await client.post(
            f"/api/interviews/{interview_id}/advance-persona", json={"direction": "go-back"}
        )
        assert went_back.status_code == 200
        assert went_back.json()["command"] == "go-back"

        after2 = await client.get(f"/api/interviews/{interview_id}")
        assert after2.json()["current_persona_index"] == 0


async def test_http_advance_persona_404_unknown_interview_and_422_bad_direction(
    store, content_store, git_brain
):
    app = _wire_app(store, content_store, git_brain, FakeInterviewProvider())
    async with await _http(app) as client:
        missing = await client.post(
            "/api/interviews/doesnotexist/advance-persona", json={"direction": "skip"}
        )
        assert missing.status_code == 404

        piece = await _piece(store, slug="p-http-advance-bad-direction")
        opened = await client.post(
            f"/api/pieces/{piece.id}/interviews", json={"interviewer_personas": ["ferriss"]}
        )
        interview_id = opened.json()["id"]
        bad = await client.post(
            f"/api/interviews/{interview_id}/advance-persona", json={"direction": "restart"}
        )
        assert bad.status_code == 422


async def test_http_open_interview_422_unknown_persona(store, content_store, git_brain):
    provider = FakeInterviewProvider()
    app = _wire_app(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-http-422")
    async with await _http(app) as client:
        resp = await client.post(
            f"/api/pieces/{piece.id}/interviews", json={"interviewer_personas": ["nonexistent"]}
        )
        assert resp.status_code == 422


async def test_http_404_unknown_interview_and_409_no_pending_question(store, content_store, git_brain):
    provider = FakeInterviewProvider()
    app = _wire_app(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-http-409")

    async with await _http(app) as client:
        missing = await client.get("/api/interviews/doesnotexist")
        assert missing.status_code == 404

        opened = await client.post(
            f"/api/pieces/{piece.id}/interviews", json={"interviewer_personas": ["ferriss"]}
        )
        interview_id = opened.json()["id"]

        resp = await client.post(f"/api/interviews/{interview_id}/respond", json={"text": "hi"})
        assert resp.status_code == 409


def test_http_503_when_engine_unconfigured():
    from fastapi.testclient import TestClient

    from app.main import app

    app.state.interview_engine = None
    resp = TestClient(app).get("/api/interviews/x")
    assert resp.status_code == 503


async def test_http_list_interviewer_personas_roster(store, content_store, git_brain):
    """The full ~10-persona roster (§1.2) — a UI persona menu's seam for showing on/off state."""
    app = _wire_app(store, content_store, git_brain, FakeInterviewProvider())
    async with await _http(app) as client:
        resp = await client.get("/api/personas/interviewers")
        assert resp.status_code == 200
        roster = resp.json()
        assert "ferriss" in roster
        assert "skeptic" in roster
        assert roster == sorted(roster)  # GitBrain.list_personas returns them sorted


async def test_http_transcript_turns_structured(store, content_store, git_brain):
    """Structured turns (parsed server-side) rather than callers re-parsing raw markdown."""
    provider = FakeInterviewProvider()
    app = _wire_app(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-http-turns")

    async with await _http(app) as client:
        opened = await client.post(
            f"/api/pieces/{piece.id}/interviews", json={"interviewer_personas": ["ferriss"]}
        )
        interview_id = opened.json()["id"]

        provider.queue(PipelineStep.INTERVIEW_QUESTION, "What's the workload?")
        await client.post(f"/api/interviews/{interview_id}/next-question")

        provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("answer"))
        provider.queue(PipelineStep.RECAP, "recap text")
        await client.post(f"/api/interviews/{interview_id}/respond", json={"text": "10TB"})

        turns = await client.get(f"/api/pieces/{piece.id}/transcript/turns")
        assert turns.status_code == 200
        body = turns.json()
        assert len(body) == 1
        assert body[0]["persona"] == "ferriss"
        assert body[0]["question"] == "What's the workload?"
        assert body[0]["answer"] == "10TB"

    async with await _http(app) as client2:
        missing = await client2.get("/api/pieces/not-a-real-piece/transcript/turns")
        assert missing.status_code == 404


async def test_http_edit_answer_409_once_complete_but_200_while_open(store, content_store, git_brain):
    """The real hole this fix closes: the edit-turn route itself, not just a UI control, must
    refuse a write once the referenced interview is complete."""
    provider = FakeInterviewProvider()
    app = _wire_app(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-http-edit-gate")

    async with await _http(app) as client:
        opened = await client.post(
            f"/api/pieces/{piece.id}/interviews", json={"interviewer_personas": ["ferriss"]}
        )
        interview_id = opened.json()["id"]

        provider.queue(PipelineStep.INTERVIEW_QUESTION, "What's the workload?")
        await client.post(f"/api/interviews/{interview_id}/next-question")
        provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("answer"))
        provider.queue(PipelineStep.RECAP, "recap text")
        responded = await client.post(f"/api/interviews/{interview_id}/respond", json={"text": "10TB"})
        turn_id = responded.json()["turn"]["id"]

        # open: the direct endpoint call succeeds.
        edited = await client.post(
            f"/api/pieces/{piece.id}/transcript/turns/{turn_id}",
            json={"text": "12TB", "interview_id": interview_id},
        )
        assert edited.status_code == 200
        assert edited.json()["answer"] == "12TB"

        # recap always stays available — it never writes back over the transcript.
        recapped = await client.post(f"/api/pieces/{piece.id}/transcript/turns/{turn_id}/recap")
        assert recapped.status_code == 200

        await client.post(f"/api/interviews/{interview_id}/mark-complete")

        # complete: the same endpoint now refuses, even called directly (not through any UI).
        blocked = await client.post(
            f"/api/pieces/{piece.id}/transcript/turns/{turn_id}",
            json={"text": "13TB", "interview_id": interview_id},
        )
        assert blocked.status_code == 409

        # recap is unaffected by completion — still read-only, still available.
        recapped_after = await client.post(f"/api/pieces/{piece.id}/transcript/turns/{turn_id}/recap")
        assert recapped_after.status_code == 200

        # an unknown interview_id 404s rather than silently succeeding or 500ing.
        unknown = await client.post(
            f"/api/pieces/{piece.id}/transcript/turns/{turn_id}",
            json={"text": "14TB", "interview_id": "not-a-real-interview"},
        )
        assert unknown.status_code == 404


# --- staleness triage (cmw-staleness-timestamps): answering/editing counts as a human touch ---
#
# Deliberately narrow: only a real transcript write (`respond`'s "answer" op, or `edit_answer`)
# stamps `Piece.last_human_touch_at`. Session-management ops on the SAME interview (asking the
# next question, a research-sidecar detour, meta-commands, mark-complete) do not — none of them
# land human-authored content on the piece, and generating a question is itself an LLM (machine)
# call. `respond`'s own `_charge` cost-accounting write is a separate, coincidental piece touch
# (fires on nonzero LLM spend, not on "did a human answer") and must not be confused with this.


async def test_answering_a_question_stamps_last_human_touch_at(store, content_store, git_brain):
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-human-touch")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])

    assert (await store.pieces.get(piece.id)).last_human_touch_at is None

    provider.queue(PipelineStep.INTERVIEW_QUESTION, "How much storage?")
    await engine.next_question(interview.id)
    # asking the question alone is a machine (LLM) call — no human touch yet.
    assert (await store.pieces.get(piece.id)).last_human_touch_at is None

    provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("answer"))
    provider.queue(PipelineStep.RECAP, "You said 10TB.")
    await engine.respond(interview.id, "About 10TB")

    assert (await store.pieces.get(piece.id)).last_human_touch_at is not None


async def test_editing_an_answer_stamps_last_human_touch_at(store, content_store, git_brain):
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-human-touch-edit")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])

    provider.queue(PipelineStep.INTERVIEW_QUESTION, "How much storage?")
    await engine.next_question(interview.id)
    provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("answer"))
    provider.queue(PipelineStep.RECAP, "You said 10TB.")
    result = await engine.respond(interview.id, "About 10TB")

    # reset it, so this test proves `edit_answer` itself stamps — not a leftover from `respond`.
    await store.pieces.update(piece.id, {"last_human_touch_at": None})
    assert (await store.pieces.get(piece.id)).last_human_touch_at is None

    await engine.edit_answer(
        piece.id, result.turn.id, "Actually 12TB", interview_id=interview.id
    )

    assert (await store.pieces.get(piece.id)).last_human_touch_at is not None


async def test_research_sidecar_detour_does_not_stamp_human_touch(store, content_store, git_brain):
    """A research request is the interviewee talking, but it never lands answer content on the
    piece — the pending question is returned untouched, "borrowed time, then returned"."""
    provider = FakeInterviewProvider()
    engine = _engine(store, content_store, git_brain, provider)
    piece = await _piece(store, slug="p-research-no-touch")
    interview = await engine.open_interview(piece.id, interviewer_personas=["ferriss"])

    provider.queue(PipelineStep.INTERVIEW_QUESTION, "How much storage?")
    await engine.next_question(interview.id)
    provider.queue(PipelineStep.INTERVIEW_CLASSIFY, _classify("research-this"))
    provider.queue(PipelineStep.RESEARCH, "Here's what I found.")
    result = await engine.respond(interview.id, "Can you look up our current pricing tier?")

    assert isinstance(result, ResearchResult)
    assert (await store.pieces.get(piece.id)).last_human_touch_at is None
