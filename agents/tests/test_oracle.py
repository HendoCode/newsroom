"""Oracle tests (§1.8; context report §4; engine/1-oracle.md).

Covers, per the acceptance criteria:
- retrieve → rank → persist end to end, for both entry points (A open scan / B narrative-biased);
- ranked spikes persisted with ``status=proposed``, attributed to creator + origin, carrying a
  convergence score;
- the top-K bound is enforced and logged (never a silent "scanned everything");
- the lookback window is a genuine per-run parameter;
- the Opus tier is used for ranking, and retrieval goes through the lake's query API only;
- the ``BatchStep``/``JobRunner`` integration (Oracle jobs are pieceless);
- the ranking-response parser (JSON fence tolerance, hallucinated-id filtering, malformed input).

Zero external deps: the lake runs on the in-memory Mongo + local hybrid index (``lake`` fixture);
the LLM path runs on a tiny fake provider (no ``anthropic`` package, no key, no network); the Git
brain reads the fixture brain copied into a throwaway repo (``git_brain``).
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta

import pytest

from app.git import GitBrain
from app.lake import ContentLake, ContentLakeItem, ContentMetadata
from app.lake.query import RankedCandidate
from app.llm.budget import RunBudget
from app.llm.pricing import Usage, cost_usd
from app.llm.provider import LLMProvider, LLMResult
from app.llm.tiering import MODEL_GLM5
from app.models import (
    DistributionIntent,
    Job,
    JobType,
    Narrative,
    OracleEntryMode,
    OracleRunParams,
)
from app.models.common import utcnow
from app.models.source import SourceClassification
from app.models.spike import SpikeOriginKind, SpikeStatus
from app.oracle import OracleService, OracleStep, build_user_prompt, parse_ranked_spikes
from app.oracle.service import DEFAULT_TOP_K_NARRATIVE, DEFAULT_TOP_K_OPEN_SCAN
from app.orchestration.jobs import JobRunner
from app.orchestration.retry import PermanentStepError
from app.orchestration.steps import StepRegistry
from app.repositories import WorkStateStore

# --- fakes -----------------------------------------------------------------------------------


class FakeOracleProvider(LLMProvider):
    """Returns a preset ranked-spikes JSON payload and records every call it receives."""

    def __init__(self, spikes: list[dict] | None = None, usage: Usage | None = None) -> None:
        self.response_text = json.dumps(spikes if spikes is not None else [])
        self.usage = usage or Usage(input_tokens=500, output_tokens=200)
        self.calls: list[dict] = []

    async def complete(self, *, step, model, system, messages, max_tokens, effort=None, cache=False, budget=None):
        if budget is not None:
            budget.check()
        self.calls.append(
            {"step": step, "model": model, "system": system, "messages": messages}
        )
        if budget is not None:
            budget.charge(model, self.usage)
        return LLMResult(
            text=self.response_text,
            model=model,
            stop_reason="end_turn",
            usage=self.usage,
            cost_usd=cost_usd(model, self.usage),
        )

    def stream(self, **kwargs):
        raise NotImplementedError("the oracle only uses complete()")

    async def count_tokens(self, *, model, system, messages):
        return 0


class BoomProvider(LLMProvider):
    """Fails the test if the LLM is ever called (proves no-candidates skips the call)."""

    async def complete(self, **kwargs):
        # accepts cache etc via **
        raise AssertionError("provider.complete() must not be called with no candidates")

    def stream(self, **kwargs):
        raise AssertionError("provider.stream() must not be called with no candidates")

    async def count_tokens(self, **kwargs):
        return 0


def _item(raw: str, *, author: str | None = None, content_date=None, tags=None) -> ContentLakeItem:
    return ContentLakeItem(
        raw_content=raw,
        source_id="src-1",
        classification=SourceClassification.scraped_periodically,
        metadata=ContentMetadata(author=author, tags=tags or [], content_date=content_date),
    )


def _spike_payload(headline: str, source_item_ids: list[str] | None = None) -> dict:
    return {
        "headline": headline,
        "convergence_score": 8.5,
        "customer_partner": "Acme",
        "outcome_metric": "2x throughput",
        "rank_rationale": "named customer + outcome",
        "convergence_note": None,
        "source_item_ids": source_item_ids or [],
    }


def _budget() -> RunBudget:
    return RunBudget()


# --- ranking: prompt shape + response parsing ------------------------------------------------


def test_build_user_prompt_and_parse_roundtrip() -> None:
    item = ContentLakeItem(
        raw_content="Crown Castle deal closed, cut latency 40%",
        source_id="src-1",
        classification=SourceClassification.scraped_periodically,
    )
    item.id = "item-1"
    candidate = RankedCandidate(item=item, score=0.0, semantic_score=0.0, keyword_score=0.0)
    params = OracleRunParams(entry_mode=OracleEntryMode.open_scan, voice="demo-mira")

    prompt = build_user_prompt([candidate], params, None, top_k=40)
    assert "Entry mode: open-scan" in prompt
    assert "Entry A: an open scan" in prompt
    assert "id=item-1" in prompt
    assert "top_k=40" in prompt

    payload = [_spike_payload("Crown Castle latency win", ["item-1", "hallucinated-id"])]
    ranked = parse_ranked_spikes(json.dumps(payload), candidate_ids=["item-1"])
    assert len(ranked) == 1
    assert ranked[0].headline == "Crown Castle latency win"
    assert ranked[0].convergence_score == 8.5
    # a hallucinated id never lands in the persisted result.
    assert ranked[0].source_item_ids == ["item-1"]


def test_parse_ranked_spikes_resolves_integer_positional_index() -> None:
    # Captured production failure: the ranking model returned the bracketed position (an int,
    # e.g. 0) instead of the string id the prompt asked for, and Pydantic rejected it outright
    # ("source_item_ids.0 Input should be a valid string [type=string_type, input_value=0,
    # input_type=int]") before a single spike could be persisted. An integer reference must
    # resolve to the real id at that position, not crash validation or get stored as "0".
    payload = [_spike_payload("Crown Castle latency win", [0])]
    ranked = parse_ranked_spikes(json.dumps(payload), candidate_ids=["item-1", "item-2"])
    assert len(ranked) == 1
    assert ranked[0].source_item_ids == ["item-1"]


def test_parse_ranked_spikes_mixed_index_and_string_id_and_drops_unresolvable() -> None:
    payload = [_spike_payload("x", [1, "item-1", "hallucinated-id", 99])]
    ranked = parse_ranked_spikes(json.dumps(payload), candidate_ids=["item-1", "item-2"])
    # index 1 -> item-2, the real string id item-1 passes through, the hallucinated string id and
    # the out-of-range index 99 are both dropped rather than guessed at.
    assert ranked[0].source_item_ids == ["item-2", "item-1"]


def test_build_user_prompt_entry_b_carries_the_narrative_bias() -> None:
    item = ContentLakeItem(
        raw_content="pricing story", source_id="s", classification=SourceClassification.scraped_periodically
    )
    item.id = "item-2"
    candidate = RankedCandidate(item=item, score=0.0, semantic_score=0.0, keyword_score=0.0)
    narrative = Narrative(
        author="s@x", seed_text="our new pricing model",
        intent=DistributionIntent(audience="CFOs", angle="cost savings"),
    )
    params = OracleRunParams(
        entry_mode=OracleEntryMode.narrative, voice="demo-mira", narrative_id="n-1"
    )

    prompt = build_user_prompt([candidate], params, narrative, top_k=20)
    assert "Entry B" in prompt
    assert "our new pricing model" in prompt
    assert "CFOs" in prompt
    assert "cost savings" in prompt
    assert "do not hard-filter" in prompt


def test_parse_ranked_spikes_tolerates_json_fence() -> None:
    fenced = "```json\n[{\"headline\": \"x\", \"convergence_score\": 1.0}]\n```"
    ranked = parse_ranked_spikes(fenced)
    assert len(ranked) == 1 and ranked[0].headline == "x"


def test_parse_ranked_spikes_recovers_json_embedded_in_prose() -> None:
    text = 'Here is my ranking:\n[{"headline": "x", "convergence_score": 1.0}]\nDone.'
    ranked = parse_ranked_spikes(text)
    assert len(ranked) == 1


def test_parse_ranked_spikes_invalid_json_raises_permanent_step_error() -> None:
    with pytest.raises(PermanentStepError):
        parse_ranked_spikes("not json at all, no brackets either")


def test_parse_ranked_spikes_non_array_raises() -> None:
    with pytest.raises(PermanentStepError):
        parse_ranked_spikes(json.dumps({"not": "a list"}))


def test_parse_ranked_spikes_validation_error_raises() -> None:
    # missing the required "headline" field.
    with pytest.raises(PermanentStepError):
        parse_ranked_spikes(json.dumps([{"convergence_score": 5.0}]))


def test_oracle_run_params_narrative_entry_requires_narrative_id() -> None:
    with pytest.raises(ValueError, match="narrative_id"):
        OracleRunParams(entry_mode=OracleEntryMode.narrative, voice="demo-mira")


# --- OracleService: entry points, attribution, top-K cap, lookback ---------------------------


async def test_entry_a_persists_spikes_attributed_to_creator_and_oracle_run(
    store: WorkStateStore, lake: ContentLake, git_brain: GitBrain
) -> None:
    stored = await lake.ingest(_item("Crown Castle story with a metric", author="demo-mira"))
    provider = FakeOracleProvider([_spike_payload("Crown Castle win", [stored.id])])
    service = OracleService(store=store, lake=lake, provider=provider, brain=git_brain)
    job = await store.jobs.insert(Job(type=JobType.oracle, triggered_by="demo-mira@x"))
    params = OracleRunParams(entry_mode=OracleEntryMode.open_scan, voice="demo-mira")

    outcome = await service.run(job=job, params=params, budget=_budget())

    assert len(outcome.spikes) == 1
    spike = outcome.spikes[0]
    assert spike.status == SpikeStatus.proposed
    assert spike.creator == "demo-mira@x"
    assert spike.origin.kind == SpikeOriginKind.oracle_run
    assert spike.origin.ref == job.id
    assert spike.convergence_score == 8.5
    assert spike.source_ids == [stored.id]
    # persisted for real — reads back from the store.
    fetched = await store.spikes.get(spike.id)
    assert fetched is not None and fetched.headline == "Crown Castle win"

    # the Opus tier ranked it, and retrieval only ever went through the lake query API.
    assert len(provider.calls) == 1
    assert provider.calls[0]["model"] == MODEL_GLM5  # ORACLE now GLM5 live default


async def test_entry_b_biases_attribution_to_narrative_and_stamps_oracle_run_id(
    store: WorkStateStore, lake: ContentLake, git_brain: GitBrain
) -> None:
    stored = await lake.ingest(_item("A pricing story for CFOs", author="demo-mira"))
    narrative = await store.narratives.insert(
        Narrative(
            author="demo-mira@x",
            seed_text="our new pricing model",
            intent=DistributionIntent(audience="CFOs", angle="cost savings"),
        )
    )
    provider = FakeOracleProvider([_spike_payload("Pricing win", [stored.id])])
    service = OracleService(store=store, lake=lake, provider=provider, brain=git_brain)
    job = await store.jobs.insert(Job(type=JobType.oracle, triggered_by="demo-mira@x"))
    params = OracleRunParams(
        entry_mode=OracleEntryMode.narrative, voice="demo-mira", narrative_id=narrative.id
    )

    outcome = await service.run(job=job, params=params, budget=_budget())

    assert len(outcome.spikes) == 1
    spike = outcome.spikes[0]
    # Entry B attributes origin to the narrative (not the job), and carries its intent forward.
    assert spike.origin.kind == SpikeOriginKind.narrative
    assert spike.origin.ref == narrative.id
    assert spike.intent is not None and spike.intent.angle == "cost savings"
    # the narrative is stamped with the run that resulted from it.
    updated_narrative = await store.narratives.get(narrative.id)
    assert updated_narrative is not None and updated_narrative.oracle_run_id == job.id
    assert outcome.top_k == DEFAULT_TOP_K_NARRATIVE


async def test_entry_b_missing_narrative_raises_permanent_step_error(
    store: WorkStateStore, lake: ContentLake, git_brain: GitBrain
) -> None:
    service = OracleService(store=store, lake=lake, provider=FakeOracleProvider(), brain=git_brain)
    job = await store.jobs.insert(Job(type=JobType.oracle))
    params = OracleRunParams(
        entry_mode=OracleEntryMode.narrative, voice="demo-mira", narrative_id="does-not-exist"
    )
    with pytest.raises(PermanentStepError):
        await service.run(job=job, params=params, budget=_budget())


async def test_top_k_cap_enforced_and_logged(
    store: WorkStateStore, lake: ContentLake, git_brain: GitBrain, caplog: pytest.LogCaptureFixture
) -> None:
    for i in range(5):
        await lake.ingest(_item(f"story number {i} with some substance"))
    provider = FakeOracleProvider([_spike_payload("one of many")])
    service = OracleService(store=store, lake=lake, provider=provider, brain=git_brain)
    job = await store.jobs.insert(Job(type=JobType.oracle, triggered_by="s@x"))
    params = OracleRunParams(entry_mode=OracleEntryMode.open_scan, voice="demo-mira", top_k=2)

    with caplog.at_level(logging.INFO, logger="app.oracle.service"):
        outcome = await service.run(job=job, params=params, budget=_budget())

    # the cap actually bound retrieval (5 ingested, top_k=2)...
    assert outcome.top_k == 2
    assert outcome.candidates_considered <= 2
    # ...and it is never a silent "scanned everything": logged AND noted.
    assert any("top_k=2" in r.message for r in caplog.records)
    assert any("capped at top_k=2" in n for n in outcome.notes)


async def test_default_top_k_differs_open_scan_vs_narrative(
    store: WorkStateStore, lake: ContentLake, git_brain: GitBrain
) -> None:
    await lake.ingest(_item("a single story"))
    narrative = await store.narratives.insert(
        Narrative(author="s@x", seed_text="seed", intent=DistributionIntent())
    )
    service = OracleService(
        store=store, lake=lake, provider=FakeOracleProvider([]), brain=git_brain
    )

    job_a = await store.jobs.insert(Job(type=JobType.oracle))
    outcome_a = await service.run(
        job=job_a,
        params=OracleRunParams(entry_mode=OracleEntryMode.open_scan, voice="demo-mira"),
        budget=_budget(),
    )
    assert outcome_a.top_k == DEFAULT_TOP_K_OPEN_SCAN

    job_b = await store.jobs.insert(Job(type=JobType.oracle))
    outcome_b = await service.run(
        job=job_b,
        params=OracleRunParams(
            entry_mode=OracleEntryMode.narrative, voice="demo-mira", narrative_id=narrative.id
        ),
        budget=_budget(),
    )
    assert outcome_b.top_k == DEFAULT_TOP_K_NARRATIVE


async def test_lookback_window_is_a_per_run_parameter(
    store: WorkStateStore, lake: ContentLake, git_brain: GitBrain
) -> None:
    await lake.ingest(_item("ancient story", content_date=utcnow() - timedelta(days=30)))
    await lake.ingest(_item("fresh story", content_date=utcnow() - timedelta(days=1)))
    service = OracleService(
        store=store, lake=lake, provider=FakeOracleProvider([]), brain=git_brain
    )

    job = await store.jobs.insert(Job(type=JobType.oracle))
    narrow = await service.run(
        job=job,
        params=OracleRunParams(
            entry_mode=OracleEntryMode.open_scan, voice="demo-mira", lookback_days=7
        ),
        budget=_budget(),
    )
    assert narrow.candidates_considered == 1  # only the fresh story survives a 7-day window

    job2 = await store.jobs.insert(Job(type=JobType.oracle))
    wide = await service.run(
        job=job2,
        params=OracleRunParams(
            entry_mode=OracleEntryMode.open_scan, voice="demo-mira", lookback_days=60
        ),
        budget=_budget(),
    )
    assert wide.candidates_considered == 2  # both survive a 60-day window


async def test_no_candidates_skips_the_llm_call(
    store: WorkStateStore, lake: ContentLake, git_brain: GitBrain
) -> None:
    # empty lake, no candidates → the run must not spend an LLM call.
    service = OracleService(store=store, lake=lake, provider=BoomProvider(), brain=git_brain)
    job = await store.jobs.insert(Job(type=JobType.oracle))
    params = OracleRunParams(entry_mode=OracleEntryMode.open_scan, voice="demo-mira")

    outcome = await service.run(job=job, params=params, budget=_budget())

    assert outcome.spikes == []
    assert outcome.candidates_considered == 0
    assert any("no candidates" in n for n in outcome.notes)


# --- OracleStep + JobRunner: the pieceless batch-step integration -----------------------------


async def test_oracle_step_runs_pieceless_through_the_job_runner(
    store: WorkStateStore, lake: ContentLake, git_brain: GitBrain
) -> None:
    stored = await lake.ingest(_item("a convergent story", author="demo-mira"))
    provider = FakeOracleProvider([_spike_payload("headline", [stored.id])])
    registry = StepRegistry()
    registry.register(OracleStep())
    runner = JobRunner(store, registry, provider=provider, brain=git_brain, lake=lake)

    job = await runner.enqueue(
        JobType.oracle,
        triggered_by="demo-mira@x",
        oracle_params=OracleRunParams(entry_mode=OracleEntryMode.open_scan, voice="demo-mira"),
    )
    assert job.piece_id is None  # Oracle jobs run before any Piece exists (§1.8)

    job = await runner.run(job.id)

    assert job.status == "succeeded"
    assert job.cost > 0
    spikes = await store.spikes.find({"origin.ref": job.id})
    assert len(spikes) == 1


async def test_oracle_step_requires_lake_and_fails_deterministically(
    store: WorkStateStore, git_brain: GitBrain
) -> None:
    registry = StepRegistry()
    registry.register(OracleStep())
    # No lake wired at all — a configuration error, not a transient one.
    runner = JobRunner(store, registry, provider=FakeOracleProvider(), brain=git_brain, lake=None)
    job = await runner.enqueue(
        JobType.oracle,
        oracle_params=OracleRunParams(entry_mode=OracleEntryMode.open_scan, voice="demo-mira"),
    )

    job = await runner.run(job.id)

    assert job.status == "failed"
    assert job.attempts == 1  # a permanent/config error is never retried
    assert job.error is not None and job.error.code == "permanent"


async def test_oracle_step_requires_oracle_params(
    store: WorkStateStore, lake: ContentLake, git_brain: GitBrain
) -> None:
    registry = StepRegistry()
    registry.register(OracleStep())
    runner = JobRunner(store, registry, provider=FakeOracleProvider(), brain=git_brain, lake=lake)
    job = await runner.enqueue(JobType.oracle)  # no oracle_params

    job = await runner.run(job.id)

    assert job.status == "failed"
    assert job.error is not None and job.error.code == "permanent"


# --- REST surface ------------------------------------------------------------------------------


def _wire_oracle_app(store: WorkStateStore, lake: ContentLake, git_brain: GitBrain, provider):
    from app.main import app

    registry = StepRegistry()
    registry.register(OracleStep())
    app.state.job_runner = JobRunner(store, registry, provider=provider, brain=git_brain, lake=lake)
    return app


async def _http(app):
    from httpx import ASGITransport, AsyncClient

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_http_oracle_run_succeeds(
    store: WorkStateStore, lake: ContentLake, git_brain: GitBrain
) -> None:
    stored = await lake.ingest(_item("a convergent story", author="demo-mira"))
    provider = FakeOracleProvider([_spike_payload("headline", [stored.id])])
    app = _wire_oracle_app(store, lake, git_brain, provider)
    async with await _http(app) as client:
        resp = await client.post(
            "/api/oracle/run",
            json={"entry_mode": "open-scan", "voice": "demo-mira", "triggered_by": "s@x"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "succeeded"
    assert body["cost_usd"] > 0


async def test_http_oracle_narrative_entry_without_id_is_400(
    store: WorkStateStore, lake: ContentLake, git_brain: GitBrain
) -> None:
    app = _wire_oracle_app(store, lake, git_brain, FakeOracleProvider())
    async with await _http(app) as client:
        resp = await client.post(
            "/api/oracle/run", json={"entry_mode": "narrative", "voice": "demo-mira"}
        )
    assert resp.status_code == 400


def test_http_oracle_503_when_unconfigured() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    app.state.job_runner = None
    resp = TestClient(app).post("/api/oracle/run", json={"voice": "demo-mira"})
    assert resp.status_code == 503


async def test_http_oracle_501_when_step_unregistered(
    store: WorkStateStore, lake: ContentLake, git_brain: GitBrain
) -> None:
    from app.main import app

    app.state.job_runner = JobRunner(store, StepRegistry(), lake=lake)  # no Oracle step registered
    async with await _http(app) as client:
        resp = await client.post("/api/oracle/run", json={"voice": "demo-mira"})
    assert resp.status_code == 501
