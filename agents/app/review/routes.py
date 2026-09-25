"""HTTP surface for the review round-trip (open-decisions Item 7; domain model §1.14/§1.15).

ReviewRound is the primary REST resource here — the Google Doc is a child link on each round
(``DocRef``, carried inside ``ReviewRoundOut``), never the top-level affordance (cmw-review-round-ux-impl).

- ``GET /api/pieces/{piece_id}/review/rounds`` — list every round for a piece (the primary
  read path the UI mounts from).
- ``GET /api/pieces/{piece_id}/review/rounds/{round_number}`` — a single round by number.
- ``POST /api/pieces/{piece_id}/review/mint`` — mint an internal/external Doc from the piece's
  current revision, opening a new ``ReviewRound`` (§1.14). Returns the new round (the primary
  object), with the Doc link nested inside it.
- ``GET /api/pieces/{piece_id}/review/preview`` — the assisted ingest preview ("N comments · M
  edits — fold these in?") a human checks before clicking "reviews done".

The human "reviews done" trigger that actually closes a round already exists at
``POST /api/pieces/{piece_id}/reviews-done`` (``app.orchestration.routes``) — it dispatches this
ticket's ``IncorporateStep`` once that step is registered into the shared ``StepRegistry`` (see
``app/review/README.md`` for the integration point).

Mirrors the other route modules' 503-when-unconfigured guard (no Mongo / no Git content store / no
Google Docs credentials).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import get_settings
from app.drive import HttpDriveFolderClient
from app.git.content import GitContentStore
from app.models import ReviewRound, ReviewRoundStatus, ShareMode
from app.repositories import WorkStateStore
from app.review.docs_client import HttpReviewDocsClient, ReviewDocsClient
from app.review.errors import NoRevisionToMint, NotInReviewStage, UnsafeExternalShareError
from app.review.mint import ReviewMintService
from app.review.preview import preview_round
from app.schemas import ReviewRoundOut

router = APIRouter(prefix="/api/pieces", tags=["review"])


class MintReviewRequest(BaseModel):
    share_mode: ShareMode = ShareMode.internal
    reviewer_emails: list[str] | None = None


class MintReviewResponse(BaseModel):
    round_number: int
    doc_url: str | None = None
    share_mode: str
    warnings: list[str] = Field(default_factory=list)


class ReviewPreviewResponse(BaseModel):
    round_number: int
    comment_count: int
    edit_count: int
    no_changes: bool
    diff_degraded: bool
    samples: list[str] = Field(default_factory=list)


class ReviewRoundListResponse(BaseModel):
    """ReviewRound as the primary REST resource — the Doc is a child link inside each round."""
    rounds: list[ReviewRoundOut]


def _require_store(request: Request) -> WorkStateStore:
    store = getattr(request.app.state, "work_state", None)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="review unavailable (MONGO_URL not configured)",
        )
    return store


def _require(request: Request) -> tuple[WorkStateStore, GitContentStore]:
    store = getattr(request.app.state, "work_state", None)
    content = getattr(request.app.state, "git_content", None)
    if store is None or content is None:
        raise HTTPException(
            status_code=503,
            detail="review unavailable (MONGO_URL / brain_root not configured)",
        )
    return store, content


Deps = Annotated[tuple[WorkStateStore, GitContentStore], Depends(_require)]


def _docs_client(request: Request) -> ReviewDocsClient | None:
    """``app.state.review_docs_client`` if one is attached (tests inject a fake here, mirroring
    ``app.state.llm_provider``); otherwise built fresh from server-side settings — the same OAuth
    grant as the Drive connector / finalize's clean-Doc export (no separate credential story).

    Returns ``None`` when the OAuth trio is not configured, so review can still open a round
    locally without uploading a Google Doc.
    """
    attached = getattr(request.app.state, "review_docs_client", None)
    if attached is not None:
        return attached
    settings = get_settings()
    if not (
        settings.google_oauth_client_id
        and settings.google_oauth_client_secret
        and settings.google_oauth_refresh_token
    ):
        return None
    return HttpReviewDocsClient(
        settings.google_oauth_client_id,
        settings.google_oauth_client_secret,
        settings.google_oauth_refresh_token,
    )


def _drive_client(request: Request) -> HttpDriveFolderClient:
    """``app.state.review_drive_client`` if a test attached one (mirrors ``_docs_client``);
    otherwise the same OAuth grant, wrapped with the folder/upload calls
    (cmw-drive-named-folder-scoping). Credential checks stay lazy (``_require_creds`` at call time) —
    only ``GOOGLE_DRIVE_ROOT_FOLDER_NAME`` gates whether this is ever actually called at all."""
    attached = getattr(request.app.state, "review_drive_client", None)
    if attached is not None:
        return attached
    settings = get_settings()
    return HttpDriveFolderClient(
        settings.google_oauth_client_id,
        settings.google_oauth_client_secret,
        settings.google_oauth_refresh_token,
    )


@router.post("/{piece_id}/review/mint", response_model=MintReviewResponse)
async def mint(piece_id: str, req: MintReviewRequest, deps: Deps, request: Request) -> MintReviewResponse:
    """Mint an internal/external review Doc from the piece's current revision (D4/D11)."""
    store, content = deps
    docs_client = _docs_client(request)
    service = ReviewMintService(
        store,
        content,
        docs_client,
        drive_client=_drive_client(request),
        root_folder_name=get_settings().google_drive_root_folder_name,
    )
    try:
        result = await service.mint(
            piece_id, share_mode=req.share_mode, reviewer_emails=req.reviewer_emails
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotInReviewStage as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UnsafeExternalShareError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NoRevisionToMint as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MintReviewResponse(
        round_number=result.round.round_number,
        doc_url=result.round.doc.url,
        # DocRef is a plain nested BaseModel (not a MongoModel), so it doesn't inherit the
        # `use_enum_values` coercion — normalize explicitly (mirrors piece_detail._review_round_out).
        share_mode=ShareMode(result.round.doc.share_mode).value,
        warnings=result.warnings,
    )


@router.get("/{piece_id}/review/preview", response_model=ReviewPreviewResponse)
async def preview(piece_id: str, deps: Deps, request: Request) -> ReviewPreviewResponse:
    """The assisted ingest preview for the piece's currently open review round."""
    store, content = deps
    piece = await store.pieces.get(piece_id)
    if piece is None:
        raise HTTPException(status_code=404, detail=f"no piece {piece_id!r}")
    round_ = await store.review_rounds.latest_for_piece(piece_id)
    if round_ is None or ReviewRoundStatus(round_.status) != ReviewRoundStatus.open:
        raise HTTPException(
            status_code=404, detail=f"no open review round for piece {piece_id!r}"
        )
    docs_client = _docs_client(request)
    if docs_client is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "review preview unavailable (GOOGLE_OAUTH_CLIENT_ID / _SECRET / _REFRESH_TOKEN not "
                "configured — see app/connectors/README.md)"
            ),
        )
    result = await preview_round(docs_client, content, round_, slug=piece.slug)
    return ReviewPreviewResponse(
        round_number=result.round_number,
        comment_count=result.comment_count,
        edit_count=result.edit_count,
        no_changes=result.no_changes,
        diff_degraded=result.diff_degraded,
        samples=result.samples,
    )


