"""Create child derivative artifacts and promote them to top-level Pieces.

Child by default (no owner/review/publish of their own, hidden from the dashboard queue because
they are not Pieces). Promotion mints a real Piece with ``role=derivative`` and
``parent_piece_id`` pointing at the anchor — that Piece then has its own owner and can move
through review/publish independently.
"""

from __future__ import annotations

import re

from app.derivatives.errors import (
    DerivativeAlreadyExists,
    DerivativeAlreadyPromoted,
    DerivativeNotFound,
)
from app.models import DerivativeArtifact, DerivativeLineage, Piece, PieceRole, PieceStage
from app.repositories import WorkStateStore

_SLUG_RE = re.compile(r"[^a-z0-9]+")


class DerivativesService:
    def __init__(self, store: WorkStateStore) -> None:
        self.store = store

    async def list_for_anchor(self, anchor_piece_id: str) -> list[DerivativeArtifact]:
        await self._get_piece(anchor_piece_id)
        return await self.store.derivatives.by_anchor(anchor_piece_id)

    async def create_child(
        self,
        anchor_piece_id: str,
        *,
        destination: str,
        title: str | None = None,
    ) -> DerivativeArtifact:
        """Record a child artifact of the anchor. Does not generate native content."""
        anchor = await self._get_piece(anchor_piece_id)
        dest = destination.strip()
        if not dest:
            raise ValueError("destination is empty")
        existing = await self.store.derivatives.by_anchor_and_destination(anchor_piece_id, dest)
        if existing is not None:
            raise DerivativeAlreadyExists(
                f"anchor {anchor_piece_id!r} already has a {dest!r} derivative"
            )
        anchor_title = anchor.title or anchor.slug
        artifact = DerivativeArtifact(
            anchor_piece_id=anchor_piece_id,
            content_project_id=anchor.content_project_id,
            destination=dest,
            title=(title.strip() if title and title.strip() else f"{anchor_title} — {dest}"),
            voice=anchor.voice,
            lineage=DerivativeLineage.child,
        )
        return await self.store.derivatives.insert(artifact)

    async def promote(
        self,
        anchor_piece_id: str,
        artifact_id: str,
        *,
        owner: str | None = None,
    ) -> tuple[DerivativeArtifact, Piece]:
        """Promote a child artifact to a top-level Piece with its own owner/review/publish state."""
        anchor = await self._get_piece(anchor_piece_id)
        artifact = await self.store.derivatives.get(artifact_id)
        if artifact is None or artifact.anchor_piece_id != anchor_piece_id:
            raise DerivativeNotFound(
                f"no derivative {artifact_id!r} on piece {anchor_piece_id!r}"
            )
        if DerivativeLineage(artifact.lineage) != DerivativeLineage.child:
            raise DerivativeAlreadyPromoted(
                f"derivative {artifact_id!r} is already a top-level piece"
            )

        slug = await self._unique_slug(anchor.slug, artifact.destination)
        piece = Piece(
            content_project_id=anchor.content_project_id,
            role=PieceRole.derivative,
            parent_piece_id=anchor.id,
            slug=slug,
            voice=artifact.voice or anchor.voice,
            title=artifact.title,
            target=artifact.destination,
            stage=PieceStage.interviewing,
            owner=owner,
        )
        created = await self.store.pieces.insert(piece)
        assert created.id is not None
        updated = await self.store.derivatives.update(
            artifact_id,
            {
                "lineage": DerivativeLineage.promoted,
                "promoted_piece_id": created.id,
            },
        )
        assert updated is not None
        return updated, created

    async def _get_piece(self, piece_id: str) -> Piece:
        piece = await self.store.pieces.get(piece_id)
        if piece is None:
            raise KeyError(f"no piece {piece_id!r}")
        return piece

    async def _unique_slug(self, anchor_slug: str, destination: str) -> str:
        dest_slug = _SLUG_RE.sub("-", destination.lower()).strip("-") or "derivative"
        base = f"{anchor_slug}-{dest_slug}"
        slug = base
        n = 2
        while await self.store.pieces.by_slug(slug) is not None:
            slug = f"{base}-{n}"
            n += 1
        return slug
