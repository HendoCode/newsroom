"""Brain-draft visibility: register brain-authored ``drafts/<slug>/`` folders as Pieces
(cmw-brain-pieces-visibility).

A Piece is a composite (domain model §1.9): content in Git (``drafts/<slug>/``) + work-state in
Mongo. The brain side can author draft folders ON ITS OWN — hand-nurtured or via brain-side agent
tasks (the 2026-08-30/31 AWS seller briefs: ``amazon-quick-seller-brief``,
``failed-poc-unit-economics``, ``aws-agentcore-websearch``, ``aws-iceberg-agentic``) —
and those folders then have content but no Mongo record, so they are invisible to every piece
list the site renders (dashboard queue, desk recent-pieces strip, Library). This module completes
the composite for them: one idempotent sync mints the missing Mongo half per unregistered slug.

The synced record is deliberately minimal and honest about what it is:

- ``brain_synced=True`` marks the provenance (never written by the pipeline itself).
- Identity (title/voice/target/partners) is lifted from the folder's ``piece.md`` metadata block
  (``app.piece_md.parse_piece_md_meta``), falling back to the slug / ``demo-dana``.
- ``latest_revision`` points at the newest commit touching the folder (``GitContentStore.
  latest_folder_revision``) even when there is no ``draft.html`` Revision lineage.
- Stage is ``review`` — the closest settled stage (§1.9) to "a draft exists and is awaiting a
  human pass" (the brain's own piece.md vocabulary: *ready-for-human-pass*). It is NOT
  ``drafting`` (that stage asserts a draft JOB is running), and nothing about the sync pretends
  the piece ever went through interview/council — its content is readable as-is via
  ``app.piece_detail.read_draft_content``'s piece.md fallback.

Nothing here ever writes to the brain (no commits, no pushes) — sync only reads Git and writes
Mongo work-state.

Trigger points: the lifespan runs it once at boot (auto-discovery — a deploy/restart alone makes
brain drafts visible, no operator step), and ``POST /api/brain/pull`` re-runs it after a
successful pull so freshly pulled drafts appear without a restart. This module also exposes the
explicit ``POST /api/brain/sync`` for an on-demand run.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.git.content import GitContentStore, PieceFiles
from app.git.repo import GitError
from app.models.piece import Piece, PieceStage
from app.piece_md import PieceMdMeta, first_h1, html_document_title, parse_piece_md_meta
from app.repositories import WorkStateStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/brain", tags=["ops"])

# A brain draft whose piece.md names no voice gets the org's default voice pack (the same one the
# operator desk's commit-idea path uses).
DEFAULT_SYNC_VOICE = "demo-dana"

# The settled stage (§1.9) a synced brain draft lands at — see the module docstring.
SYNCED_STAGE = PieceStage.review


def _identity_from(files: PieceFiles) -> PieceMdMeta:
    """The identity fields for a synced piece, merged from ``piece.md`` and the brain-side
    ``meta.json`` (when present). ``piece.md`` bullets win field-by-field; ``meta.json`` fills
    what the bullets lack (the direct-content briefs carry their structure ONLY in meta.json).
    Entirely tolerant: a malformed meta.json or missing file degrades, never fails.
    """
    meta = parse_piece_md_meta(files.piece_md)
    data: object = None
    if files.meta_json:
        try:
            data = json.loads(files.meta_json)
        except (ValueError, TypeError):
            data = None
    if isinstance(data, dict):
        if meta.title is None and isinstance(data.get("title"), str) and data["title"].strip():
            meta.title = data["title"].strip()
        if meta.voice is None and isinstance(data.get("voice"), str) and data["voice"].strip():
            meta.voice = data["voice"].strip().split()[0]
        if meta.target is None:
            for key in ("format", "type"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    meta.target = value.strip()
                    break
        if not meta.partners:
            partners = data.get("partners")
            if isinstance(partners, list):
                seen: set[str] = set()
                for entry in partners:
                    if isinstance(entry, str):
                        slug = entry.strip().lower()
                        if slug and slug not in seen:
                            seen.add(slug)
                            meta.partners.append(slug)
    # Last resort for the direct-content shape: the piece.md's own first H1 heading.
    if meta.title is None:
        meta.title = first_h1(files.piece_md)
    # Final fallback for piece.md-less folders (older pipeline-shaped drafts): the draft.html's
    # own <title>/<h1> — a real headline beats the raw slug.
    if meta.title is None:
        meta.title = html_document_title(files.draft_html)
    return meta


class BrainSyncResult(BaseModel):
    """What one sync pass did (also the REST response shape)."""

    created: list[str] = Field(default_factory=list)  # slugs newly registered as Pieces
    existing: list[str] = Field(default_factory=list)  # slugs that already had a Piece
    drafts: int = 0  # total draft folders the brain currently holds


async def sync_brain_pieces(store: WorkStateStore, content: GitContentStore) -> BrainSyncResult:
    """Idempotently register every brain draft folder that has no Piece yet.

    Slugs that already have a Piece (pipeline-created OR previously synced) are never touched —
    the sync never overwrites or re-stages an existing record.
    """
    slugs = content.list_pieces()
    existing_slugs = {p.slug for p in await store.pieces.find({})}
    created: list[str] = []
    for slug in slugs:
        if slug in existing_slugs:
            continue
        files = content.read_piece_files(slug)
        meta = _identity_from(files)
        try:
            revision = content.latest_folder_revision(slug)
        except GitError:
            revision = None  # provenance pointer is best-effort, never a reason to skip
        await store.pieces.insert(
            Piece(
                slug=slug,
                voice=meta.voice or DEFAULT_SYNC_VOICE,
                title=meta.title or slug,
                target=meta.target,
                partners=meta.partners,
                stage=SYNCED_STAGE,
                latest_revision=revision,
                brain_synced=True,
            )
        )
        created.append(slug)
    if created:
        logger.info(
            "brain-draft sync registered %d piece(s): %s", len(created), ", ".join(created)
        )
    return BrainSyncResult(
        created=created,
        existing=sorted(existing_slugs & set(slugs)),
        drafts=len(slugs),
    )


@router.post("/sync", response_model=BrainSyncResult)
async def brain_sync(request: Request) -> BrainSyncResult:
    """Register brain-authored draft folders as Pieces on demand.

    Idempotent — safe to re-run after every ``POST /api/brain/pull`` that may have brought new
    drafts in. 503s cleanly when either dependency is unconfigured (Mongo, or a usable brain
    clone) rather than crashing, matching the other optional-subsystem routes.
    """
    store: WorkStateStore | None = getattr(request.app.state, "work_state", None)
    if store is None:
        raise HTTPException(status_code=503, detail="brain sync unavailable (MONGO_URL not configured)")
    content: GitContentStore | None = getattr(request.app.state, "git_content", None)
    if content is None:
        raise HTTPException(
            status_code=503, detail="brain sync unavailable (brain clone not configured)"
        )
    return await sync_brain_pieces(store, content)
