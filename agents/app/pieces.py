"""Piece visibility REST surface — orthogonal to the stage machine.

Two concerns live here, both about *seeing* pieces rather than transitioning them:

- ``POST /api/pieces/{id}/archive`` / ``.../unarchive`` — triage at scale. Deliberately NOT
  routed through ``PieceMachine``/``orchestration/routes.py``: archiving is a dashboard-visibility
  flag, not a stage
  transition (``Piece.archived_at`` is not a ``PieceStage`` value and never touches
  ``ALLOWED_TRANSITIONS``), so it must work regardless of the piece's current stage — including the
  terminal ``published`` stage. It changes nothing else about the piece: no job is stopped, no
  permission changes, no asset is touched or deleted, and it is always reversible (unarchive), per
  this project's "never delete anything" principle. See ``app.dashboard.build_queue`` for the one
  place an archived piece is actually hidden (the dashboard queue) — direct access via
  ``GET /api/pieces/{id}`` is unaffected either way.
- ``GET /api/pieces/recent`` — the desk's "~6 most recently active pieces" projection, live from
  the Mongo work-state with NO seed fallback (see its section below).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request

from app.models.piece import Piece
from app.repositories import WorkStateStore
from app.schemas import PieceArchiveResponse, RecentPiece, RecentPiecesResponse, PieceTitleUpdateRequest, PieceTitleUpdateResponse

router = APIRouter(prefix="/api/pieces", tags=["pieces"])

# Sort floor for a piece with no timestamps at all (seed-era docs); sorts below anything dated.
_DATETIME_FLOOR = datetime.min


def _require_store(request: Request) -> WorkStateStore:
    store = getattr(request.app.state, "work_state", None)
    if store is None:
        raise HTTPException(
            status_code=503, detail="archive unavailable (MONGO_URL not configured)"
        )
    return store


def _to_out(piece: Piece) -> PieceArchiveResponse:
    assert piece.id is not None
    return PieceArchiveResponse(id=piece.id, slug=piece.slug, archived_at=piece.archived_at)


# --- Recent pieces: the desk's "what was touched lately" visibility strip -----------------------
#
# The Operator Desk needs the ~6 most recently created/active pieces, live from the work-state —
# never a hardcoded/seed list (that is exactly the thing this projection replaces). Sorted by
# `updated_at` (the machine signal — every write bumps it; see the cmw-staleness-timestamps
# entries), which covers "recently created" too since insert sets both timestamps. Archived pieces
# are hidden here for the SAME reason `build_queue` hides them (triage-at-scale): a piece a human
# archived out of the queue should not re-surface on the desk. Unlike `/api/dashboard` there is no
# seed fallback: unconfigured/empty Mongo returns an honest empty list (`source: "none"`).


@router.get("/recent", response_model=RecentPiecesResponse)
async def recent_pieces(
    request: Request,
    limit: int = Query(default=6, ge=1, le=20),
) -> RecentPiecesResponse:
    """The ~N most recently active non-archived pieces, newest activity first.

    `limit` defaults to 6 (the desk's strip), clamped to 1..20 by FastAPI validation (a
    non-positive or oversized limit is a 422, not a silent re-clamp). When Mongo is not
    configured this returns an empty list with `source: "none"` rather than 503 — the desk card
    degrades to its honest empty state, same posture as `/api/content-workflow/desk`.
    """
    store: WorkStateStore | None = getattr(request.app.state, "work_state", None)
    if store is None:
        return RecentPiecesResponse(source="none", items=[])
    pieces = await store.pieces.find({})
    active = [p for p in pieces if p.archived_at is None]
    active.sort(
        key=lambda p: p.updated_at or p.created_at or p.last_human_touch_at or _DATETIME_FLOOR,
        reverse=True,
    )
    items = [
        RecentPiece(
            id=p.id or "",
            title=p.title,
            slug=p.slug,
            stage=p.stage if isinstance(p.stage, str) else p.stage.value,
            voice=p.voice,
            owner=p.owner,
            created_at=p.created_at,
            updated_at=p.updated_at,
            last_human_touch_at=p.last_human_touch_at,
        )
        for p in active[:limit]
    ]
    return RecentPiecesResponse(source="store", items=items)


@router.post("/{piece_id}/archive", response_model=PieceArchiveResponse)
async def archive_piece(piece_id: str, request: Request) -> PieceArchiveResponse:
    """Hide a piece from the dashboard queue, regardless of its current stage."""
    store = _require_store(request)
    try:
        piece = await store.pieces.archive(piece_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_out(piece)


@router.post("/{piece_id}/unarchive", response_model=PieceArchiveResponse)
async def unarchive_piece(piece_id: str, request: Request) -> PieceArchiveResponse:
    """Reverse :func:`archive_piece` — restores the piece to the dashboard queue."""
    store = _require_store(request)
    try:
        piece = await store.pieces.unarchive(piece_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_out(piece)


def _to_title_out(piece: Piece) -> PieceTitleUpdateResponse:
    assert piece.id is not None
    return PieceTitleUpdateResponse(
        id=piece.id,
        slug=piece.slug,
        title=piece.title,
        updated_at=piece.updated_at,
    )


@router.post("/{piece_id}/title", response_model=PieceTitleUpdateResponse)
async def update_piece_title(
    piece_id: str, request: Request, body: PieceTitleUpdateRequest
) -> PieceTitleUpdateResponse:
    """Update a piece's title (dashboard rename)."""
    store = _require_store(request)
    existing = await store.pieces.get(piece_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"piece {piece_id!r} not found")
    piece = await store.pieces.update(piece_id, {"title": body.title})
    # piece should not be None because we just found it, but guard anyway
    if piece is None:
        raise HTTPException(status_code=404, detail=f"piece {piece_id!r} disappeared")
    return _to_title_out(piece)
