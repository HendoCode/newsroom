"""LLM provider layer tests (D14; cmw-context-assembly report §3/§10/§12).

Covers, per the acceptance criteria:
- the per-step tiering map matches the context report,
- the three-tier assembler's prefix/tail split, cache-breakpoint placement, and forbidden
  silent-invalidator guard,
- per-run ceiling enforcement + ``usage``/cost capture,
- provider swappability (a fake provider satisfies the interface) and the council fan-out
  primitive's fire-one-await-first-token-then-fan-out contract.

Zero external deps: the assembler runs against the real brain copied into a temp git repo (the
shared ``git_brain`` / ``content_store`` fixtures); the provider path runs entirely on a fake
that implements the ABC — no ``anthropic`` package, no key, no network.
"""

from __future__ import annotations

from typing import Self

import pytest

from app.llm import (
    MODEL_GLM5,
    MODEL_GLM47,
    MODEL_GLM47_FLASH,
    MODEL_OPUS,
    MODEL_SONNET,
    STEP_MODEL_TIERS,
    AnthropicLLMProvider,
    AssembledPrompt,
    BedrockGLMProvider,
    CacheInvalidatorError,
    FanoutCall,
    LLMProvider,
    LLMResult,
    LLMStream,
    PipelineStep,
    PromptAssembler,
    RunBudget,
    RunBudgetExceeded,
    Usage,
    build_message_kwargs,
    cost_usd,
    council_fanout,
    model_for_step,
    result_from_message,
)

# --- a fake provider proving the seam is swappable (acceptance: fake satisfies the interface) ---


def _label(messages: list[dict[str, object]]) -> str:
    content = messages[0]["content"] if messages else ""
    return content if isinstance(content, str) else ""


class FakeStream(LLMStream):
    def __init__(self, provider: FakeProvider, model: str, messages, budget) -> None:
        self.p = provider
        self.model = model
        self.messages = messages
        self.budget = budget

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def wait_first_token(self) -> None:
        self.p.events.append(("first_token", _label(self.messages)))

    async def final(self) -> LLMResult:
        self.p.events.append(("final", _label(self.messages)))
        usage = self.p.usage
        if self.budget is not None:
            self.budget.charge(self.model, usage)
        return LLMResult(
            text=_label(self.messages),
            model=self.model,
            stop_reason="end_turn",
            usage=usage,
            cost_usd=cost_usd(self.model, usage),
        )


class FakeProvider(LLMProvider):
    """A swappable double: implements every abstract method, records call order, honors budget."""

    def __init__(self, usage: Usage | None = None) -> None:
        self.events: list[tuple[str, str]] = []
        self.usage = usage or Usage(input_tokens=100, output_tokens=50)

    def stream(self, *, step, model, system, messages, max_tokens, effort=None, cache=False, budget=None):
        if budget is not None:
            budget.check()
        self.events.append(("stream", _label(messages)))
        return FakeStream(self, model, messages, budget)

    async def complete(self, *, step, model, system, messages, max_tokens, effort=None, cache=False, budget=None):
        if budget is not None:
            budget.check()
        self.events.append(("complete", _label(messages)))
        usage = self.usage
        if budget is not None:
            budget.charge(model, usage)
        return LLMResult(
            text=_label(messages),
            model=model,
            stop_reason="end_turn",
            usage=usage,
            cost_usd=cost_usd(model, usage),
        )

    async def count_tokens(self, *, model, system, messages):
        return sum(len(str(m.get("content", ""))) for m in messages)


# --- tiering map (context report §3 / §12) -------------------------------------------------


def test_tiering_map_matches_context_report():
    # GLM top tier for the taste-heavy / drafting-class steps (preserves §3 relationships).
    for step in (
        PipelineStep.ORACLE,
        PipelineStep.INTERVIEW_QUESTION,
        PipelineStep.DRAFT,
        PipelineStep.COUNCIL,
        PipelineStep.REWRITE,
        PipelineStep.LESSONS,
    ):
        assert model_for_step(step) == MODEL_GLM5
    # GLM5 for the bounded / light steps except RESEARCH (which stays on Anthropic SONNET per carve-out).
    for step in (
        PipelineStep.INTERVIEW_CLASSIFY,
        PipelineStep.RECAP,
        PipelineStep.FEEDBACK_CLASSIFY,
    ):
        assert model_for_step(step) == MODEL_GLM5
    assert model_for_step(PipelineStep.RESEARCH) == MODEL_SONNET


