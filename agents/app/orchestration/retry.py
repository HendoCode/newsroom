"""Error classification for the job runner (open-decisions Item 4; domain model §1.16).

The settled failure model splits every job error into **transient** (auto-retry with bounded outer
attempts) and **deterministic** (surface immediately; retrying unchanged just fails again), keyed
to the Anthropic error taxonomy:

- **Transient → retryable:** 429 rate-limit, 5xx server errors, 529 overloaded, and network /
  timeout errors. (The ``anthropic`` SDK already retries these once or twice with backoff; the job
  layer adds a bounded *outer* retry so a whole-job transient still recovers.)
- **Deterministic → not retryable:** 400/422 invalid request, a ``stop_reason == "refusal"``
  completion, and the per-run **cost ceiling** (:class:`~app.llm.budget.RunBudgetExceeded`) — the
  one sanctioned hard block (D14).

Classification is by **duck-typing**, not ``isinstance`` against ``anthropic`` classes, so this
runs identically whether the failure came from a real SDK exception (which carries ``status_code``)
or a lightweight test double — and needs neither the package nor a network. Steps that want to be
explicit can raise the :class:`StepError` subclasses below instead of relying on inference.
"""

from __future__ import annotations

from app.llm.budget import RunBudgetExceeded
from app.models import JobError


class StepError(Exception):
    """Base for failures a batch step raises deliberately, carrying its own retry classification.

    A step that already knows whether a failure is worth retrying (e.g. it inspected a response)
    should raise one of the subclasses rather than let the runner infer from a bare exception.
    """

    code: str = "step_error"
    retryable: bool = False

    def as_job_error(self) -> JobError:
        return JobError(code=self.code, message=str(self) or self.code, retryable=self.retryable)


class TransientStepError(StepError):
    """A transient failure the step wants retried (bounded)."""

    code = "transient"
    retryable = True


class PermanentStepError(StepError):
    """A deterministic failure that will not succeed unchanged — do not retry."""

    code = "permanent"
    retryable = False


class RefusalError(PermanentStepError):
    """The model returned ``stop_reason == "refusal"``. Deterministic; surfaces for a human."""

    code = "refusal"


# HTTP status codes that mean "try again" (context report §2 error taxonomy).
_RETRYABLE_STATUS = {408, 409, 429}


def _looks_like_network_error(exc: BaseException) -> bool:
    """True for connection/timeout failures (no HTTP status) — always transient."""
    name = type(exc).__name__.lower()
    return "connection" in name or "timeout" in name


def classify_exception(exc: BaseException) -> JobError:
    """Map a raised exception to a :class:`~app.models.JobError` (code + message + retryable).

    Precedence: the cost ceiling first (the one hard block), then a step's own declared
    classification, then the Anthropic HTTP-status taxonomy, then network errors, and finally an
    unknown error — which is treated as **not** retryable so a mystery failure never burns retries.
    """
    # The single sanctioned hard block: per-run cost/token ceiling (D14). Never retried.
    if isinstance(exc, RunBudgetExceeded):
        return JobError(code="ceiling", message=str(exc) or "per-run ceiling exceeded", retryable=False)

    # A step that classified its own failure wins over inference.
    if isinstance(exc, StepError):
        return exc.as_job_error()

    # Anthropic APIStatusError (and SDK subclasses) carry an HTTP ``status_code``.
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        retryable = status in _RETRYABLE_STATUS or status >= 500  # 5xx incl. 529 overloaded
        code = _status_code_label(status)
        return JobError(code=code, message=f"HTTP {status}: {exc}", retryable=retryable)

    # Connection reset / read timeout with no status → transient.
    if _looks_like_network_error(exc):
        return JobError(code="network", message=str(exc) or type(exc).__name__, retryable=True)

    # Unknown: fail closed (deterministic) so an unrecognized error is surfaced, not looped on.
    return JobError(code="unknown", message=str(exc) or type(exc).__name__, retryable=False)


def _status_code_label(status: int) -> str:
    if status == 429:
        return "rate_limit"
    if status == 529:
        return "overloaded"
    if status >= 500:
        return "server_error"
    if status in (400, 422):
        return "invalid_request"
    return f"http_{status}"
