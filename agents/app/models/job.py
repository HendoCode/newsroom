"""Job — background batch-step record (domain model §1.16, the settled Item-4 schema).

A tracked execution of a batch step: oracle, draft, council, incorporate, finalize. Also the
realization of an **OracleRun** (§1.8) — an OracleRun *is* a ``Job(type=oracle)`` plus its output
spikes.

Invariants (§1.16):
- Failures **flag, do not roll back** the piece — the piece stays in its last stable stage.
- A new Revision is written to Git **only on success**; the status flip is the last step.
- The one sanctioned hard block anywhere in the system is the per-run **cost ceiling** (D14).
- ``stuck`` is detected via a missing heartbeat (crashed worker).

This module models the record only; the retry/heartbeat *policy* is the orchestration ticket.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.models.common import MongoModel


class JobType(str, Enum):
    oracle = "oracle"
    draft = "draft"
    council = "council"
    incorporate = "incorporate"
    finalize = "finalize"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    stuck = "stuck"


class JobError(BaseModel):
    code: str
    message: str
    # Transient (429/5xx/529, network) → retryable; deterministic (400/refusal/ceiling) → not.
    retryable: bool = False


class OracleEntryMode(str, Enum):
    """The Oracle's two entry points (domain model §1.8; context report §4)."""

    open_scan = "open-scan"  # Entry A — pure convergence ranking, no angle bias
    narrative = "narrative"  # Entry B — a Narrative biases ranking (incl. the retrieval query)


class OracleRunParams(BaseModel):
    """Per-run parameters for an OracleRun — a ``Job(type=oracle)`` (domain model §1.8: "two
    entry points... lookback window (per-run param, default 7d)... triggering User").

    ``voice`` selects whose style-guide grounds the convergence judgment ("contrarian points the
    author actually holds", context report §4b) — required since v1 supports more than one voice.
    ``top_k`` overrides the entry-mode default cap; leave unset to take the mode's default (open
    scan is broader than a narrative-narrowed run, context report §4e).
    """

    entry_mode: OracleEntryMode = OracleEntryMode.open_scan
    voice: str
    lookback_days: int = 7
    narrative_id: str | None = None  # required when entry_mode == narrative (Entry B)
    top_k: int | None = None

    @model_validator(mode="after")
    def _narrative_entry_requires_id(self) -> OracleRunParams:
        if self.entry_mode == OracleEntryMode.narrative and not self.narrative_id:
            raise ValueError("Entry B (entry_mode=narrative) requires narrative_id")
        return self


class OracleRunResultRecord(BaseModel):
    """Durable identity of one Oracle run's output.

    ``Job.id`` is the run. This record is what Radar (and ``GET /api/oracle/runs/{id}``) read
    back so a last-run panel can never be the whole Vault. Entry B stamps ``origin.ref`` as the
    Narrative id, not the job id, so spike-by-origin-ref is not a single key — persist the ids
    this run actually wrote.
    """

    spike_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    candidates_considered: int = 0


class Job(MongoModel):
    # Oracle jobs may run before any piece exists, so piece_id is optional.
    piece_id: str | None = None
    type: JobType
    status: JobStatus = JobStatus.queued
    attempts: int = 0
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    error: JobError | None = None
    cost: float = 0.0
    triggered_by: str | None = None  # User (email/id) — attribution
    # Set only for type=oracle — the OracleRun's entry mode/lookback/narrative (§1.8).
    oracle_params: OracleRunParams | None = None
    # Set only for type=oracle, on success or an empty-lake no-op — the run's own spikes/notes.
    oracle_result: OracleRunResultRecord | None = None
    # Meaningful only for type=finalize: which formats to produce (use case J "selectable at
    # finalize"). None means "the step's own default" (v1: all of html/pdf/doc).
    formats: list[str] | None = None
    # Meaningful only for type=council: the "2-4 more by fit" editors beyond the mandatory editors
    # (engine/3-revision-loop.md — technical-reviewer for a technical piece, closer/cold-reader for
    # a customer story, durability-reader/idea-density/hook-retention for opinion/brand, ...). Which
    # fit category a piece
    # belongs to is a judgment call the coordinator triggering the round makes (mirroring how the
    # engine step frames selection as "you" choosing); None means "mandatory + per-partner
    # steward(s) only" for this round. Unknown persona names are dropped, not rejected (§1.2 roster
    # is prunable — a stale name here should degrade, not fail the round).
    council_fit_editors: list[str] | None = None
