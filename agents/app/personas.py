"""Read-only Git-brain persona listing (§1.2) — for UI selects.

A thin GET so screens that need "which personas exist" (the kickoff screen's interviewer picker,
wireframe screen 6 step 4; the Oracle-run-adjacent selects) read the real brain instead of
hardcoding a list that would silently drift from it. No writes here — Persona *content* edits
stay in their existing owning tickets.

Distinct from `agents/app/voices.py`'s `GET /api/voices`, which already covers voice-slug
listing as part of its full view/edit/rollback CRUD (D12, screen 11) — this module doesn't
duplicate that. Also distinct from `agents/app/interview/routes.py`'s
`GET /api/personas/interviewers` (hard-coded to the interviewer kind, bare `list[str]`, for the
interview surface's persona menu) — this one is generic over kind (`interviewer` | `editor`) for
the spike-kickoff and narrative-run screens' selects.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.git.brain import GitBrain
from app.schemas import PersonaListResponse

router = APIRouter(prefix="/api", tags=["personas"])


def _require_brain(request: Request) -> GitBrain:
    brain = getattr(request.app.state, "git_brain", None)
    if brain is None:
        raise HTTPException(
            status_code=503, detail="brain unavailable (brain_root is not a git repo)"
        )
    return brain


@router.get("/personas", response_model=PersonaListResponse)
async def list_personas(request: Request, kind: str = "interviewer") -> PersonaListResponse:
    brain = _require_brain(request)
    try:
        names = brain.list_personas(kind)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PersonaListResponse(kind=kind, personas=names)