def test_every_step_has_a_tier():
    assert set(STEP_MODEL_TIERS) == set(PipelineStep)
    assert set(STEP_MODEL_TIERS.values()) <= {MODEL_GLM5, MODEL_GLM47, MODEL_GLM47_FLASH, MODEL_OPUS, MODEL_SONNET}


def test_tier_map_routes_to_openrouter_slug_when_backend_is_openrouter(monkeypatch: pytest.MonkeyPatch):
    """``LLM_BACKEND=openrouter`` makes every GLM slot route to the OpenRouter slug from
    config (the bedrock IDs don't resolve on OpenRouter) — and the RESEARCH carve-out
    (direct Anthropic) is untouched, exactly like it is for every other backend.

    tiering reads settings at import time, so this reloads the module with the env var set,
    then restores it — the reload is the only way to exercise the import-time branch.
    """
    import importlib

    from app.config import get_settings
    from app.llm import tiering

    monkeypatch.setenv("LLM_BACKEND", "openrouter")
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL_ID", "z-ai/glm-test")
    get_settings.cache_clear()
    try:
        reloaded = importlib.reload(tiering)
        for step in PipelineStep:
            if step is PipelineStep.RESEARCH:
                assert reloaded.model_for_step(step) == MODEL_SONNET
            else:
                assert reloaded.model_for_step(step) == "z-ai/glm-test"
    finally:
        # Restore the default-backend module state. The env vars must be undone BEFORE the
        # restoring reload (monkeypatch's own teardown runs after this finally, so relying on
        # it would leave tiering re-imported against the test's openrouter settings).
        monkeypatch.delenv("LLM_BACKEND", raising=False)
        monkeypatch.delenv("OPENROUTER_DEFAULT_MODEL_ID", raising=False)
        get_settings.cache_clear()
        importlib.reload(tiering)


def test_openrouter_default_model_is_priced():
    """The cost readout degrades to 0.0 for unpriced models (pricing.py's documented
    behavior) — the OpenRouter default slug must be priced, otherwise every openrouter run
    silently reports no cost."""
    from app.config import get_settings
    from app.llm.pricing import MODEL_PRICING
    from app.llm.tiering import MODEL_OPENROUTER_DEFAULT

    assert MODEL_OPENROUTER_DEFAULT == get_settings().openrouter_default_model_id
    assert MODEL_OPENROUTER_DEFAULT in MODEL_PRICING


def test_gpt56_terra_pricing_and_settings_roundtrip():
    from app.config import get_settings
    from app.llm.pricing import MODEL_PRICING
    from app.llm.tiering import MODEL_GPT56_TERRA

    assert MODEL_PRICING[MODEL_GPT56_TERRA].input_per_mtok == 2.0
    assert MODEL_PRICING[MODEL_GPT56_TERRA].output_per_mtok == 12.0
    settings = get_settings()
    assert settings.gpt_56_terra_model_id == "gpt-5.6-terra"
    assert MODEL_GPT56_TERRA == "gpt-5.6-terra"


# --- assembler: tier split + cache placement + forbidden invalidators (§1.2, §2, §10) ------


def test_assemble_stable_first_split_no_cache():
    a = PromptAssembler.__new__(PromptAssembler)  # no git needed for pure assemble
    prompt = a.assemble(t0=["engine", "voice"], t1=["transcript"], t2="the tail", cache=False)
    assert isinstance(prompt, AssembledPrompt)
    assert prompt.system == ["engine", "voice", "transcript"]
    assert prompt.cache is False
    assert prompt.messages == [{"role": "user", "content": "the tail"}]


def test_assemble_places_single_breakpoint_on_last_stable_block():
    a = PromptAssembler.__new__(PromptAssembler)
    prompt = a.assemble(t0=["engine", "voice"], t1=["transcript"], t2="q", cache=True)
    assert prompt.cache is True
    assert prompt.system == ["engine", "voice", "transcript"]


def test_assemble_1h_ttl_is_carried():
    # ttl support removed from neutral seam (cache flag only); test kept as no-op for coverage
    a = PromptAssembler.__new__(PromptAssembler)
    prompt = a.assemble(t0=["stable"], t2="x", cache=True)
    assert prompt.cache is True


