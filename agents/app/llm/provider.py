"""The swappable ``LLMProvider`` seam (open-decisions Item 1; context report §14).

Item 1 is settled: **thin, direct first-party Anthropic, behind a swappable interface** so a
future Hendo / Bedrock implementation drops in without touching callers. This module defines that
interface and the wire-neutral value types every implementation and caller share. The Anthropic
implementation lives in ``anthropic_provider``; a fake used by the pipeline steps' tests and by
``council`` lives behind the same ABC.

Design notes:
- ``system`` / ``messages`` use neutral plain-text value types; each provider translates to its
  own wire (Anthropic adds cache_control when cache=True; Bedrock/GLM ignores cache and uses
  Converse shape).
- Sampling params absent (Opus/Sonnet reject them). ``effort``/``thinking``/``tools``/``cache``
  are passed through or ignored per provider.
- Streaming under the hood for timeout safety and first-token fan-out.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager

from pydantic import BaseModel

from app.llm.budget import RunBudget
from app.llm.pricing import Usage
from app.llm.tiering import PipelineStep

# Neutral seam types: callers and assembler supply plain text (or list of plain text blocks for
# system). Providers translate to their wire format internally. Cache control, thinking, tools and
# effort are provider-specific and never appear in these types.
SystemPrompt = str | list[str]
Message = dict[str, str]  # {"role": "user"|"assistant", "content": "<plain text>"}


class LLMResult(BaseModel):
    """The outcome of one completed call — the same shape from every provider."""

    text: str  # concatenated text blocks of the response
    model: str
    stop_reason: str | None = None
    usage: Usage
    cost_usd: float


class LLMStream(ABC):
    """A live call in progress. Exists for the council fan-out primitive (§10): the caller awaits
    :meth:`wait_first_token` (the cache write has begun) before firing the rest of the round, then
    awaits :meth:`final` for the result. Used as an async context manager."""

    @abstractmethod
    async def __aenter__(self) -> LLMStream: ...

    @abstractmethod
    async def __aexit__(self, *exc: object) -> None: ...

    @abstractmethod
    async def wait_first_token(self) -> None:
        """Resolve once the first output token has streamed (or the call finished without one).
        After this resolves the prefix cache entry is being written and is readable by fan-out
        siblings (claude-api concurrent-request rule)."""

    @abstractmethod
    async def final(self) -> LLMResult:
        """Await the completed :class:`LLMResult` (charges ``budget`` if one was supplied)."""


class LLMProvider(ABC):
    """The one seam every pipeline step calls. Swappable by construction — callers depend only on
    this ABC, never on a concrete provider or the ``anthropic`` SDK."""

    @abstractmethod
    async def complete(
        self,
        *,
        step: PipelineStep,
        model: str,
        system: SystemPrompt,
        messages: list[Message],
        max_tokens: int,
        effort: str | None = None,
        thinking: dict[str, object] | None = None,
        tools: list[dict[str, object]] | None = None,
        cache: bool = False,
        budget: RunBudget | None = None,
    ) -> LLMResult:
        """One non-streaming completion. ``model`` is a per-call argument (D14 tiering); ``step``
        is passed for routing/telemetry, not to pick the model. ``tools`` carries raw Anthropic
        tool definitions (research sidecar carve-out only). ``thinking`` and ``effort`` are
        provider-specific (omitted/ignored by providers that do not support them). ``cache=True``
        requests a cache breakpoint on the stable prefix where supported (Anthropic only; others
        ignore). ``budget`` is pre-flighted and charged if supplied."""

    @abstractmethod
    def stream(
        self,
        *,
        step: PipelineStep,
        model: str,
        system: SystemPrompt,
        messages: list[Message],
        max_tokens: int,
        effort: str | None = None,
        thinking: dict[str, object] | None = None,
        tools: list[dict[str, object]] | None = None,
        cache: bool = False,
        budget: RunBudget | None = None,
    ) -> AbstractAsyncContextManager[LLMStream]:
        """Open a streaming call. Same arguments as :meth:`complete` plus optional neutral
        ``cache`` flag (supported providers only)."""

    @abstractmethod
    async def count_tokens(
        self,
        *,
        model: str,
        system: SystemPrompt,
        messages: list[Message],
    ) -> int:
        """Pre-flight token estimate (neutral types only)."""
