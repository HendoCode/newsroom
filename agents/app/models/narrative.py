"""Narrative — the distribution-intent attachment point (domain model §1.5, Oracle Entry B).

An author-spoken seed, in their own voice, carrying audience/angle intent, committed to run the
Oracle. In v1 the intent is consumed **only** as a soft Oracle ranking bias (D7). Per §5-Q5 we
model the intent as a first-class object now — and carry it forward onto the Spike/Piece it seeds
— so the deferred distribution effort (§9) can attach later without reshaping the model.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.models.common import MongoModel


class DistributionIntent(BaseModel):
    """Author's audience/angle intent. First-class per §5-Q5 (deferred-distribution anchor).
    Carried onto the Spike and Piece a Narrative seeds; consumed only as a ranking bias in v1."""

    audience: str | None = None
    angle: str | None = None


class Narrative(MongoModel):
    author: str  # User (email/id) — attribution
    seed_text: str
    intent: DistributionIntent = DistributionIntent()
    # The OracleRun (a Job of type=oracle) this narrative triggered, once it runs.
    oracle_run_id: str | None = None
