"""The Oracle — on-demand retrieval + Opus convergence ranking over the content lake (§1.8).

Runs as a pieceless background job (a ``Job(type=oracle)``, dispatched through the shared
``JobRunner``, never through ``PieceMachine``'s piece-stage batch chain): query the lake (bounded
top-K, windowed) via :class:`~app.lake.store.ContentLake`, run the Opus two-stage convergence rank
(:mod:`app.oracle.ranking`), and persist ranked Spikes to the pool/Vault, attributed to their
creator and this run's origin (:mod:`app.oracle.service`). Two entry points: **A** (open scan,
pure convergence) and **B** (a Narrative biases both the retrieval query and the ranking, §5-Q5).

Builds on the merged seams — never reimplements them:
- retrieval → ``ContentLake.query`` (D9),
- the job lifecycle → ``app.orchestration.jobs.JobRunner`` (Item 4), via :class:`OracleStep`
  (the ``BatchStep`` plug-in seam, D5),
- the Opus tier → ``app.llm.tiering.model_for_step(PipelineStep.ORACLE)`` (D14),
- persistence → ``WorkStateStore.spikes`` / ``.narratives`` (D3).

REST: ``POST /api/oracle/run`` (:mod:`app.oracle.routes`) — on-demand only, no scheduler (D7).
"""

from __future__ import annotations

from app.oracle.ranking import RankedSpikeCandidate, build_user_prompt, parse_ranked_spikes
from app.oracle.routes import router
from app.oracle.service import (
    DEFAULT_TOP_K_NARRATIVE,
    DEFAULT_TOP_K_OPEN_SCAN,
    OracleRunOutcome,
    OracleService,
)
from app.oracle.step import OracleStep

__all__ = [
    "DEFAULT_TOP_K_NARRATIVE",
    "DEFAULT_TOP_K_OPEN_SCAN",
    "OracleRunOutcome",
    "OracleService",
    "OracleStep",
    "RankedSpikeCandidate",
    "build_user_prompt",
    "parse_ranked_spikes",
    "router",
]