# --- ReviewRound as the primary REST resource (cmw-review-round-ux-impl) ---
# The Google Doc is a child link inside each round (ReviewRoundOut.doc_url), never the
# top-level affordance. These two endpoints make the round the first-class resource the
# UI mounts from, rather than relying on the piece-detail response's embedded rounds.


def _round_out(round_: ReviewRound) -> ReviewRoundOut:
    """Thin normalization (mirrors piece_detail._review_round_out)."""
    return ReviewRoundOut(
        round_number=round_.round_number,
        minted_from_revision=round_.minted_from_revision,
        status=ReviewRoundStatus(round_.status).value,
        share_mode=ShareMode(round_.doc.share_mode).value,
        doc_url=round_.doc.url,
        opened_at=round_.opened_at,
        routing_log=list(round_.routing_log),
    )


@router.get("/{piece_id}/review/rounds", response_model=ReviewRoundListResponse)
async def list_rounds(piece_id: str, request: Request) -> ReviewRoundListResponse:
    """Every review round for this piece, ascending (round 1 first)."""
    store = _require_store(request)
    piece = await store.pieces.get(piece_id)
    if piece is None:
        raise HTTPException(status_code=404, detail=f"no piece {piece_id!r}")
    rounds = await store.review_rounds.by_piece(piece_id)
    return ReviewRoundListResponse(rounds=[_round_out(r) for r in rounds])


@router.get("/{piece_id}/review/rounds/{round_number}", response_model=ReviewRoundOut)
async def get_round(piece_id: str, round_number: int, request: Request) -> ReviewRoundOut:
    """A single review round by number."""
    store = _require_store(request)
    piece = await store.pieces.get(piece_id)
    if piece is None:
        raise HTTPException(status_code=404, detail=f"no piece {piece_id!r}")
    rounds = await store.review_rounds.by_piece(piece_id)
    for r in rounds:
        if r.round_number == round_number:
            return _round_out(r)
    raise HTTPException(
        status_code=404, detail=f"no round {round_number} for piece {piece_id!r}"
    )
