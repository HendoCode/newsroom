"""Bedrock-backed LLMProvider for Z.AI GLM models (zai.glm-5 etc) using the Converse API.

Ambient IAM only (instance role or SSO); no API key. Follows the lazy-boto3 + injectable-client
pattern from aws_provider.py and publish/storage.py so tests never touch real AWS.

Wire translation is required: the LLMProvider seam receives Anthropic-wire SystemPrompt/Message
dicts from the assembler (provider.py:31-36). GLM 5 on Bedrock uses the unified Converse shape,
so this provider translates both directions. Bedrock Converse response is mapped back to
LLMResult/Usage exactly as the Anthropic path does.

GLM 5 does not support Anthropic prompt caching, effort, or thinking. The parameters are accepted
(per ABC) and ignored; the seam contract is preserved and no Bedrock-specific types leak out.
Council fan-out still functions but every sibling pays full input cost (no shared prefix cache).

Pricing: see agents/app/llm/pricing.py for the GLM rates (sourced from AWS Bedrock pricing page
https://aws.amazon.com/bedrock/pricing/ as of 2026-08-14: zai.glm-5 $0.0008/1k in, $0.0032/1k out;
zai.glm-4.7 $0.0004/1k in, $0.0016/1k out; zai.glm-4.7-flash $0.0002/1k in, $0.0008/1k out).
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


def _to_bedrock_system(system: SystemPrompt) -> list[dict[str, str]]:
    if isinstance(system, str):
        return [{"text": system}] if system else []
    return [{"text": s} for s in system]


def _to_bedrock_messages(messages: list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        out.append({"role": role, "content": [{"text": content}] if content else []})
    return out


def _from_bedrock_output(output: dict[str, Any]) -> str:
    msg = output.get("message", {})
    parts = msg.get("content", [])
    return "".join(p.get("text", "") for p in parts if isinstance(p, dict))


class _BedrockStream(LLMStream):
    """Async context manager wrapper over bedrock-runtime converse (non-stream for v1)."""

    def __init__(
        self,
        client: Any,
        model: str,
        kwargs: dict[str, Any],
        budget: RunBudget | None,
        *,
        cw_client: Any | None = None,
        step: PipelineStep | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._kwargs = kwargs
        self._budget = budget
        self._cw_client = cw_client
        self._step = step
        self._result: LLMResult | None = None
        self._first_token_event: Any = None  # not real stream in v1

    async def __aenter__(self) -> Self:
        # Blocking call offloaded via thread (same pattern as other I/O in the app)
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(None, lambda: self._client.converse(**self._kwargs))
        text = _from_bedrock_output(raw.get("output", {}))
        usage = raw.get("usage", {})
        u = Usage(
            input_tokens=int(usage.get("inputTokens", 0)),
            output_tokens=int(usage.get("outputTokens", 0)),
            total_tokens=int(usage.get("totalTokens", 0)),
        )
        c = cost_usd(self._model, u)
        self._result = LLMResult(text=text, model=self._model, stop_reason=raw.get("stopReason"), usage=u, cost_usd=c)
        if self._budget is not None:
            self._budget.charge(self._model, u)
        # Emit custom metric for dashboard (swallow+log; never slow or break inference on telemetry failure)
        if self._cw_client is not None and self._step is not None:
            def _emit_metric() -> None:
                try:
                    self._cw_client.put_metric_data(
                        Namespace="CMW/Bedrock",
                        MetricData=[
                            {
                                "MetricName": "InferenceCostUSD",
                                "Value": c,
                                "Unit": "None",
                                "Dimensions": [
                                    {"Name": "Step", "Value": self._step.value},
                                    {"Name": "Model", "Value": self._model},
                                ],
                            }
                        ],
                    )
                except Exception as exc:  # telemetry failure must not affect inference
                    logging.getLogger(__name__).warning("cloudwatch metric emission failed (non-fatal): %s", exc)

            loop.run_in_executor(None, _emit_metric)
        return self

    async def __aexit__(self, *exc: object) -> None:
        pass

    async def wait_first_token(self) -> None:
        # No real streaming in this v1 impl; resolve immediately (fan-out still works, just no cache benefit)
        return

    async def final(self) -> LLMResult:
        assert self._result is not None
        return self._result


class BedrockGLMProvider(LLMProvider):
    """Bedrock Converse implementation for GLM family. Construct via from_settings (ambient IAM)."""

    def __init__(self, client: Any, *, cw_client: Any | None = None, emit_cost_metrics: bool = True) -> None:
        # client is a boto3 bedrock-runtime client (or test double). Injected so no real AWS in tests.
        self._client = client
        self._cw_client = cw_client
        self._emit_cost_metrics = emit_cost_metrics

    @classmethod
    def from_settings(cls, settings: Any | None = None) -> BedrockGLMProvider:
        from app.config import get_settings

        settings = settings or get_settings()
        import boto3  # lazy, same as aws_provider

        # region default is fine; caller can pass a pre-made client for tests / specific region
        client = boto3.client("bedrock-runtime")
        cw_client = None
        if getattr(settings, "emit_bedrock_cost_metrics", True):
            cw_client = boto3.client("cloudwatch")
        return cls(client, cw_client=cw_client, emit_cost_metrics=getattr(settings, "emit_bedrock_cost_metrics", True))

    def _build_converse_kwargs(
        self,
        model: str,
        system: SystemPrompt,
        messages: list[Message],
        max_tokens: int,
        tools: list[dict[str, object]] | None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "modelId": model,
            "system": _to_bedrock_system(system),
            "messages": _to_bedrock_messages(messages),
            "inferenceConfig": {"maxTokens": max_tokens},
        }
        if tools:
            # GLM on Converse does not support Anthropic tool shape; ignore for v1 (research sidecar
            # stays on direct Anthropic path per captain carve-out, so this path never receives tools)
            pass
        return kwargs

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
        if budget is not None:
            budget.check()
        # effort/thinking/cache_control are Anthropic-only; accepted per ABC contract but ignored for GLM
        # (documented in module docstring; no silent drop of caller args)
        kwargs = self._build_converse_kwargs(model, system, messages, max_tokens, tools)
        cw = self._cw_client if self._emit_cost_metrics else None
        return _BedrockStream(self._client, model, kwargs, budget, cw_client=cw, step=step)

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
            budget=budget,
        ) as s:
            return await s.final()

    async def count_tokens(
        self,
        *,
        model: str,
        system: SystemPrompt,
        messages: list[Message],
    ) -> int:
        # Bedrock has no count_tokens equivalent for GLM models. Approximate by naive tokenization
        # (word count / 0.75) so the courtesy readout still works; real usage is captured on the call.
        text = ""
        if isinstance(system, str):
            text += system
        elif isinstance(system, list):
            text += " ".join(system)
        for m in messages:
            c = m.get("content", "")
            if isinstance(c, str):
                text += c
        approx = max(1, int(len(text.split()) / 0.75))
        return approx
