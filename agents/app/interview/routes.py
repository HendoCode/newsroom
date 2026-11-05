"""HTTP surface for the interview engine (D5) — the engine's API seam, not the screen.

Thin wrappers over :class:`~app.interview.engine.InterviewEngine` so a future interview UI
(a separate ticket) has a REST seam to build against. Error mapping mirrors
``app.orchestration.routes``: unknown interview/piece/turn → 404, an illegal op for the current
state → 409, an unknown persona name → 422, engine not configured → 503.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.interview.classify import MetaCommand
from app.interview.engine import (
    IllegalInterviewOp,
    InterviewEngine,
    InterviewEngineNotConfigured,
    InterviewNotFound,
    MetaCommandResult,
    RespondResult,
    UnknownPersona,
    UnknownTurn,
)
from app.interview.transcript import TranscriptTurn, parse_turns
from app.models import Interview

router = APIRouter(tags=["interview"])


def get_engine(request: Request) -> InterviewEngine:
    engine = getattr(request.app.state, "interview_engine", None)
    if engine is None:
        raise HTTPException(
            status_code=503, detail="interview engine unavailable (MONGO_URL not configured)"
        )
    return engine


EngineDep = Annotated[InterviewEngine, Depends(get_engine)]


class InterviewOut(BaseModel):
    """The wire shape of an :class:`~app.models.Interview` — its full turn-taking state."""

    id: str
    piece_id: str
    status: str
    interviewer_personas: list[str]
    current_persona_index: int
    current_question: str | None
    assigned_expert: str | None
    about: str | None
    is_gap_interview: bool


def _out(interview: Interview) -> InterviewOut:
    assert interview.id is not None
    return InterviewOut(
        id=interview.id,
        piece_id=interview.piece_id,
        status=str(interview.status),
        interviewer_personas=interview.interviewer_personas,
        current_persona_index=interview.current_persona_index,
        current_question=interview.current_question,
        assigned_expert=interview.assigned_expert,
        about=interview.about,
        is_gap_interview=interview.is_gap_interview,
    )


class OpenInterviewRequest(BaseModel):
    interviewer_personas: list[str] = Field(min_length=1)
    assigned_expert: str | None = None
    about: str | None = None
    is_gap_interview: bool = False


class RespondRequest(BaseModel):
    text: str


class AdvancePersonaRequest(BaseModel):
    direction: Literal["skip", "go-back"]


class EditAnswerRequest(BaseModel):
    text: str
    interview_id: str


class RecapOut(BaseModel):
    recap: str


class TranscriptOut(BaseModel):
    piece_id: str
    transcript_md: str


async def _run(coro) -> InterviewOut:
    try:
        interview = await coro
    except InterviewNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IllegalInterviewOp as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InterviewEngineNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _out(interview)


@router.post("/api/pieces/{piece_id}/interviews", response_model=InterviewOut)
async def open_interview(
    piece_id: str, body: OpenInterviewRequest, engine: EngineDep, request: Request
) -> InterviewOut:
    """Open a new Interview session on ``piece_id`` (initial or a council-spawned gap interview).

    Research gate (research-v1): a piece that belongs to a ContentProject cannot open its
    extraction interview until that project's research requirement is satisfied — a current
    research report OR a recorded experiential waiver. Gap interviews (opened mid-pipeline,
    after this gate has necessarily already been passed) are exempt.
    """
    if not body.is_gap_interview:
        await _enforce_research_gate(request, engine, piece_id)
    try:
        interview = await engine.open_interview(
            piece_id,
            interviewer_personas=body.interviewer_personas,
            assigned_expert=body.assigned_expert,
            about=body.about,
            is_gap_interview=body.is_gap_interview,
        )
    except UnknownPersona as exc:
        raise HTTPException(status_code=422, detail=f"unknown interviewer persona: {exc}") from exc
    return _out(interview)


async def _enforce_research_gate(request: Request, engine: InterviewEngine, piece_id: str) -> None:
    """409 when the piece's project still needs a research report (or a recorded waiver).

    Degrades open, never closed: a piece with no ContentProject (the legacy pick-spike path),
    an unconfigured workflow, or a lookup failure never blocks an interview — the research
    requirement only exists for pieces created through the content workflow.
    """
    workflow = getattr(request.app.state, "content_workflow", None)
    if workflow is None:
        return
    piece = await engine.store.pieces.get(piece_id)
    if piece is None or not piece.content_project_id:
        return
    from app.content_workflow.workflow import ProjectNotFound

    try:
        gate = await workflow.research_gate(piece.content_project_id)
    except ProjectNotFound:
        return
    if gate.required and not gate.satisfied:
        raise HTTPException(
            status_code=409,
            detail=(
                "This piece's project needs a sourced research report \u2014 or a recorded "
                "experiential waiver \u2014 before interviews can open. Add one on the project "
                "page."
            ),
        )


@router.get("/api/interviews/{interview_id}", response_model=InterviewOut)
async def get_interview(interview_id: str, engine: EngineDep) -> InterviewOut:
    return await _run(engine.get(interview_id))


@router.post("/api/interviews/{interview_id}/next-question", response_model=InterviewOut)
async def next_question(interview_id: str, engine: EngineDep) -> InterviewOut:
    """Generate (Opus) and persist the active persona's next question (§5a)."""
    return await _run(engine.next_question(interview_id))


