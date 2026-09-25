"""Interview metadata (domain model §1.12).

An interactive extraction *session* on a Piece. The **Transcript** content is the sacred source
and lives in Git (``drafts/<slug>/transcript.md``); this Mongo record holds only the session
*metadata* — assignment, selected interviewer personas, status, and the SSO-gated expert deep
link (D3/D10).

Per §5-Q1 the Transcript is **piece-scoped** (one accumulated `transcript.md` per piece);
many Interview sessions — the initial one plus council-spawned targeted **gap interviews** —
append attributed turns to that one transcript. So Interview is piece-scoped here, and
``is_gap_interview`` marks the council-triggered re-openings.

Invariant: marking complete is a **signal**, not the draft trigger (D16a); interviewers are
voice-neutral (§1.2).

``current_persona_index`` / ``current_question`` are the interview *engine's* per-turn
continuity state (D5-context-assembly §5a/§5b): which of ``interviewer_personas`` is asking now,
and the question awaiting an interviewee response. Both are plain Mongo fields — the sacred
answer text itself never lives here, only in the Git transcript (D16b).
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from app.models.common import MongoModel


class InterviewStatus(str, Enum):
    open = "open"
    complete = "complete"


class Interview(MongoModel):
    piece_id: str
    assigned_expert: str | None = None  # User (email/id)
    interviewer_personas: list[str] = Field(default_factory=list)  # 2–4 persona names
    status: InterviewStatus = InterviewStatus.open
    about: str | None = None  # the "who/what" signal
    expert_link: str | None = None  # SSO-gated deep link (D10) — not a magic link
    is_gap_interview: bool = False  # a council-spawned targeted gap interview
    current_persona_index: int = 0  # which interviewer_personas entry is asking now
    current_question: str | None = None  # the question awaiting an interviewee response
