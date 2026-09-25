"""Brain drafts view (cmw-drafts-view).

A dedicated, read-only reading surface for brain-authored ``drafts/<slug>/`` content — live
from the brain clone, additive to the existing Google-Doc review/finalize flow, never a
replacement. Lists every draft folder and renders each as a clean, boss/customer-appropriate
page: ``draft.html`` when it exists, otherwise the direct-authored ``piece.md`` markdown section
rendered to HTML.

This module intentionally reads straight from Git rather than from Mongo work-state, so council
passes and hand-edits that land in the brain clone appear here automatically with no extra step.
Any minted Google Doc links are looked up from the synced Piece record and shown alongside the
brain content as additive references.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.git.content import GitContentStore
from app.git.repo import Commit
from app.piece_detail import draft_content_from_files
from app.schemas import BrainDraftDetailResponse, BrainDraftItem, BrainDraftListResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/brain", tags=["drafts"])


def _draft_metadata(files: object) -> dict[str, object]:
    """Identity metadata for a draft folder (title/voice/target/partners)."""
    from app.brain_sync import _identity_from

    meta = _identity_from(files)
    return {
        "title": meta.title or files.slug,
        "voice": meta.voice,
        "target": meta.target,
        "partners": meta.partners,
    }


def _commit_date(commit: Commit | None) -> str | None:
    if commit is None:
        return None
    return commit.date


@router.get("/drafts", response_model=BrainDraftListResponse)
async def list_brain_drafts(request: Request) -> BrainDraftListResponse:
    """List every draft folder currently in the brain clone, live from Git.

    503s cleanly when the brain clone is not configured, matching the other optional-subsystem
    routes.
    """
    content: GitContentStore | None = getattr(request.app.state, "git_content", None)
    if content is None:
        raise HTTPException(
            status_code=503, detail="brain drafts unavailable (brain clone not configured)"
        )

    slugs = content.list_pieces()
    items: list[BrainDraftItem] = []
    for slug in slugs:
        files = content.read_piece_files(slug)
        meta = _draft_metadata(files)
        try:
            revision = content.latest_folder_revision(slug)
        except Exception:  # noqa: BLE001 — best-effort provenance
            revision = None
        commits = content.repo.log(content._p("drafts", slug), max_count=1)
        latest = commits[0] if commits else None
        items.append(
            BrainDraftItem(
                slug=slug,
                title=meta["title"],
                voice=meta["voice"],
                target=meta["target"],
                partners=meta["partners"],
                has_html=files.draft_html is not None,
                has_piece_md=files.piece_md is not None,
                revision=revision,
                updated_at=_commit_date(latest),
            )
        )
    return BrainDraftListResponse(items=items)


@router.get("/drafts/{slug}", response_model=BrainDraftDetailResponse)
async def read_brain_draft(slug: str, request: Request) -> BrainDraftDetailResponse:
    """Render one brain draft as a presentable reading page.

    Content is read live from Git. If a matching Piece exists in Mongo, its minted review/final
    Doc URLs are included as additive references; if Mongo is unconfigured or the Piece has no
    such links, those fields are ``None`` and the page still renders the draft content.
    """
    content: GitContentStore | None = getattr(request.app.state, "git_content", None)
    if content is None:
        raise HTTPException(
            status_code=503, detail="brain drafts unavailable (brain clone not configured)"
        )

    if slug not in content.list_pieces():
        raise HTTPException(status_code=404, detail=f"no draft {slug!r}")

    files = content.read_piece_files(slug)
    meta = _draft_metadata(files)
    rendered = draft_content_from_files(files)
    content_kind = "html" if files.draft_html is not None else "markdown"

    try:
        revision = content.latest_folder_revision(slug)
    except Exception:  # noqa: BLE001
        revision = None
    commits = content.repo.log(content._p("drafts", slug), max_count=1)
    latest = commits[0] if commits else None

    review_doc_url: str | None = None
    final_doc_url: str | None = None
    store = getattr(request.app.state, "work_state", None)
    if store is not None:
        try:
            pieces = await store.pieces.find({"slug": slug})
            if pieces:
                piece = pieces[0]
                # Latest open or closed review round's Doc URL, if any.
                rounds = await store.review_rounds.find(
                    {"piece_id": piece.id}, sort=[("round_number", -1)]
                )
                if rounds:
                    review_doc_url = rounds[0].doc.url
                final = getattr(piece, "final_doc", None)
                if final is not None:
                    final_doc_url = final.url
        except Exception as exc:  # noqa: BLE001 — doc links are additive, never fatal
            logger.warning("could not load doc links for draft %s: %s", slug, exc)

    return BrainDraftDetailResponse(
        slug=slug,
        title=meta["title"],
        voice=meta["voice"],
        target=meta["target"],
        partners=meta["partners"],
        content_kind=content_kind,
        draft_html=rendered,
        revision=revision,
        updated_at=_commit_date(latest),
        review_doc_url=review_doc_url,
        final_doc_url=final_doc_url,
    )
