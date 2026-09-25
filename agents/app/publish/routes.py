"""HTTP surface for the publish flow: ``POST /api/pieces/{piece_id}/publish``.

The path deliberately matches the generic ``/api/pieces/{piece_id}/{trigger}`` shape
``app.orchestration.routes`` exposes for the other human triggers — ``web/``'s BFF proxy
(``app/api/pieces/[pieceId]/trigger/route.ts``) already forwards to exactly that shape, so no new
BFF plumbing was needed; only its ``PieceTrigger`` allow-list gained ``"publish"``. This module is
separate from ``app.orchestration.routes`` (rather than adding a fourth human trigger there)
because, like the review round-trip's mint, it composes a whole service (render + S3 upload +
Google Doc share) rather than firing a bare state-machine edge.

Mirrors the other route modules' 503-when-unconfigured guard (no Mongo / no Git content+brain / no
Google Docs credentials / no S3 bucket configured).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import get_settings
from app.drive import HttpDriveFolderClient
from app.git.brain import GitBrain
from app.git.content import GitContentStore
from app.models import PieceStage
from app.models.common import new_id, utcnow
from app.orchestration.machine import PieceMachine
from app.models.publication import ReleaseActor, TrivialEditWaiver
from app.publish.errors import (
    ApprovalInvalidated,
    DerivativeGateBlocked,
    NoRevisionToPublish,
    NotReleasableStage,
    PublishError,
)
from app.release.approval import approval_status
from app.publish.service import PublishService, UnpublishService
from app.publish.storage import PublishStorage, PublishStorageError, S3PublishStorage
from app.render.pdf import ChromiumPdfRenderer
from app.render.template import TemplateStore
from app.repositories import WorkStateStore
from app.review.docs_client import HttpReviewDocsClient, ReviewDocsClient

router = APIRouter(prefix="/api/pieces", tags=["publish"])


class PublishResponse(BaseModel):
    id: str
    slug: str
    stage: str
    published_release: int
    published_html_url: str | None = None
    published_pdf_url: str | None = None
    published_doc_url: str | None = None
    warnings: list[str] = Field(default_factory=list)


def _require(request: Request) -> tuple[WorkStateStore, GitContentStore, GitBrain, PieceMachine]:
    store = getattr(request.app.state, "work_state", None)
    content = getattr(request.app.state, "git_content", None)
    brain = getattr(request.app.state, "git_brain", None)
    machine = getattr(request.app.state, "piece_machine", None)
    if store is None or content is None or brain is None or machine is None:
        raise HTTPException(
            status_code=503,
            detail="publish unavailable (MONGO_URL / brain_root not configured)",
        )
    return store, content, brain, machine


Deps = Annotated[tuple[WorkStateStore, GitContentStore, GitBrain, PieceMachine], Depends(_require)]


def _docs_client(request: Request) -> ReviewDocsClient:
    """``app.state.publish_docs_client`` if a test attached one; otherwise the same server-side
    OAuth grant every other Google Docs caller uses (finalize's clean Doc, review's mint)."""
    attached = getattr(request.app.state, "publish_docs_client", None)
    if attached is not None:
        return attached
    settings = get_settings()
    if not (
        settings.google_oauth_client_id
        and settings.google_oauth_client_secret
        and settings.google_oauth_refresh_token
    ):
        raise HTTPException(
            status_code=503,
            detail=(
                "publish unavailable (GOOGLE_OAUTH_CLIENT_ID / _SECRET / _REFRESH_TOKEN not "
                "configured — see app/connectors/README.md)"
            ),
        )
    return HttpReviewDocsClient(
        settings.google_oauth_client_id,
        settings.google_oauth_client_secret,
        settings.google_oauth_refresh_token,
    )


def _drive_client(request: Request) -> HttpDriveFolderClient:
    """``app.state.publish_drive_client`` if a test attached one (mirrors ``_docs_client``);
    otherwise the same OAuth grant, wrapped with the folder/upload calls
    (cmw-drive-named-folder-scoping). Credential checks stay lazy — only
    ``GOOGLE_DRIVE_ROOT_FOLDER_NAME`` gates whether this is ever actually called at all."""
    attached = getattr(request.app.state, "publish_drive_client", None)
    if attached is not None:
        return attached
    settings = get_settings()
    return HttpDriveFolderClient(
        settings.google_oauth_client_id,
        settings.google_oauth_client_secret,
        settings.google_oauth_refresh_token,
    )


def _storage(request: Request) -> PublishStorage | None:
    """``app.state.publish_storage`` if a test attached one; otherwise a real S3 client from
    ``PUBLISHED_ASSETS_BUCKET``/``PUBLISHED_ASSETS_REGION``. Returns ``None`` when the bucket is
    not configured so the service can raise its own stage-gated 503."""
    attached = getattr(request.app.state, "publish_storage", None)
    if attached is not None:
        return attached
    settings = get_settings()
    try:
        return S3PublishStorage(settings.published_assets_bucket, region=settings.published_assets_region)
    except PublishStorageError:
        return None


@router.post("/{piece_id}/publish", response_model=PublishResponse)
async def publish(piece_id: str, deps: Deps, request: Request, actor: str | None = None) -> PublishResponse:
    """HUMAN "publish" (finalized → published, terminal): mint durable public outputs."""
    store, content, brain, machine = deps
    # Reuses the already-open brain repo/prefix rather than re-discovering from settings.brain_root
    # — the same repo `HttpReviewDocsClient`'s sibling callers share, and the seam tests inject a
    # throwaway fixture repo through (`app.state.git_brain`).
    template_store = TemplateStore(get_settings().brain_root, repo=brain.repo, prefix=brain.prefix)
    service = PublishService(
        store,
        content,
        brain,
        template_store,
        _storage(request),
        _docs_client(request),
        machine,
        pdf_renderer=ChromiumPdfRenderer(),
        drive_client=_drive_client(request),
        root_folder_name=get_settings().google_drive_root_folder_name,
    )
    try:
        result = await service.publish(piece_id, actor=actor)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotReleasableStage as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ApprovalInvalidated as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DerivativeGateBlocked as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NoRevisionToPublish as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PublishStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PublishError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    piece = result.piece
    assert piece.id is not None
    doc = piece.published_doc
    return PublishResponse(
        id=piece.id,
        slug=piece.slug,
        stage=PieceStage(piece.stage).value,
        published_release=piece.published_release,
        published_html_url=piece.published_html_url,
        published_pdf_url=piece.published_pdf_url,
        published_doc_url=doc.url if doc else None,
        warnings=result.warnings,
    )


class PublicationReleaseOut(BaseModel):
    id: str | None = None
    piece_id: str
    release_number: int
    revision: str
    authorized_by_subject_id: str
    authorized_at: object
    html_url: str | None = None
    pdf_url: str | None = None
    doc_url: str | None = None


class TrivialEditWaiverBody(BaseModel):
    from_revision: str = Field(min_length=1)
    to_revision: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    actor: str | None = None


def _store_only(request: Request) -> WorkStateStore:
    store = getattr(request.app.state, "work_state", None)
    if store is None:
        raise HTTPException(status_code=503, detail="work-state store unavailable")
    return store


@router.get("/{piece_id}/releases", response_model=list[PublicationReleaseOut])
async def list_releases(piece_id: str, request: Request) -> list[PublicationReleaseOut]:
    """Immutable numbered Publication Releases for a piece, oldest first."""
    store = _store_only(request)
    piece = await store.pieces.get(piece_id)
    if piece is None:
        raise HTTPException(status_code=404, detail=f"no piece {piece_id!r}")
    releases = await store.releases.by_piece(piece_id)
    return [
        PublicationReleaseOut(
            id=item.id,
            piece_id=item.piece_id,
            release_number=item.release_number,
            revision=item.revision,
            authorized_by_subject_id=item.authorized_by.subject_id,
            authorized_at=item.authorized_at,
            html_url=item.html_url,
            pdf_url=item.pdf_url,
            doc_url=item.doc.url if item.doc else None,
        )
        for item in releases
    ]


@router.post("/{piece_id}/waivers/trivial-edit", status_code=201)
async def record_trivial_edit_waiver(
    piece_id: str, body: TrivialEditWaiverBody, request: Request
) -> dict[str, object]:
    """Record that a canonical edit is trivial, keeping the prior approval valid."""
    store = _store_only(request)
    piece = await store.pieces.get(piece_id)
    if piece is None:
        raise HTTPException(status_code=404, detail=f"no piece {piece_id!r}")
    now = utcnow()
    actor_id = body.actor or piece.owner or "unknown"
    waiver = TrivialEditWaiver(
        id=new_id(),
        piece_id=piece_id,
        content_project_id=piece.content_project_id,
        from_revision=body.from_revision,
        to_revision=body.to_revision,
        actor=ReleaseActor(subject_id=actor_id, email=actor_id),
        reason=body.reason,
        recorded_at=now,
        created_at=now,
        updated_at=now,
    )
    await store.trivial_edit_waivers.insert(waiver)
    waivers = await store.trivial_edit_waivers.by_piece(piece_id)
    status = approval_status(
        approved_revision=piece.approved_revision,
        latest_revision=piece.latest_revision,
        waivers=waivers,
    )
    return {
        "id": waiver.id,
        "piece_id": piece_id,
        "approval_valid": status.valid,
        "reason": status.reason,
    }


class UnpublishResponse(BaseModel):
    id: str
    slug: str
    published_release: int
    warnings: list[str] = Field(default_factory=list)


@router.post("/{piece_id}/unpublish", response_model=UnpublishResponse)
async def unpublish(piece_id: str, deps: Deps, request: Request, actor: str | None = None) -> UnpublishResponse:
    """HUMAN "unpublish": flip S3 objects + Drive Published/ subfolder to private (idempotent, resilient to missing artifacts)."""
    store, _, _, _ = deps
    service = UnpublishService(
        store,
        _storage(request),
        _docs_client(request),
    )
    try:
        result = await service.unpublish(piece_id, actor=actor)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PublishStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    piece = result.piece
    assert piece.id is not None
    return UnpublishResponse(
        id=piece.id,
        slug=piece.slug,
        published_release=piece.published_release,
        warnings=result.warnings,
    )
