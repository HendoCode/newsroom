"""HTTP surface for the lessons loop (D12; domain model §1.18).

Thin wrappers over :class:`~app.lessons.service.LessonsService` so the piece's ``lessons`` stage
(§1.9) is reachable at the service's REST boundary. This is the loop's API seam only — the
voice-kit UI that reviews accepted lessons is a separate, downstream ticket.

- ``POST /api/lessons/{piece_id}/propose`` — diff + Opus call; persists PENDING proposals to Mongo.
- ``GET /api/lessons/pending`` / ``GET /api/lessons/{piece_id}`` — read seams for that future UI.
- ``POST /api/lessons/{lesson_id}/accept`` / ``/reject`` — the D12 human gate. Only ``accept``
  reaches Git (via the service, which is the only place ``commit_accepted_lesson`` is called from
  a human-triggered path — the machine never self-commits).

Mirrors the other route modules' 503-when-unconfigured guard (no Mongo / no Git brain / no
content store attached to ``app.state``).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.git.brain import GitBrain
from app.git.content import GitContentStore
from app.lessons.errors import LessonNotPending, LessonsParseError, NotInLessonsStage
from app.lessons.service import LessonsService
from app.llm.provider import LLMProvider
from app.models import Lesson
from app.repositories import WorkStateStore
from app.schemas import (
    LessonBatchError,
    LessonBatchRequest,
    LessonBatchResponse,
    LessonDecisionRequest,
    LessonOut,
    LessonPreviewOut,
    ProposeLessonsRequest,
    ProposeLessonsResponse,
)

router = APIRouter(prefix="/api/lessons", tags=["lessons"])


def _lesson_out(lesson: Lesson) -> LessonOut:
    assert lesson.id is not None
    return LessonOut(
        id=lesson.id,
        voice=lesson.voice,
        source_piece_id=lesson.source_piece_id,
        observed_change=lesson.observed_change,
        generalizable_rule=lesson.generalizable_rule,
        status=str(lesson.status),
    )


def _require(request: Request) -> tuple[WorkStateStore, GitBrain, GitContentStore]:
    store = getattr(request.app.state, "work_state", None)
    brain = getattr(request.app.state, "git_brain", None)
    content = getattr(request.app.state, "git_content", None)
    if store is None or brain is None or content is None:
        raise HTTPException(
            status_code=503,
            detail="lessons unavailable (MONGO_URL / brain_root not configured)",
        )
    return store, brain, content


Deps = Annotated[tuple[WorkStateStore, GitBrain, GitContentStore], Depends(_require)]


def _service(deps: tuple[WorkStateStore, GitBrain, GitContentStore], request: Request) -> LessonsService:
    store, brain, content = deps
    provider: LLMProvider | None = getattr(request.app.state, "llm_provider", None)
    budget_factory = getattr(request.app.state, "budget_factory", None)
    return LessonsService(store, brain, content, provider, budget_factory=budget_factory)


@router.post("/{piece_id}/propose", response_model=ProposeLessonsResponse)
async def propose(
    piece_id: str, req: ProposeLessonsRequest, deps: Deps, request: Request
) -> ProposeLessonsResponse:
    """Diff the final draft vs ``published_content`` and propose deduped lessons (Opus tier)."""
    service = _service(deps, request)
    if service.provider is None:
        raise HTTPException(status_code=503, detail="lessons unavailable (LLM provider not configured)")
    try:
        proposed = await service.propose(piece_id, published_content=req.published_content)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotInLessonsStage as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LessonsParseError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ProposeLessonsResponse(proposed=[_lesson_out(lesson) for lesson in proposed])


@router.post("/batch", response_model=LessonBatchResponse)
async def decide_batch(req: LessonBatchRequest, deps: Deps, request: Request) -> LessonBatchResponse:
    """Accept or reject several pending lessons (voice-kit batch review). Partial success."""
    service = _service(deps, request)
    decided, errors = await service.decide_batch(
        req.lesson_ids,
        action=req.action,
        rule_texts=req.rule_texts,
        actor=req.actor,
    )
    return LessonBatchResponse(
        decided=[_lesson_out(lesson) for lesson in decided],
        errors=[LessonBatchError(id=lid, error=msg) for lid, msg in errors],
    )


@router.get("/pending", response_model=list[LessonOut])
async def list_pending(deps: Deps, voice: str | None = None) -> list[LessonOut]:
    """Pending proposals awaiting the D12 gate, optionally narrowed to one voice."""
    store, _, _ = deps
    lessons = await store.lessons.proposed()
    if voice is not None:
        lessons = [lesson for lesson in lessons if lesson.voice == voice]
    return [_lesson_out(lesson) for lesson in lessons]


@router.get("/{piece_id}", response_model=list[LessonOut])
async def list_for_piece(piece_id: str, deps: Deps) -> list[LessonOut]:
    """Every Lesson (any status) sourced from one piece."""
    store, _, _ = deps
    lessons = await store.lessons.by_piece(piece_id)
    return [_lesson_out(lesson) for lesson in lessons]


@router.get("/{lesson_id}/preview", response_model=LessonPreviewOut)
async def preview(
    lesson_id: str, deps: Deps, request: Request, rule_text: str | None = None
) -> LessonPreviewOut:
    """Git diff of the rule about to land in ``content-lessons.md``. Does not write."""
    service = _service(deps, request)
    try:
        lesson, path, before, after, final_rule = await service.preview(
            lesson_id, rule_text=rule_text
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LessonNotPending as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    assert lesson.id is not None
    return LessonPreviewOut(
        lesson_id=lesson.id,
        path=path,
        before=before,
        after=after,
        rule_text=final_rule,
    )


@router.post("/{lesson_id}/accept", response_model=LessonOut)
async def accept(lesson_id: str, req: LessonDecisionRequest, deps: Deps, request: Request) -> LessonOut:
    """The D12 accept gate: commits the (optionally edited) rule to Git, flips Mongo to accepted."""
    service = _service(deps, request)
    try:
        lesson = await service.accept(lesson_id, rule_text=req.rule_text, actor=req.actor)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LessonNotPending as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _lesson_out(lesson)


@router.post("/{lesson_id}/reject", response_model=LessonOut)
async def reject(lesson_id: str, req: LessonDecisionRequest, deps: Deps, request: Request) -> LessonOut:
    """The D12 reject gate: marks the proposal rejected. Never touches Git."""
    service = _service(deps, request)
    try:
        lesson = await service.reject(lesson_id, actor=req.actor)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LessonNotPending as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _lesson_out(lesson)