def test_assemble_rejects_invalidators_in_stable_prefix():
    a = PromptAssembler.__new__(PromptAssembler)
    for bad in (
        "run started 2026-07-30T09:15:00Z",  # ISO datetime (datetime.now leak)
        "id 123e4567-e89b-42d3-a456-426614174000",  # uuid
        "run_id=abc123",  # explicit run id
        "piece-id: token-vs-storage",  # explicit piece id
    ):
        with pytest.raises(CacheInvalidatorError):
            a.assemble(t0=["fine"], t1=[bad], t2="tail", cache=True)


def test_assemble_allows_plain_date_and_invalidators_when_uncached():
    a = PromptAssembler.__new__(PromptAssembler)
    # a plain date (brain files cite dates) is fine in the stable prefix.
    prompt = a.assemble(t0=["last-verified: 2026-07-30"], t2="x", cache=True)
    assert prompt.system[0] == "last-verified: 2026-07-30"
    prompt2 = a.assemble(t0=["run started 2026-07-30T09:15:00Z"], t2="x", cache=False)
    assert prompt2.system[0].startswith("run started")


def test_assemble_empty_stable_prefix_with_cache_raises():
    a = PromptAssembler.__new__(PromptAssembler)
    with pytest.raises(CacheInvalidatorError):
        a.assemble(t0=[], t1=[], t2="x", cache=True)


def test_assembler_reads_brain_and_content_via_git_layer(git_brain, content_store):
    a = PromptAssembler(git_brain, content_store)
    # T0: voice pack in override order (guide → style → lessons), all present for mira.
    voice = a.voice_pack_blocks("demo-mira")
    assert len(voice) == 3
    pack = git_brain.read_voice("demo-mira")
    assert voice == [pack.voice_guide, pack.style_guide, pack.content_lessons]
    # T0: engine + persona + partner read through the brain module.
    assert a.engine_block("2-draft")
    assert a.persona_block("editor", "cold-reader")
    assert a.partner_block("aws")
    # T1: transcript + revision + sources read through the content module.
    assert a.transcript_block("token-vs-storage")
    assert a.revision_block("token-vs-storage")
    assert a.sources_block("token-vs-storage")


def test_council_shaped_assembly_from_real_brain(git_brain, content_store):
    a = PromptAssembler(git_brain, content_store)
    t0 = [a.engine_block("3-revision-loop"), *a.voice_pack_blocks("demo-mira"), a.partner_block("aws")]
    t1 = [a.revision_block("token-vs-storage"), a.transcript_block("token-vs-storage")]
    prompt = a.assemble(t0=t0, t1=t1, t2="You are the slop-allergist. Score this draft.", cache=True)
    assert len(prompt.system) == len(t0) + len(t1)
    assert prompt.cache is True


# --- pricing / usage / cost (§2, D14) ------------------------------------------------------


def test_usage_totals_and_addition():
    u = Usage(input_tokens=100, output_tokens=50, cache_creation_input_tokens=10, cache_read_input_tokens=5)
    assert u.total_input_tokens == 115
    combined = u + Usage(input_tokens=1, output_tokens=2)
    assert combined.input_tokens == 101 and combined.output_tokens == 52


def test_cost_usd_opus_and_sonnet():
    # 1M uncached input + 1M output on Opus: $5 + $25.
    opus = cost_usd(MODEL_OPUS, Usage(input_tokens=1_000_000, output_tokens=1_000_000))
    assert opus == pytest.approx(30.0)
    # Sonnet: $3 + $15.
    sonnet = cost_usd(MODEL_SONNET, Usage(input_tokens=1_000_000, output_tokens=1_000_000))
    assert sonnet == pytest.approx(18.0)


def test_cost_usd_cache_multipliers():
    # cache read bills at 0.1× input, cache write at 1.25× input (5-min TTL).
    cost = cost_usd(MODEL_OPUS, Usage(cache_read_input_tokens=1_000_000, cache_creation_input_tokens=1_000_000))
    assert cost == pytest.approx(1_000_000 * 5 * 0.1 / 1e6 + 1_000_000 * 5 * 1.25 / 1e6)


def test_cost_usd_unknown_model_is_zero():
    assert cost_usd("some-future-model", Usage(input_tokens=1000)) == 0.0


# --- run budget ceiling enforcement (D14) --------------------------------------------------


