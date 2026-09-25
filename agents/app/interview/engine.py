"""The interview engine (D5-context-assembly §5; domain model §1.12; D16a/D16b).

Composes the four stateless sub-steps — :mod:`~app.interview.question` (5a, Opus),
:mod:`~app.interview.classify` (5b/D6, Sonnet), :mod:`~app.interview.research` (5c, Sonnet +
web_search), :mod:`~app.interview.recap` (5d, Sonnet) — into the turn-taking session: serial
personas, one question per turn, the growing transcript re-hydrated every turn (continuity comes
from re-reading Git + Mongo, never from model memory).

:class:`InterviewEngine` owns persistence and D6 routing:

- **Interview metadata** (assignment, roster, ``status``, per-turn continuity) → Mongo, through
  :class:`~app.repositories.WorkStateStore` (D3).
- **The transcript** (the sacred source, D16b) → Git, through
  :mod:`app.interview.transcript` / :class:`~app.git.GitContentStore` (D4).
- **D6 routing**, with no silent drops: ``answer`` → a new transcript turn; ``research-this`` → the
  sidecar, the pending question untouched ("borrowed time, then returned"); ``meta-command`` → the
  bounded subset this piece-scoped engine can enact (add/drop-interviewer, restart, skip/go-back
  to move the active persona forward/back through the roster, stop-for-the-day via the piece
  machine); ``switch-piece``/``other`` are cross-piece or ambiguous, so they are recorded and
  returned unhandled, never silently dropped; ``tangent`` → parked to the Vault as a Spike with
  ``origin.kind=tangent`` (§5-Q2), never discarded.
- **Mark-complete is a signal only** (D16a): it flips ``Interview.status``, never the Piece stage —
  the "enough input" human trigger (``PieceMachine.enough_input``) is the only thing that advances
  the piece to drafting.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from app.git.brain import GitBrain
from app.git.content import GitContentStore
from app.interview.classify import ClassifiedInput, InputOp, MetaCommand, classify_input
from app.interview.question import DEFAULT_QUESTION_MAX_TOKENS, ask_next_question
from app.interview.recap import DEFAULT_RECAP_MAX_TOKENS, recap_answer
from app.interview.research import DEFAULT_RESEARCH_MAX_TOKENS
from app.interview.research import research as research_sidecar
from app.interview.transcript import (
    TranscriptTurn,
    append_turn,
    edit_answer,
    parse_turns,
    read_transcript,
)
from app.lake import ContentLake
from app.llm.assembler import PromptAssembler
from app.llm.budget import RunBudget
from app.llm.provider import LLMProvider
from app.models import (
    Interview,
    InterviewStatus,
    Piece,
    Spike,
    SpikeOrigin,
    SpikeOriginKind,
    SpikeStatus,
)
from app.orchestration.machine import PieceMachine
from app.repositories import WorkStateStore

# Meta-commands this piece-scoped engine directly enacts. "skip" / "go-back" are the roster
# navigation within a serial interview (advance/retreat the active persona — a persona can take
# several turns before the roster moves on, so nothing else advances it). "switch-piece" / "other"
# are cross-piece or ambiguous concerns outside this engine's remit — recorded, never enacted here
# (D6 "no silent drops": every op still returns a clear, structured result).
_ENACTED_META_COMMANDS = frozenset(
    {
        MetaCommand.add_interviewer,
        MetaCommand.drop_interviewer,
        MetaCommand.restart,
        MetaCommand.stop_for_the_day,
        MetaCommand.skip,
        MetaCommand.go_back,
    }
)


class InterviewNotFound(KeyError):
    """No :class:`~app.models.Interview` exists for the given id."""


class UnknownPersona(ValueError):
    """A persona name isn't a file under ``interviewers/`` in the Git brain."""


class UnknownTurn(KeyError):
    """No transcript turn exists for the given id on this piece."""


class IllegalInterviewOp(ValueError):
    """An interview operation was attempted from a state where it isn't legal."""


