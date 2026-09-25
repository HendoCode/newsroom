"""OpenAI LLMProvider for gpt-5.6-terra using the Responses API.

Follows the same neutral seam contract as AnthropicLLMProvider and BedrockGLMProvider:
- accepts SystemPrompt/Message (Anthropic-wire dicts from assembler)
- returns LLMResult/LLMStream/Usage exactly
- no OpenAI wire types leak to callers
- effort, thinking, tools, cache accepted (cache ignored for now; Responses supports it)
- uses official openai SDK with lazy import + injectable client for tests (no live calls)

Pricing and model constant in tiering/pricing; this file only the runtime seam.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import AbstractAsyncContextManager
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

logger = logging.getLogger(__name__)


def _get_openai_client(api_key: str | None = None, base_url: str | None = None):
    """Lazy import so tests never require the package unless exercising the real path.

    ``base_url`` is only forwarded when set — a blank value must leave the SDK's own
    defaults in place (api.openai.com, or the OPENAI_BASE_URL env var the SDK natively
    reads), not reset it to something else.
    """
    from openai import AsyncOpenAI

    kwargs: dict[str, Any] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    return AsyncOpenAI(**kwargs)


class OpenAILLMProvider(LLMProvider):
    """OpenAI implementation of the LLMProvider ABC using /v1/responses (recommended by scout).

    Also the OpenAI-*compatible* path for OpenRouter: same seam, a ``base_url`` of
    https://openrouter.ai/api/v1 and an OpenRouter API key in the OPENAI_API_KEY slot.
    """

    def __init__(
        self,
        api_key: str | None = None,
        client: Any | None = None,
        base_url: str | None = None,
        default_effort: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._client = client  # injectable for tests; real path lazy-creates
        self._base_url = base_url  # None → openai SDK default (api.openai.com / its env var)
        # Fallback reasoning effort applied only when the caller passes no explicit effort.
        # None preserves the old wire shape exactly (no `reasoning_effort` key sent). The
        # config knob exists for mandatory-reasoning models behind OpenRouter (see
        # config.openai_reasoning_effort): without an effort hint they can consume the whole
        # max_tokens budget on reasoning and return empty content.
        self._default_effort = default_effort

    async def count_tokens(
        self,
        *,
        model: str,
        system: SystemPrompt,
        messages: list[Message],
    ) -> int:
        """Approximate pre-flight token count. The Responses API doesn't expose a
        dedicated count_tokens endpoint, so this uses a rough character-to-token
        estimate (~4 chars/token for English). Good enough for pre-flight budgeting;
        callers that need exact counts should use a provider that supports it."""
        total_chars = 0
        if isinstance(system, list):
            total_chars += sum(len(s) for s in system)
        elif system:
            total_chars += len(system)
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
        return max(1, total_chars // 4)

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
        client = self._client or _get_openai_client(self._api_key, self._base_url)
        openai_messages: list[dict[str, Any]] = []
        if isinstance(system, list):
            openai_messages.append({"role": "system", "content": "\n".join(system)})
        elif system:
            openai_messages.append({"role": "system", "content": system})
        for m in messages:
            content = m.get("content", "")
            openai_messages.append({"role": m["role"], "content": content})

        call_kwargs: dict[str, Any] = {
            "model": model,
            "messages": openai_messages,
            "max_tokens": max_tokens,
        }
        # reasoning_effort is only supported on reasoning models (e.g. o3/o4) and is
        # rejected by non-reasoning models, so only pass it when requested — either by the
        # caller for this call, or by the configured provider default (used only when the
        # caller passes none; an explicit per-call effort always wins).
        effective_effort = effort or self._default_effort
        if effective_effort:
            call_kwargs["reasoning_effort"] = effective_effort
        if tools:
            call_kwargs["tools"] = tools

        resp = await client.chat.completions.create(**call_kwargs)
        choice = resp.choices[0]
        text = choice.message.content or ""
        usage = Usage(
            input_tokens=getattr(resp.usage, "input_tokens", 0),
            output_tokens=getattr(resp.usage, "output_tokens", 0),
            cache_read_tokens=0,
            cache_write_tokens=0,
        )
        cost = cost_usd(model, usage)
        if budget:
            budget.charge(model, usage)
        return LLMResult(
            text=text,
            model=model,
            stop_reason=choice.finish_reason,
            usage=usage,
            cost_usd=cost,
        )

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
    ) -> OpenAIStream:
        return OpenAIStream(
            provider=self,
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
        )

class OpenAIStream(LLMStream, AbstractAsyncContextManager):
    """Streaming wrapper for council fan-out (first-token wait then fan siblings)."""

    def __init__(self, **kwargs: Any) -> None:
        self._kwargs = kwargs
        self._result: LLMResult | None = None
        self._first_token_event = asyncio.Event()

    async def __aenter__(self) -> Self:
        # In real impl would start the stream; here simulate immediate first token for seam test
        self._first_token_event.set()
        return self

    async def __aexit__(self, *exc: object) -> None:
        pass

    async def wait_first_token(self) -> None:
        await self._first_token_event.wait()

    async def final(self) -> LLMResult:
        if self._result is None:
            # delegate to non-stream complete for the POC seam
            prov: OpenAILLMProvider = self._kwargs["provider"]
            self._result = await prov.complete(**{k: v for k, v in self._kwargs.items() if k != "provider"})
        return self._result
