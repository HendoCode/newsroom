"""Orchestration core (D5; open-decisions Item 2 & 4; domain model §1.9/§1.16).

The deterministic per-piece state machine that sequences the pipeline lives in THIS Python service
(never in TypeScript, §6). This package is that core, built on the data layer (Piece/Job
repositories) and the LLM provider seam:

- :class:`~app.orchestration.machine.PieceMachine` — the settled 9-state machine: the three human
  triggers, batch chaining, and flag-not-rollback failure handling. Reuses the repository's
  ``ALLOWED_TRANSITIONS`` guard rather than re-encoding the table.
- :class:`~app.orchestration.jobs.JobRunner` — the background-job engine over the settled Job
  record: bounded retries, heartbeat/stuck detection, the per-run cost ceiling (the one hard block),
  and ``usage``/cost capture.
- :mod:`~app.orchestration.steps` — the batch-step plug-in seam (:class:`BatchStep` + registry) that
  Oracle/draft/council/incorporate/finalize will each implement (all downstream tickets).
- :mod:`~app.orchestration.retry` — the Anthropic error-taxonomy → retryable classifier.
- :mod:`~app.orchestration.stub_step` — the trivial stub proving the loop end-to-end.
"""

from __future__ import annotations

from app.orchestration.jobs import JobNotClaimable, JobRunner
from app.orchestration.machine import IllegalTrigger, PieceMachine
from app.orchestration.retry import (
    PermanentStepError,
    RefusalError,
    StepError,
    TransientStepError,
    classify_exception,
)
from app.orchestration.steps import (
    BatchStep,
    StepContext,
    StepNotRegistered,
    StepRegistry,
    StepResult,
)
from app.orchestration.stub_step import StubStep, build_stub_registry

__all__ = [
    "BatchStep",
    "IllegalTrigger",
    "JobNotClaimable",
    "JobRunner",
    "PermanentStepError",
    "PieceMachine",
    "RefusalError",
    "StepContext",
    "StepError",
    "StepNotRegistered",
    "StepRegistry",
    "StepResult",
    "StubStep",
    "TransientStepError",
    "build_stub_registry",
    "classify_exception",
]