class PendingQuestionError(IllegalInterviewOp):
    """A new question was requested while one is still awaiting a response."""


class NoPendingQuestionError(IllegalInterviewOp):
    """Free-form input arrived with no pending question to respond to."""


class RosterExhausted(IllegalInterviewOp):
    """Every persona in the roster has already been cycled through."""


class AnsweredTurn(BaseModel):
    op: Literal["answer"] = "answer"
    turn: TranscriptTurn
    recap: str


class ResearchResult(BaseModel):
    op: Literal["research-this"] = "research-this"
    answer: str
    resume_question: str | None  # the announced return point (research-sidecar.md: "hand back")


class MetaCommandResult(BaseModel):
    op: Literal["meta-command"] = "meta-command"
    command: MetaCommand
    handled: bool
    note: str | None = None


class TangentResult(BaseModel):
    op: Literal["tangent"] = "tangent"
    spike_id: str


RespondResult = AnsweredTurn | ResearchResult | MetaCommandResult | TangentResult


class InterviewEngineNotConfigured(RuntimeError):
    """Raised when a call needs an LLM provider but none is configured."""


class InterviewEngine:
    """The turn-taking session over the four sub-steps, plus Mongo + Git persistence."""

    def __init__(
        self,
        store: WorkStateStore,
        content: GitContentStore,
        brain: GitBrain,
        provider: LLMProvider | None,
        *,
        lake: ContentLake | None = None,
        machine: PieceMachine | None = None,
        question_max_tokens: int = DEFAULT_QUESTION_MAX_TOKENS,
        classify_max_tokens: int = 200,
        research_max_tokens: int = DEFAULT_RESEARCH_MAX_TOKENS,
        recap_max_tokens: int = DEFAULT_RECAP_MAX_TOKENS,
        budget_factory: Callable[[], RunBudget] | None = None,
    ) -> None:
        self.store = store
        self.content = content
        self.brain = brain
        self.assembler = PromptAssembler(brain, content)
        self.provider = provider
        self.lake = lake
        self.machine = machine
        self._question_max_tokens = question_max_tokens
        self._classify_max_tokens = classify_max_tokens
        self._research_max_tokens = research_max_tokens
        self._recap_max_tokens = recap_max_tokens
        # Each interview turn gets a fresh per-run ceiling. Default is unbounded; production
        # wires a real cost/token ceiling here — the one sanctioned hard block (D14).
        self._budget_factory = budget_factory or RunBudget

    def _require_provider(self) -> LLMProvider:
        if self.provider is None:
            raise InterviewEngineNotConfigured(
                "no LLM provider is configured for the interview engine"
            )
        return self.provider

    # --- reads / session management --------------------------------------------------------

    async def get(self, interview_id: str) -> Interview:
        interview = await self.store.interviews.get(interview_id)
        if interview is None:
            raise InterviewNotFound(interview_id)
        return interview

    async def _piece_for(self, interview: Interview) -> Piece:
        piece = await self.store.pieces.get(interview.piece_id)
        if piece is None:
            raise KeyError(f"no piece {interview.piece_id!r} for interview {interview.id!r}")
        return piece

    async def open_interview(
        self,
        piece_id: str,
        *,
        interviewer_personas: list[str],
        assigned_expert: str | None = None,
        about: str | None = None,
        is_gap_interview: bool = False,
    ) -> Interview:
        """Open a new Interview session (initial or a council-spawned gap interview, §5-Q1).

        Personas run **serially** (§5a) in the given order; ``current_persona_index`` starts at 0.
        """
        known = set(self.brain.list_personas("interviewer"))
        for name in interviewer_personas:
            if name not in known:
                raise UnknownPersona(name)
        interview = Interview(
            piece_id=piece_id,
            interviewer_personas=list(interviewer_personas),
            assigned_expert=assigned_expert,
            about=about,
            is_gap_interview=is_gap_interview,
        )
        return await self.store.interviews.insert(interview)

    # --- 5a: next question -------------------------------------------------------------------

    async def next_question(
        self, interview_id: str, *, budget: RunBudget | None = None
    ) -> Interview:
        """Generate (Opus) and persist the next question for the active persona.

        Raises :class:`PendingQuestionError` if a question is already awaiting a response (one
        question per turn — never stack) and :class:`RosterExhausted` once every persona in the
        roster has been asked at least once.
        """
        provider = self._require_provider()
        interview = await self.get(interview_id)
        if InterviewStatus(interview.status) != InterviewStatus.open:
            raise IllegalInterviewOp(f"interview {interview_id!r} is not open")
        if interview.current_question:
            raise PendingQuestionError(
                "a question is already pending a response — answer it before asking the next one"
            )
        if interview.current_persona_index >= len(interview.interviewer_personas):
            raise RosterExhausted(interview_id)

        piece = await self._piece_for(interview)
        persona_name = interview.interviewer_personas[interview.current_persona_index]
        budget = budget or self._budget_factory()
        cost_before = budget.cost
        try:
            question = await ask_next_question(
                provider,
                self.assembler,
                piece_slug=piece.slug,
                voice_slug=piece.voice,  # exactly one active voice per piece (domain model §1.1)
                persona_name=persona_name,
                max_tokens=self._question_max_tokens,
                budget=budget,
            )
        finally:
            await self._charge(piece.id, budget, cost_before)
        updated = await self.store.interviews.update(interview_id, {"current_question": question})
        assert updated is not None
        return updated

    # --- roster navigation: skip / go-back, no classifier and no pending-question gate -------

    async def advance_persona(self, interview_id: str, direction: MetaCommand) -> MetaCommandResult:
        """Move the active persona forward (``skip``) or back (``go-back``) through the roster.

        Pure index arithmetic — the same math ``_route_meta_command`` applies below — with
        neither a classifier call nor ``respond``'s pending-question gate: unlike every other
        meta-command (add/drop-interviewer, restart, stop-for-the-day), roster navigation never
        needed the classifier's context, so a human shouldn't have to force a throwaway question
        into existence just to move past a persona they don't want to answer (Hendo, 2026-08-10).
        """
        if direction not in (MetaCommand.skip, MetaCommand.go_back):
            raise ValueError(f"advance_persona only accepts skip/go-back, got {direction!r}")
        interview = await self.get(interview_id)
        await self._apply_persona_navigation(interview, direction)
        return MetaCommandResult(command=direction, handled=True)

    async def _apply_persona_navigation(self, interview: Interview, direction: MetaCommand) -> None:
        if direction == MetaCommand.skip:
            new_index = min(interview.current_persona_index + 1, len(interview.interviewer_personas))
        else:
            new_index = max(interview.current_persona_index - 1, 0)
        await self.store.interviews.update(
            interview.id, {"current_persona_index": new_index, "current_question": None}
        )

    # --- 5b/D6: classify + route the interviewee's free-form input -------------------------

    async def respond(
        self, interview_id: str, text: str, *, budget: RunBudget | None = None
    ) -> RespondResult:
        provider = self._require_provider()
        interview = await self.get(interview_id)
        if not interview.current_question:
            raise NoPendingQuestionError("no pending question to respond to")
        piece = await self._piece_for(interview)
        active_persona = interview.interviewer_personas[interview.current_persona_index]

        budget = budget or self._budget_factory()
        cost_before = budget.cost
        try:
            classified = await classify_input(
                provider,
                text=text,
                active_piece=piece.slug,
                active_persona=active_persona,
                current_question=interview.current_question,
                max_tokens=self._classify_max_tokens,
                budget=budget,
            )
            if classified.op == InputOp.answer:
                return await self._route_answer(interview, piece, text, budget=budget)
            if classified.op == InputOp.research_this:
                return await self._route_research(interview, text, budget=budget)
            if classified.op == InputOp.meta_command:
                return await self._route_meta_command(interview, classified)
            return await self._route_tangent(interview, text)
        finally:
            await self._charge(piece.id, budget, cost_before)

    async def _route_answer(
        self, interview: Interview, piece: Piece, text: str, *, budget: RunBudget | None
    ) -> AnsweredTurn:
        provider = self._require_provider()
        persona = interview.interviewer_personas[interview.current_persona_index]
        assert interview.current_question is not None
        turn = append_turn(
            self.content, piece.slug, persona=persona, question=interview.current_question, answer=text
        )
        await self.store.interviews.update(interview.id, {"current_question": None})
        # A real, human-authored answer landed in the sacred transcript (D16b) — this is a human
        # touch on the piece (cmw-staleness-timestamps), independent of `_charge`'s cost-accounting
        # write below, which fires on LLM spend, not on the human act of answering.
        await self.store.pieces.mark_human_touch(piece.id)
        recap_text = await recap_answer(
            provider,
            question=turn.question,
            answer=turn.answer,
            max_tokens=self._recap_max_tokens,
            budget=budget,
        )
        return AnsweredTurn(turn=turn, recap=recap_text)

    async def _route_research(
        self, interview: Interview, text: str, *, budget: RunBudget | None
    ) -> ResearchResult:
        provider = self._require_provider()
        # Borrowed time, then returned: the pending question is untouched (research-sidecar.md).
        # research_sidecar() itself degrades a missing/misconfigured ANTHROPIC_API_KEY to a
        # friendly string rather than raising (F5, research.py's own carve-out resolution) —
        # nothing to catch here.
        answer = await research_sidecar(
            provider,
            self.assembler,
            query=text,
            lake=self.lake,
            max_tokens=self._research_max_tokens,
            budget=budget,
        )
        return ResearchResult(answer=answer, resume_question=interview.current_question)

    async def _route_meta_command(
        self, interview: Interview, classified: ClassifiedInput
    ) -> MetaCommandResult:
        command = classified.meta_command or MetaCommand.other
        if command not in _ENACTED_META_COMMANDS:
            # switch-piece / other: recorded, not enacted (out of this piece-scoped engine's
            # remit) — never a silent no-op (D6).
            return MetaCommandResult(command=command, handled=False, note=classified.note)

        if command in (MetaCommand.skip, MetaCommand.go_back):
            # Same index math `advance_persona` above exposes directly, with no classifier call.
            await self._apply_persona_navigation(interview, command)
            return MetaCommandResult(command=command, handled=True)

        if command == MetaCommand.add_interviewer:
            name = (classified.note or "").strip().lower()
            known = set(self.brain.list_personas("interviewer"))
            if not name or name not in known:
                return MetaCommandResult(command=command, handled=False, note=classified.note)
            if name not in interview.interviewer_personas:
                personas = [*interview.interviewer_personas, name]
                await self.store.interviews.update(interview.id, {"interviewer_personas": personas})
            return MetaCommandResult(command=command, handled=True, note=name)

        if command == MetaCommand.drop_interviewer:
            name = (classified.note or "").strip().lower()
            if name not in interview.interviewer_personas:
                return MetaCommandResult(command=command, handled=False, note=classified.note)
            personas = [p for p in interview.interviewer_personas if p != name]
            new_index = min(interview.current_persona_index, len(personas))
            await self.store.interviews.update(
                interview.id,
                {
                    "interviewer_personas": personas,
                    "current_persona_index": new_index,
                    "current_question": None,
                },
            )
            return MetaCommandResult(command=command, handled=True, note=name)

        if command == MetaCommand.restart:
            await self.store.interviews.update(
                interview.id, {"current_persona_index": 0, "current_question": None}
            )
            return MetaCommandResult(command=command, handled=True)

        # stop-for-the-day: delegates to the piece machine's pause (interviewing → paused, D6).
        if self.machine is None:
            return MetaCommandResult(
                command=command, handled=False, note="no piece machine configured"
            )
        await self.machine.pause(interview.piece_id)
        return MetaCommandResult(command=command, handled=True)

    async def _route_tangent(self, interview: Interview, text: str) -> TangentResult:
        # A parked tangent is a Spike with origin.kind=tangent, null convergence score — one pool,
        # one Vault filter model (domain model §5-Q2) — never simply discarded.
        spike = Spike(
            headline=text.strip()[:120],
            status=SpikeStatus.vaulted,
            creator=interview.assigned_expert or "unknown",
            origin=SpikeOrigin(kind=SpikeOriginKind.tangent),
        )
        stored = await self.store.spikes.insert(spike)
        assert stored.id is not None
        return TangentResult(spike_id=stored.id)

    # --- mark-complete: a signal only (D16a) -------------------------------------------------

    async def mark_complete(self, interview_id: str) -> Interview:
        """Flip ``Interview.status`` to complete — a *signal* for a coordinator, never the draft
        trigger. Only ``PieceMachine.enough_input`` (a separate, human-driven call) advances the
        piece to drafting."""
        await self.get(interview_id)  # 404s cleanly if missing
        updated = await self.store.interviews.update(
            interview_id, {"status": InterviewStatus.complete.value}
        )
        assert updated is not None
        return updated

    # --- the sacred transcript: read + interviewee edit (D16b) ------------------------------

    async def transcript(self, piece_id: str) -> str:
        piece = await self._get_piece(piece_id)
        return read_transcript(self.content, piece.slug)

    async def edit_answer(
        self, piece_id: str, turn_id: str, new_answer: str, *, interview_id: str
    ) -> TranscriptTurn:
        """Splice the interviewee's edit into the transcript (D16b) — refused once the named
        interview is complete (the surface reached must itself still be open; a still-open sibling
        interview on the same piece does not reopen a *different*, completed interview's surface).
        """
        piece = await self._get_piece(piece_id)
        interview = await self.get(interview_id)
        if interview.piece_id != piece_id:
            raise InterviewNotFound(interview_id)
        if InterviewStatus(interview.status) != InterviewStatus.open:
            raise IllegalInterviewOp(
                f"interview {interview_id!r} is complete — its transcript is read-only"
            )
        try:
            turn = edit_answer(self.content, piece.slug, turn_id, new_answer)
        except KeyError as exc:
            raise UnknownTurn(turn_id) from exc
        # The interviewee editing their own answer is a human touch (cmw-staleness-timestamps),
        # same as answering fresh — see `_route_answer`'s identical stamp above.
        await self.store.pieces.mark_human_touch(piece_id)
        return turn

    async def recap_turn(
        self, piece_id: str, turn_id: str, *, budget: RunBudget | None = None
    ) -> str:
        """Regenerate the recap for an already-stored (possibly just-edited) turn."""
        provider = self._require_provider()
        piece = await self._get_piece(piece_id)
        text = read_transcript(self.content, piece.slug)
        turn = next((t for t in parse_turns(text) if t.id == turn_id), None)
        if turn is None:
            raise UnknownTurn(turn_id)
        budget = budget or self._budget_factory()
        cost_before = budget.cost
        try:
            return await recap_answer(
                provider,
                question=turn.question,
                answer=turn.answer,
                max_tokens=self._recap_max_tokens,
                budget=budget,
            )
        finally:
            await self._charge(piece.id, budget, cost_before)

    # --- cost accounting: every direct provider call this engine makes lands on the piece ---

    async def _charge(self, piece_id: str, budget: RunBudget, cost_before: float) -> None:
        """Cost tracking removed (flaky and doesn't matter). No-op."""
        pass

    async def _get_piece(self, piece_id: str) -> Piece:
        piece = await self.store.pieces.get(piece_id)
        if piece is None:
            raise KeyError(f"no piece {piece_id!r}")
        return piece