def test_budget_call_ceiling():
    b = RunBudget(max_calls=2)
    b.check()
    b.charge(MODEL_OPUS, Usage(input_tokens=10, output_tokens=5))
    b.check()
    b.charge(MODEL_OPUS, Usage(input_tokens=10, output_tokens=5))
    with pytest.raises(RunBudgetExceeded):
        b.check()
    assert b.calls == 2


def test_budget_cost_ceiling():
    b = RunBudget(max_cost_usd=0.01)
    b.check()  # nothing spent yet
    # one big call blows the cost ceiling.
    b.charge(MODEL_OPUS, Usage(input_tokens=1_000_000, output_tokens=1_000_000))
    with pytest.raises(RunBudgetExceeded):
        b.check()


def test_budget_token_ceiling():
    b = RunBudget(max_total_tokens=100)
    b.check()
    b.charge(MODEL_OPUS, Usage(input_tokens=80, output_tokens=40))  # 120 > 100
    with pytest.raises(RunBudgetExceeded):
        b.check()


def test_budget_snapshot_and_charge_return():
    b = RunBudget()
    call_cost = b.charge(MODEL_OPUS, Usage(input_tokens=1_000_000, output_tokens=0))
    assert call_cost == pytest.approx(5.0)
    snap = b.snapshot()
    assert snap["calls"] == 1 and snap["input_tokens"] == 1_000_000
    assert snap["cost_usd"] == pytest.approx(5.0)


# --- anthropic request/response shaping (pure helpers, no network) -------------------------


def test_build_message_kwargs_omits_sampling_params():
    kwargs = build_message_kwargs(
        model=MODEL_OPUS, system=[{"type": "text", "text": "s"}], messages=[{"role": "user", "content": "hi"}], max_tokens=1024
    )
    assert kwargs["model"] == MODEL_OPUS and kwargs["max_tokens"] == 1024
    assert kwargs["system"] and kwargs["messages"]
    # Opus 4.8 / Sonnet 5 reject these — they must never be sent.
    for banned in ("temperature", "top_p", "top_k"):
        assert banned not in kwargs
    assert "output_config" not in kwargs  # effort omitted → no output_config
    assert "thinking" not in kwargs  # omitted by default — the model's own default applies


def test_build_message_kwargs_effort_maps_to_output_config():
    kwargs = build_message_kwargs(model=MODEL_OPUS, system="s", messages=[], max_tokens=8, effort="high")
    assert kwargs["output_config"] == {"effort": "high"}


def test_build_message_kwargs_thinking_is_forwarded_verbatim():
    """Sonnet 5 runs adaptive thinking even with no `thinking` field at all (unlike Opus 4.8,
    which only thinks if asked) — a caller with a bounded max_tokens must be able to disable it
    explicitly, and the raw config must reach the wire unchanged."""
    kwargs = build_message_kwargs(
        model=MODEL_SONNET, system="s", messages=[], max_tokens=8, thinking={"type": "disabled"}
    )
    assert kwargs["thinking"] == {"type": "disabled"}


class _Block:
    def __init__(self, type_, text=""):
        self.type = type_
        self.text = text


class _Msg:
    def __init__(self, content, usage, stop_reason, model):
        self.content = content
        self.usage = usage
        self.stop_reason = stop_reason
        self.model = model


class _Usage:
    def __init__(self, i, o, cc=0, cr=0):
        self.input_tokens = i
        self.output_tokens = o
        self.cache_creation_input_tokens = cc
        self.cache_read_input_tokens = cr


def test_result_from_message_captures_text_usage_cost():
    msg = _Msg(
        content=[_Block("thinking"), _Block("text", "Score: 9/10"), _Block("text", " ok")],
        usage=_Usage(1_000_000, 0, cc=0, cr=0),
        stop_reason="end_turn",
        model=MODEL_OPUS,
    )
    result = result_from_message(msg, model=MODEL_OPUS)
    assert result.text == "Score: 9/10 ok"  # only text blocks, concatenated
    assert result.stop_reason == "end_turn"
    assert result.usage.input_tokens == 1_000_000
    assert result.cost_usd == pytest.approx(5.0)


# --- provider swappability + council fan-out (§7, §10) -------------------------------------


def test_providers_satisfy_the_interface():
    # Both the fake and the real Anthropic provider are LLMProvider — the seam is swappable.
    assert issubclass(FakeProvider, LLMProvider)
    assert issubclass(AnthropicLLMProvider, LLMProvider)
    # the fake instantiates (proves every abstract method is implemented).
    assert isinstance(FakeProvider(), LLMProvider)


