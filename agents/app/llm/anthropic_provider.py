"""First-party Anthropic implementation of :class:`LLMProvider` (open-decisions Item 1).

Thin, direct, one server-side ``ANTHROPIC_API_KEY`` (never client-exposed — read from
``app.config.Settings``, D14). Every call goes through the streaming path so a large ``max_tokens``
(a ~10K draft) never trips the SDK's non-streaming timeout guard and the council fan-out gets a
real first-token signal from the same code.

Request shaping is intentionally minimal: model + max_tokens + the assembler's ``system`` /
``messages`` + optional ``effort``. No ``temperature`` / ``top_p`` / ``top_k`` and no fixed
thinking budget — Opus 4.8 / Sonnet 5 reject all of them (400). The pure helpers
:func:`build_message_kwargs` and :func:`result_from_message` are split out so request/response
shaping is unit-testable without a network call or an API key.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, Self

from app.llm.budget import RunBudget
from app.llm.pricing import Usage, cost_usd
from app.llm.provider import (
    LLMProvider,
    LLMResult,
    LLMStream,
    Message,
    SystemPrompt,
)
from app.llm.tiering import PipelineStep


def build_message_kwargs(
    *,
    model: str,
    system: SystemPrompt,
    messages: list[Message],
    max_tokens: int,
    effort: str | None = None,
    thinking: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    cache: bool = False,
) -> dict[str, Any]:
    """Build Anthropic wire kwargs from neutral seam types. Wraps plain system text into
    Anthropic blocks and inserts cache_control on last block when cache=True.
    """
    if isinstance(system, str):
        sys_blocks: list[dict[str, Any]] = [{"type": "text", "text": system}] if system else []
    else:
        sys_blocks = [{"type": "text", "text": s} for s in system]
    if cache and sys_blocks:
        sys_blocks[-1]["cache_control"] = {"type": "ephemeral"}

    # messages content is already plain str from neutral seam
    wire_messages = [{"role": m["role"], "content": m["content"]} for m in messages]

    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": sys_blocks,
        "messages": wire_messages,
    }
    if effort is not None:
        kwargs["output_config"] = {"effort": effort}
    if thinking is not None:
        kwargs["thinking"] = thinking
    if tools is not None:
        kwargs["tools"] = tools
    return kwargs


def _usage_from(raw: Any) -> Usage:
    """Capture the four ``usage`` counters (D14), tolerant of missing cache fields."""
    return Usage(
        input_tokens=getattr(raw, "input_tokens", 0) or 0,
        output_tokens=getattr(raw, "output_tokens", 0) or 0,
        cache_creation_input_tokens=getattr(raw, "cache_creation_input_tokens", 0) or 0,
        cache_read_input_tokens=getattr(raw, "cache_read_input_tokens", 0) or 0,
    )


def result_from_message(message: Any, *, model: str) -> LLMResult:
    """Turn a final Anthropic ``Message`` into an :class:`LLMResult` (text + usage + cost).

    Pure: pass a real SDK message or a lightweight stand-in with ``.content`` / ``.stop_reason`` /
    ``.usage``. Concatenates the response's text blocks; captures ``usage``; computes the courtesy
    cost. ``message.model`` (the model that actually served) wins over the requested ``model``.
    """
    text = "".join(
        getattr(block, "text", "")
        for block in getattr(message, "content", [])
        if getattr(block, "type", None) == "text"
    )
    served_model = getattr(message, "model", None) or model
    usage = _usage_from(getattr(message, "usage", None))
    return LLMResult(
        text=text,
        model=served_model,
        stop_reason=getattr(message, "stop_reason", None),
        usage=usage,
        cost_usd=cost_usd(served_model, usage),
    )


class _AnthropicStream(LLMStream):
    """Drives one SDK stream in a background task, exposing the first-token signal the council
    fan-out needs (§10) and the final result. Charges ``budget`` once, on completion."""

    def __init__(
        self,
        stream_cm: Any,
        *,
        model: str,
        budget: RunBudget | None,
    ) -> None:
        self._cm = stream_cm
        self._model = model
        self._budget = budget
        self._first_token = asyncio.Event()
        self._driver: asyncio.Task[LLMResult] | None = None

    async def __aenter__(self) -> Self:
        self._stream = await self._cm.__aenter__()
        self._driver = asyncio.create_task(self._drive())
        return self

    async def __aexit__(self, *exc: object) -> None:
        # If the caller awaited final(), the driver is already done. If they left the block early
        # (or an exception unwound it), cancel the background driver so it doesn't dangle, then
        # close the SDK stream — never masking the caller's own exception.
        if self._driver is not None and not self._driver.done():
            self._driver.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._driver
        await self._cm.__aexit__(*exc)

    async def _drive(self) -> LLMResult:
        try:
            async for event in self._stream:
                if getattr(event, "type", None) == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    if getattr(delta, "type", None) == "text_delta":
                        self._first_token.set()
            message = await self._stream.get_final_message()
        finally:
            # A call that streamed no text (or errored) must still release fan-out siblings.
            self._first_token.set()
        result = result_from_message(message, model=self._model)
        if self._budget is not None:
            self._budget.charge(result.model, result.usage)
        return result

    async def wait_first_token(self) -> None:
        await self._first_token.wait()

    async def final(self) -> LLMResult:
        assert self._driver is not None, "stream not entered"
        return await self._driver


class AnthropicLLMProvider(LLMProvider):
    """Direct first-party Anthropic provider. Construct once; share across the service."""

    def __init__(self, client: Any) -> None:
        # ``client`` is an ``anthropic.AsyncAnthropic``. Injected (not built here) so the key stays
        # in config and tests/other providers can pass a double. Use :func:`from_settings`.
        self._client = client

    @classmethod
    def from_settings(cls, settings: Any | None = None) -> AnthropicLLMProvider:
        """Build from ``Settings`` using the single server-side ``ANTHROPIC_API_KEY`` (D14).

        Imports the SDK lazily so the rest of the service (and most tests) need neither the
        ``anthropic`` package installed nor a key configured.
        """
        from anthropic import AsyncAnthropic

        from app.config import get_settings

        settings = settings or get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not configured; the LLM layer needs the single "
                "server-side company key (D14)."
            )
        return cls(AsyncAnthropic(api_key=settings.anthropic_api_key))

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
    ) -> _AnthropicStream:
        if budget is not None:
            budget.check()
        kwargs = build_message_kwargs(
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            effort=effort,
            thinking=thinking,
            tools=tools,
            cache=cache,
        )
        return _AnthropicStream(
            self._client.messages.stream(**kwargs), model=model, budget=budget
        )

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
        async with self.stream(
            step=step,
            model=model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
            effort=effort,
            thinking=thinking,
            tools=tools,
            cache=cache,
            budget=budget,
        ) as stream:
            return await stream.final()

    async def count_tokens(
        self,
        *,
        model: str,
        system: SystemPrompt,
        messages: list[Message],
    ) -> int:
        if isinstance(system, str):
            sys_blocks: list[dict[str, Any]] = [{"type": "text", "text": system}] if system else []
        else:
            sys_blocks = [{"type": "text", "text": s} for s in system]
        wire_messages = [{"role": m["role"], "content": m["content"]} for m in messages]
        result = await self._client.messages.count_tokens(
            model=model, system=sys_blocks, messages=wire_messages
        )
        return int(result.input_tokens)
