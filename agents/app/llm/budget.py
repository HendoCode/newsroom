"""Per-run cost / iteration ceiling — the one sanctioned hard stop (D14).

D14: "one company key, server-side, model-tiered, **per-run ceilings**". A :class:`RunBudget`
threads through the calls of a single pipeline run (an Oracle run, a council round, an interview
session). Each call the provider makes against it is *pre-flighted* — if the run has already hit
its call, token, or cost ceiling, the next call raises :class:`RunBudgetExceeded` instead of
firing. After a call lands, its ``usage`` + cost are *charged* so the ceiling and the courtesy
cost readout share one source of truth.

This is deliberately the only hard stop in the layer: the council runs one scoring pass per human
round (settled), drafts are single calls, so a runaway can only come from a caller looping — the
budget bounds exactly that.
"""

from __future__ import annotations

from app.llm.pricing import Usage, cost_usd


class RunBudgetExceeded(RuntimeError):
    """Raised when a call would exceed a run's call / token / cost ceiling (D14)."""


class RunBudget:
    """A mutable per-run ceiling. Not thread-safe by design — a run's calls are driven from one
    orchestration coroutine; council fan-out charges its concurrent calls on the same loop.

    Any of ``max_calls`` / ``max_total_tokens`` / ``max_cost_usd`` left ``None`` is unbounded on
    that axis. ``check`` is the pre-flight gate; ``charge`` records a landed call's usage/cost.
    """

    def __init__(
        self,
        *,
        max_calls: int | None = None,
        max_total_tokens: int | None = None,
        max_cost_usd: float | None = None,
    ) -> None:
        self.max_calls = max_calls
        self.max_total_tokens = max_total_tokens
        self.max_cost_usd = max_cost_usd
        self.calls = 0
        self.usage = Usage()
        self.cost = 0.0

    def check(self) -> None:
        """Pre-flight gate, called *before* a request fires. Raises if the run has already
        reached any ceiling — so the ceiling is enforced without first spending another call."""
        if self.max_calls is not None and self.calls >= self.max_calls:
            raise RunBudgetExceeded(
                f"run call ceiling reached: {self.calls}/{self.max_calls} calls"
            )
        if (
            self.max_total_tokens is not None
            and self.usage.total_input_tokens + self.usage.output_tokens
            >= self.max_total_tokens
        ):
            raise RunBudgetExceeded(
                f"run token ceiling reached: "
                f"{self.usage.total_input_tokens + self.usage.output_tokens}"
                f"/{self.max_total_tokens} tokens"
            )
        if self.max_cost_usd is not None and self.cost >= self.max_cost_usd:
            raise RunBudgetExceeded(
                f"run cost ceiling reached: ${self.cost:.4f}/${self.max_cost_usd:.4f}"
            )

    def charge(self, model: str, usage: Usage) -> float:
        """Record a landed call's ``usage`` against the run and return its USD cost. Called
        *after* a response completes; keeps the ceiling and the cost readout in lockstep."""
        self.calls += 1
        self.usage = self.usage + usage
        call_cost = cost_usd(model, usage)
        self.cost += call_cost
        return call_cost

    def snapshot(self) -> dict[str, object]:
        """A plain-dict view for the per-piece cost readout / run record (D14)."""
        return {
            "calls": self.calls,
            "input_tokens": self.usage.input_tokens,
            "output_tokens": self.usage.output_tokens,
            "cache_creation_input_tokens": self.usage.cache_creation_input_tokens,
            "cache_read_input_tokens": self.usage.cache_read_input_tokens,
            "total_tokens": self.usage.total_input_tokens + self.usage.output_tokens,
            "cost_usd": round(self.cost, 6),
        }
