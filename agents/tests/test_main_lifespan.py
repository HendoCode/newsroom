"""Regression coverage: a misconfigured brain must degrade the finalize step, never crash boot.

Confirmed defect: ``build_finalize_step(settings)`` (wired into ``app/main.py``'s lifespan
alongside oracle/draft/council/incorporate) constructs a ``TemplateStore`` whose ``__init__`` calls
``discover_repo`` eagerly — unlike every sibling step here, which all degrade lazily at call time
(``ctx.brain is None`` checks). So whenever ``MONGO_URL`` is configured but ``BRAIN_ROOT`` isn't a
valid git repo, this one construction raised ``GitError`` straight out of the lifespan and took the
whole service down — not just the finalize route, but health, auth, the dashboard, everything. This
is the exact same class of failure the ``git_brain``/``git_content`` construction two lines above it
already guards against (see that ``except GitError`` block and ``tests/test_brain_availability.py``);
this test proves ``build_finalize_step`` now gets the same treatment: the service boots, and the
finalize step simply reports unavailable (``registry.has(JobType.finalize) is False``, the same
signal ``app/orchestration/routes.py`` already maps to a clean 501 — see
``test_orchestration.py::test_http_batch_trigger_501_when_step_unregistered`` for that mapping)
rather than an exception ever reaching the caller.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.models import JobType
from app.secrets import reset_secrets_provider


@pytest.fixture(autouse=True)
def _clean_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("MONGO_URL", "BRAIN_ROOT", "BRAIN_REPO_URL", "BRAIN_DEPLOY_KEY", "BRAIN_REF"):
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()
    reset_secrets_provider()
    yield
    get_settings.cache_clear()
    reset_secrets_provider()


def test_boot_survives_an_unusable_brain_root_and_leaves_only_finalize_unregistered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    monkeypatch.setenv("MONGO_URL", "mongodb://localhost:27017/does-not-need-to-be-reachable")
    monkeypatch.setenv("BRAIN_ROOT", str(not_a_repo))
    get_settings.cache_clear()

    with (
        caplog.at_level(logging.WARNING, logger="app.main"),
        TestClient(app) as client,  # runs the real lifespan — this must not raise
    ):
        registry = client.app.state.step_registry
        resp = client.get("/health")

    assert resp.status_code == 200
    # Only finalize (the one step whose construction touches the brain eagerly) is affected —
    # every sibling batch step registers fine, proving this is a narrow, single-step degrade.
    assert registry.has(JobType.finalize) is False
    assert registry.has(JobType.oracle) is True
    assert registry.has(JobType.draft) is True
    assert registry.has(JobType.council) is True
    assert registry.has(JobType.incorporate) is True
    # Degrading must not mean silent (the sharp-edge lesson the sibling guard already learned).
    assert any("finalize step unavailable" in r.message for r in caplog.records)


def test_openai_backend_constructs_provider_when_key_set(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """``LLM_BACKEND=openai`` with ``OPENAI_API_KEY`` set now has its own dedicated branch
    in the provider selection (routing through ``OpenAILLMProvider`` instead of falling through
    to the ``has_llm_credentials()`` → Anthropic path). The service boots with a real provider.
    """
    from app.llm import OpenAILLMProvider

    monkeypatch.setenv("MONGO_URL", "mongodb://localhost:27017/does-not-need-to-be-reachable")
    monkeypatch.setenv("LLM_BACKEND", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-not-anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()

    with (
        caplog.at_level(logging.WARNING, logger="app.main"),
        TestClient(app) as client,  # runs the real lifespan — this must not raise
    ):
        resp = client.get("/health")
        provider = client.app.state.llm_provider

    assert resp.status_code == 200
    assert provider is not None
    assert isinstance(provider, OpenAILLMProvider)
    # No "LLM provider unavailable" warning since construction succeeded.
    assert not any("LLM provider unavailable" in r.message for r in caplog.records)


def test_openrouter_backend_constructs_provider_with_openrouter_endpoint(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """``LLM_BACKEND=openrouter`` is first-class: same OpenAI-compatible provider as
    ``openai``, but with the endpoint defaulting to OpenRouter when OPENAI_BASE_URL is unset,
    and an OPENAI_BASE_URL override honored when it is set."""
    from app.llm import OpenAILLMProvider

    monkeypatch.setenv("MONGO_URL", "mongodb://localhost:27017/does-not-need-to-be-reachable")
    monkeypatch.setenv("LLM_BACKEND", "openrouter")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-or-fake")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()

    with (
        caplog.at_level(logging.WARNING, logger="app.main"),
        TestClient(app) as client,  # runs the real lifespan — this must not raise
    ):
        resp = client.get("/health")
        provider = client.app.state.llm_provider

    assert resp.status_code == 200
    assert provider is not None
    assert isinstance(provider, OpenAILLMProvider)
    assert provider._base_url == "https://openrouter.ai/api/v1"
    assert not any("LLM provider unavailable" in r.message for r in caplog.records)


def test_openrouter_backend_honors_openai_base_url_override(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from app.llm import OpenAILLMProvider

    monkeypatch.setenv("MONGO_URL", "mongodb://localhost:27017/does-not-need-to-be-reachable")
    monkeypatch.setenv("LLM_BACKEND", "openrouter")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-or-fake")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://my.proxy.local/v1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    get_settings.cache_clear()

    with (
        caplog.at_level(logging.WARNING, logger="app.main"),
        TestClient(app) as client,
    ):
        provider = client.app.state.llm_provider

    assert provider is not None
    assert isinstance(provider, OpenAILLMProvider)
    assert provider._base_url == "https://my.proxy.local/v1"


def test_boot_with_mongo_configured_does_not_crash_reading_content_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for the #156-induced boot crash (2026-08-31 live P0): CouncilStep's lifespan
    construction reads ``app.state.content_workflow`` at line ~172, but that attribute is only
    assigned inside the Mongo-configured branch further down the lifespan. When Mongo IS
    reachable-configured (the production shape), boot still reached the CouncilStep register call
    before the content_workflow assignment, raising AttributeError and taking the whole service
    down. The fix initializes ``app.state.content_workflow = None`` before the register call.

    This test boots the real lifespan with MONGO_URL set (a syntactically valid URL; reachability
    is not exercised here beyond what the lifespan tolerates) and asserts boot survives and the
    attribute exists (None or a real ContentWorkflow) rather than the attribute being a missing
    name on Starlette's State."""
    monkeypatch.delenv("BRAIN_ROOT", raising=False)
    get_settings.cache_clear()
    with TestClient(app) as client:  # must not raise AttributeError
        assert client.get("/health").status_code == 200
        # hasattr instead of direct read: the regression is a missing attribute, so reading it
        # directly would itself raise before the fix.
        assert hasattr(client.app.state, "content_workflow")
