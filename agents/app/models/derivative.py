"""Derivative artifacts (cmw-lesson-lineage-impl).

A native-format follow-on of an anchor piece (LinkedIn post, X thread, newsletter, …). **Child
of the anchor by default** — not a top-level Piece, so it has no owner/review/publish state of
its own and does not appear in the dashboard queue. Promoted to a Piece only when it needs that
independent lifecycle (``lineage=promoted``, ``promoted_piece_id`` set).

Generation of the native content is a separate ticket; this model is the lineage record.
"""

from __future__ import annotations

from enum import Enum

from app.models.common import MongoModel


class DerivativeLineage(str, Enum):
    child = "child"
    promoted = "promoted"


class DerivativeArtifact(MongoModel):
    anchor_piece_id: str
    content_project_id: str | None = None
    destination: str
    title: str
    voice: str | None = None
    lineage: DerivativeLineage = DerivativeLineage.child
    promoted_piece_id: str | None = None
