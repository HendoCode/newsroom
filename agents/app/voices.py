"""Voice kit (screen 11 / D12; domain model §1.1): view, edit, and roll back Git-backed voice
packs.

REST surface over ``app.git.brain.GitBrain``'s voice-pack read/write/history/rollback methods —
the counterpart to ``app/lessons/routes.py``, which owns the *proposed-lessons* gate (Mongo
proposal -> accepted commit). This module owns direct human edits to any pack file
(``voice-guide.md`` / ``style-guide.md`` / ``content-lessons.md``, plus ``visual-identity.md`` /
``brand-guidelines.md`` for demo-dana) — commit, diff-by-version, history, and rollback.
Never reimplements Git: every operation is a thin call onto ``GitBrain``, which itself calls
``GitRepo`` plumbing.

D12: any employee may edit any voice; this is a **flat**, ungated surface (the non-blocking
"courtesy note" for editing someone else's kit is a `web/` UI concern, not a server check). Needs
no Mongo — ``app.state.git_brain`` is attached independent of ``MONGO_URL`` (see ``main.py``), so
these routes 503 only when ``brain_root`` isn't a git repo at all.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.git.brain import GitBrain
from app.schemas import (
    VoiceCommitOut,
    VoiceFileContentResponse,
    VoiceFileHistoryResponse,
    VoiceFileKey,
    VoiceFileRollbackRequest,
    VoiceFileUpdateRequest,
    VoiceListResponse,
    VoicePackOut,
)

router = APIRouter(prefix="/api/voices", tags=["voices"])


def _require_brain(request: Request) -> GitBrain:
    brain = getattr(request.app.state, "git_brain", None)
    if brain is None:
        raise HTTPException(status_code=503, detail="voice kit unavailable (brain_root not configured)")
    return brain


def _require_voice(brain: GitBrain, slug: str) -> None:
    if slug not in brain.list_voices():
        raise HTTPException(status_code=404, detail=f"no voice {slug!r}")


@router.get("", response_model=VoiceListResponse)
async def list_voices(request: Request) -> VoiceListResponse:
    brain = _require_brain(request)
    return VoiceListResponse(voices=brain.list_voices())


@router.get("/{slug}", response_model=VoicePackOut)
async def get_voice_pack(slug: str, request: Request) -> VoicePackOut:
    brain = _require_brain(request)
    _require_voice(brain, slug)
    pack = brain.read_voice(slug)
    return VoicePackOut(**pack.model_dump())


@router.get("/{slug}/files/{file_key}/history", response_model=VoiceFileHistoryResponse)
async def get_voice_file_history(slug: str, file_key: VoiceFileKey, request: Request) -> VoiceFileHistoryResponse:
    brain = _require_brain(request)
    _require_voice(brain, slug)
    commits = brain.voice_file_history(slug, file_key)
    return VoiceFileHistoryResponse(
        commits=[
            VoiceCommitOut(sha=c.sha, author_name=c.author_name, author_email=c.author_email, date=c.date, message=c.message)
            for c in commits
        ]
    )


@router.get("/{slug}/files/{file_key}/at/{sha}", response_model=VoiceFileContentResponse)
async def get_voice_file_at(slug: str, file_key: VoiceFileKey, sha: str, request: Request) -> VoiceFileContentResponse:
    brain = _require_brain(request)
    _require_voice(brain, slug)
    try:
        content = brain.read_voice_file_at(slug, file_key, sha)
    except Exception as exc:  # git plumbing failure (bad sha / file absent at that sha)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return VoiceFileContentResponse(content=content)


@router.put("/{slug}/files/{file_key}", response_model=VoiceCommitOut)
async def update_voice_file(
    slug: str, file_key: VoiceFileKey, req: VoiceFileUpdateRequest, request: Request
) -> VoiceCommitOut:
    """Edit + commit one voice-pack file (D12: a human edit; the machine never self-commits)."""
    brain = _require_brain(request)
    _require_voice(brain, slug)
    try:
        sha = brain.write_voice_file(
            slug,
            file_key,
            req.content,
            message=req.message,
            author_name=req.actor_name,
            author_email=req.actor,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    commit = brain.voice_file_history(slug, file_key, max_count=1)[0]
    return VoiceCommitOut(
        sha=sha, author_name=commit.author_name, author_email=commit.author_email,
        date=commit.date, message=commit.message,
    )


@router.post("/{slug}/files/{file_key}/rollback", response_model=VoiceCommitOut)
async def rollback_voice_file(
    slug: str, file_key: VoiceFileKey, req: VoiceFileRollbackRequest, request: Request
) -> VoiceCommitOut:
    """Roll a voice-pack file back to an earlier Git revision (a new, attributable forward commit —
    history-preserving, same discipline as a piece Revision rollback)."""
    brain = _require_brain(request)
    _require_voice(brain, slug)
    try:
        sha = brain.rollback_voice_file(
            slug, file_key, req.sha, message=req.message, author_name=req.actor_name, author_email=req.actor
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    commit = brain.voice_file_history(slug, file_key, max_count=1)[0]
    return VoiceCommitOut(
        sha=sha, author_name=commit.author_name, author_email=commit.author_email,
        date=commit.date, message=commit.message,
    )
