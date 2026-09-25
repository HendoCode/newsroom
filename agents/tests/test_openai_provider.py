"""OpenAI provider seam tests (no live calls; injectable client pattern)."""

import pytest

from app.llm import OpenAILLMProvider, PipelineStep
from app.llm.provider import LLMProvider


def test_openai_provider_satisfies_interface():
    """The new provider implements the ABC exactly (swappability contract)."""
    p = OpenAILLMProvider(api_key="sk-fake")
    assert isinstance(p, LLMProvider)


def test_openai_client_base_url_forwarding():
    """The OpenAI-compatible seam honors an explicit base_url (the OpenRouter path), and a
    blank base_url leaves the SDK's own default in place rather than resetting it."""
    from app.llm.openai_provider import _get_openai_client

    client = _get_openai_client("sk-fake", "https://openrouter.ai/api/v1")
    assert str(client.base_url) == "https://openrouter.ai/api/v1/"

    client_default = _get_openai_client("sk-fake", None)
    assert str(client_default.base_url) == "https://api.openai.com/v1/"


@pytest.mark.asyncio
async def test_openai_complete_uses_injected_client(monkeypatch):
    """No real SDK call; fake client proves the lazy + injectable path uses the Chat
    Completions wire shape (OpenAI-compatible endpoints like OpenRouter do not support the
    Responses API) and that reasoning_effort is omitted by default."""
    captured = {}

    class FakeChoice:
        finish_reason = "stop"
        message = type("M", (), {"content": "ok"})()

    class FakeResp:
        choices = [FakeChoice()]
        usage = type("U", (), {"input_tokens": 10, "output_tokens": 5})()

    class FakeCompletions:
        @staticmethod
        async def create(**kw):
            captured["kwargs"] = kw
            return FakeResp()

    class FakeClient:
        chat = type("Chat", (), {"completions": FakeCompletions()})()

    p = OpenAILLMProvider(client=FakeClient())
    res = await p.complete(
        step=PipelineStep.DRAFT,
        model="gpt-5.6-terra",
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=64,
    )
    assert res.text == "ok"
    assert res.model == "gpt-5.6-terra"
    assert captured["kwargs"]["model"] == "gpt-5.6-terra"
    assert "reasoning_effort" not in captured["kwargs"]
    assert captured["kwargs"]["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]


@pytest.mark.asyncio
async def test_openai_complete_passes_reasoning_effort_when_requested():
    """reasoning_effort is only supported on OpenAI-native reasoning models, so it is
    passed only when explicitly requested (and omitted otherwise for OpenRouter compat)."""
    captured = {}

    class FakeChoice:
        finish_reason = "stop"
        message = type("M", (), {"content": "ok"})()

    class FakeResp:
        choices = [FakeChoice()]
        usage = type("U", (), {"input_tokens": 1, "output_tokens": 1})()

    class FakeCompletions:
        @staticmethod
        async def create(**kw):
            captured["kwargs"] = kw
            return FakeResp()

    class FakeClient:
        chat = type("Chat", (), {"completions": FakeCompletions()})()

    p = OpenAILLMProvider(client=FakeClient())
    await p.complete(
        step=PipelineStep.DRAFT,
        model="o3-mini",
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=64,
        effort="high",
    )
    assert captured["kwargs"]["reasoning_effort"] == "high"


def _fake_client(captured: dict):
    class FakeChoice:
        finish_reason = "stop"
        message = type("M", (), {"content": "ok"})()

    class FakeResp:
        choices = [FakeChoice()]
        usage = type("U", (), {"input_tokens": 1, "output_tokens": 1})()

    class FakeCompletions:
        @staticmethod
        async def create(**kw):
            captured["kwargs"] = kw
            return FakeResp()

    return type("FakeClient", (), {"chat": type("Chat", (), {"completions": FakeCompletions()})()})()


@pytest.mark.asyncio
async def test_openai_complete_applies_default_effort_when_caller_passes_none():
    """The configured provider-level default effort is sent when the caller does not request
    one — the knob that keeps mandatory-reasoning OpenRouter models (no disable switch) from
    burning a step's whole max_tokens budget on reasoning and returning empty content."""
    captured: dict = {}
    p = OpenAILLMProvider(client=_fake_client(captured), default_effort="low")
    await p.complete(
        step=PipelineStep.INTERVIEW_QUESTION,
        model="z-ai/glm-5.3-flash",
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=300,
    )
    assert captured["kwargs"]["reasoning_effort"] == "low"


@pytest.mark.asyncio
async def test_openai_complete_explicit_effort_beats_default():
    """A per-call effort always wins over the provider default — the default is a floor for
    steps that never set one, never an override of a step's own choice."""
    captured: dict = {}
    p = OpenAILLMProvider(client=_fake_client(captured), default_effort="low")
    await p.complete(
        step=PipelineStep.DRAFT,
        model="z-ai/glm-5.3-flash",
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=8192,
        effort="high",
    )
    assert captured["kwargs"]["reasoning_effort"] == "high"


@pytest.mark.asyncio
async def test_openai_complete_no_default_effort_keeps_wire_shape():
    """default_effort=None (the unset config default) preserves the exact old wire shape:
    no reasoning_effort key is sent at all (OpenRouter non-reasoning models reject it)."""
    captured: dict = {}
    p = OpenAILLMProvider(client=_fake_client(captured), default_effort=None)
    await p.complete(
        step=PipelineStep.DRAFT,
        model="gpt-5.6-terra",
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=64,
    )
    assert "reasoning_effort" not in captured["kwargs"]