@router.post("/api/interviews/{interview_id}/respond")
async def respond(interview_id: str, body: RespondRequest, engine: EngineDep) -> RespondResult:
    """Classify (Sonnet, D6) and route the interviewee's free-form input to the current question."""
    try:
        return await engine.respond(interview_id, body.text)
    except InterviewNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IllegalInterviewOp as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InterviewEngineNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/api/interviews/{interview_id}/advance-persona")
async def advance_persona(
    interview_id: str, body: AdvancePersonaRequest, engine: EngineDep
) -> MetaCommandResult:
    """Move the active persona forward/back through the roster with no classifier call and no
    pending-question gate (unlike ``respond``) — roster navigation never needed either."""
    try:
        return await engine.advance_persona(interview_id, MetaCommand(body.direction))
    except InterviewNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InterviewEngineNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/api/interviews/{interview_id}/mark-complete", response_model=InterviewOut)
async def mark_complete(interview_id: str, engine: EngineDep) -> InterviewOut:
    """Flip the interview to complete — a signal, never the draft trigger (D16a)."""
    return await _run(engine.mark_complete(interview_id))


@router.get("/api/pieces/{piece_id}/transcript", response_model=TranscriptOut)
async def get_transcript(piece_id: str, engine: EngineDep) -> TranscriptOut:
    try:
        text = await engine.transcript(piece_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TranscriptOut(piece_id=piece_id, transcript_md=text)


@router.get("/api/pieces/{piece_id}/transcript/turns", response_model=list[TranscriptTurn])
async def list_transcript_turns(piece_id: str, engine: EngineDep) -> list[TranscriptTurn]:
    """The sacred transcript (§1.12/D16b), pre-parsed into turns for a UI to render directly —
    reuses :func:`~app.interview.transcript.parse_turns` rather than making callers re-parse the
    raw markdown anchor format themselves."""
    try:
        text = await engine.transcript(piece_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return parse_turns(text)


@router.get("/api/personas/interviewers", response_model=list[str])
async def list_interviewer_personas(engine: EngineDep) -> list[str]:
    """The full interviewer roster (§1.2) — e.g. for a persona menu to show which of the ~10 are
    on a given interview's pre-selected fitting set versus not yet added (D6 add/drop-interviewer)."""
    return engine.brain.list_personas("interviewer")


@router.post(
    "/api/pieces/{piece_id}/transcript/turns/{turn_id}", response_model=TranscriptTurn
)
async def edit_answer(
    piece_id: str, turn_id: str, body: EditAnswerRequest, engine: EngineDep
) -> TranscriptTurn:
    """The interviewee's own edit of a previously stored answer (D16b) — refused once
    ``body.interview_id`` names a completed interview (the transcript becomes read-only)."""
    try:
        return await engine.edit_answer(
            piece_id, turn_id, body.text, interview_id=body.interview_id
        )
    except InterviewNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IllegalInterviewOp as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UnknownTurn as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InterviewEngineNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/api/pieces/{piece_id}/transcript/turns/{turn_id}/recap", response_model=RecapOut
)
async def recap_turn(piece_id: str, turn_id: str, engine: EngineDep) -> RecapOut:
    """Regenerate the "here's what I heard" recap over a (possibly just-edited) stored turn."""
    try:
        text = await engine.recap_turn(piece_id, turn_id)
    except UnknownTurn as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InterviewEngineNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return RecapOut(recap=text)


__all__ = ["router"]
