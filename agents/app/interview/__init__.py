"""The interview engine (D5-context-assembly §5; domain model §1.12) — the interactive,
multi-turn extraction step.

Serial interviewer personas generate one question at a time (Opus 4.8, :mod:`.question`); the
interviewee's free-form input is classified into the D6 bounded op set (Sonnet 5,
:mod:`.classify`) and routed; a research sidecar (Sonnet 5 + web_search, :mod:`.research`) is
available mid-turn; a "here's what I heard" recap (Sonnet 5, :mod:`.recap`) is a read-only
confirmation view. :mod:`.transcript` owns the sacred, verbatim, interviewee-editable transcript
in Git. :class:`.engine.InterviewEngine` composes all of it plus Mongo/Git persistence and D6
routing; :mod:`.routes` is the REST seam.

Each turn is a stateless call — continuity comes entirely from re-hydrating the growing
transcript (Git) and the interview's metadata (Mongo), never from model memory.
"""

from __future__ import annotations

from app.interview.classify import (
    ClassificationParseError,
    ClassifiedInput,
    InputOp,
    MetaCommand,
    classify_input,
)
from app.interview.engine import (
    AnsweredTurn,
    IllegalInterviewOp,
    InterviewEngine,
    InterviewNotFound,
    MetaCommandResult,
    NoPendingQuestionError,
    PendingQuestionError,
    ResearchResult,
    RespondResult,
    RosterExhausted,
    TangentResult,
    UnknownPersona,
    UnknownTurn,
)
from app.interview.question import ask_next_question
from app.interview.recap import recap_answer
from app.interview.research import WEB_SEARCH_TOOL, research
from app.interview.transcript import (
    TranscriptTurn,
    append_turn,
    edit_answer,
    parse_turns,
    read_transcript,
)

__all__ = [
    "WEB_SEARCH_TOOL",
    "AnsweredTurn",
    "ClassificationParseError",
    "ClassifiedInput",
    "IllegalInterviewOp",
    "InputOp",
    "InterviewEngine",
    "InterviewNotFound",
    "MetaCommand",
    "MetaCommandResult",
    "NoPendingQuestionError",
    "PendingQuestionError",
    "ResearchResult",
    "RespondResult",
    "RosterExhausted",
    "TangentResult",
    "TranscriptTurn",
    "UnknownPersona",
    "UnknownTurn",
    "append_turn",
    "ask_next_question",
    "classify_input",
    "edit_answer",
    "parse_turns",
    "read_transcript",
    "recap_answer",
    "research",
]
