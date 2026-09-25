"""Spike (domain model §1.6) and the origin/status vocabulary the Vault view filters on.

A candidate content topic proposed by the Oracle (or parked from a tangent). It persists,
carries a convergence score, and is attributed to its creator and origin (D15).

Modeling calls locked from §5:
- Q2: a *parked tangent* (D6) is represented as a Spike with ``origin.kind = tangent`` and a
  null ``convergence_score`` — one pool, one filter model — rather than a separate entity.
- The Vault (§1.7) is a *view* over spikes with ``status in {proposed, vaulted}``, not a store;
  the repository exposes it as a query, not a collection.

Invariant: ownership is **attribution, not a lock** — anyone can pick or advance any spike (D15).
A picked spike stays attributed to its creator. Nothing is thrown away (unpicked → Vault).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.models.common import MongoModel
from app.models.narrative import DistributionIntent


class SpikeStatus(str, Enum):
    proposed = "proposed"
    in_use = "in-use"
    picked = "picked"
    in_flight = "in-flight"
    vaulted = "vaulted"


class SpikeOriginKind(str, Enum):
    oracle_run = "oracle-run"
    narrative = "narrative"
    tangent = "tangent"  # parked idea (D6) — no OracleRun, no convergence score
    feedback = "feedback"  # out-of-scope review feedback parked, never discarded (feedback-intake.md)


class SpikeOrigin(BaseModel):
    """Where a spike came from. A nested value object, not its own document."""

    kind: SpikeOriginKind
    # ref = the OracleRun/Job id or Narrative id; null for a parked tangent.
    ref: str | None = None


class Spike(MongoModel):
    version: int = 0
    headline: str  # one-liner
    status: SpikeStatus = SpikeStatus.proposed
    # Null for parked tangents; a ranking score otherwise.
    convergence_score: float | None = None
    creator: str  # User (email/id) — attribution, never a lock
    origin: SpikeOrigin
    source_ids: list[str] = Field(default_factory=list)
    customer_partner: str | None = None  # "none yet" in v1
    outcome_metric: str | None = None  # "none yet" in v1
    rank_rationale: str | None = None
    convergence_note: str | None = None
    # Carried forward from a seeding Narrative (§5-Q5 deferred-distribution anchor).
    intent: DistributionIntent | None = None
    # 0..1 — set when the spike is picked and births a Piece.
    piece_id: str | None = None
    # The next workflow commits the Idea into one Content Project. This is workflow identity,
    # distinct from the legacy direct Piece hand-off above.
    content_project_id: str | None = None

    @model_validator(mode="after")
    def _tangent_has_no_convergence(self) -> Spike:
        if self.origin.kind == SpikeOriginKind.tangent and self.convergence_score is not None:
            raise ValueError(
                "a parked tangent (origin.kind=tangent) has no convergence score (§5-Q2)"
            )
        return self