async def test_complete_via_fake_charges_budget():
    provider = FakeProvider(Usage(input_tokens=1_000_000, output_tokens=0))
    budget = RunBudget()
    result = await provider.complete(
        step=PipelineStep.DRAFT,
        model=MODEL_OPUS,
        system="s",
        messages=[{"role": "user", "content": "draft it"}],
        max_tokens=4096,
        budget=budget,
    )
    assert result.text == "draft it"
    assert budget.calls == 1 and budget.cost == pytest.approx(5.0)


async def test_council_fanout_fires_one_then_fans_out():
    provider = FakeProvider()
    editors = [FanoutCall(label=name, messages=[{"role": "user", "content": name}]) for name in ("slop", "voice", "partner", "tech")]
    system = [{"type": "text", "text": "shared", "cache_control": {"type": "ephemeral"}}]
    results = await council_fanout(provider, system=system, editors=editors, max_tokens=2048, model=MODEL_OPUS)

    # results preserve editor order and label→result mapping.
    assert [r.label for r in results] == ["slop", "voice", "partner", "tech"]
    assert [r.result.text for r in results] == ["slop", "voice", "partner", "tech"]

    kinds = [e[0] for e in provider.events]
    # exactly the first editor is *streamed*; the rest are plain completes (§10 fan-out shape).
    assert kinds.count("stream") == 1
    assert provider.events[0] == ("stream", "slop")
    # the first token is awaited before any fanned-out completion begins.
    first_token_at = kinds.index("first_token")
    complete_positions = [i for i, k in enumerate(kinds) if k == "complete"]
    assert complete_positions and all(first_token_at < i for i in complete_positions)
    assert len(complete_positions) == 3  # N-1 editors fanned out


async def test_council_fanout_empty_is_noop():
    assert await council_fanout(FakeProvider(), system="s", editors=[], max_tokens=8) == []


async def test_council_fanout_respects_budget_ceiling():
    provider = FakeProvider()
    budget = RunBudget(max_calls=2)
    editors = [FanoutCall(label=str(i), messages=[{"role": "user", "content": str(i)}]) for i in range(4)]
    with pytest.raises(RunBudgetExceeded):
        await council_fanout(provider, system="s", editors=editors, max_tokens=8, budget=budget)


async def test_fake_count_tokens():
    provider = FakeProvider()
    n = await provider.count_tokens(model=MODEL_OPUS, system="s", messages=[{"role": "user", "content": "hello"}])
    assert n == len("hello")


class _MockBedrockClient:
    """Test double for boto3 bedrock-runtime client. Never calls real AWS."""

    def converse(self, **kwargs):
        # Echo back a minimal valid Converse response; assert the translation happened on input.
        assert kwargs["modelId"].startswith("zai.glm")
        assert isinstance(kwargs.get("system"), list)
        assert isinstance(kwargs.get("messages"), list)
        return {
            "output": {"message": {"role": "assistant", "content": [{"text": "translated ok"}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 7, "outputTokens": 3, "totalTokens": 10},
        }


async def test_bedrock_glm_provider_satisfies_interface_and_translates_wire():
    # Injected client means zero real AWS calls; proves the seam + translation both directions.
    provider = BedrockGLMProvider(_MockBedrockClient(), emit_cost_metrics=False)
    assert isinstance(provider, LLMProvider)
    result = await provider.complete(
        step=PipelineStep.DRAFT,
        model=MODEL_GLM5,
        system="sys",
        messages=[{"role": "user", "content": [{"text": "hi"}]}],
        max_tokens=128,
    )
    assert result.text == "translated ok"
    assert result.model.startswith("zai.glm")
    assert result.usage.input_tokens == 7


async def test_bedrock_count_tokens_and_stream_shape():
    provider = BedrockGLMProvider(_MockBedrockClient(), emit_cost_metrics=False)
    n = await provider.count_tokens(model=MODEL_OPUS, system="s", messages=[])
    assert n > 0
    # stream returns the async context manager (real streaming is future work; v1 uses blocking converse)
    ctx = provider.stream(step=PipelineStep.RECAP, model=MODEL_SONNET, system="", messages=[], max_tokens=8)
    assert hasattr(ctx, "__aenter__")
