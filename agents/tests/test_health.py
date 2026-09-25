"""Starter pytest suite for the agents service. Proves the /health and /api/status
contracts the BFF depends on, and that secrets never leak into responses."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.config import get_settings
from app.main import app
from app.secrets import reset_secrets_provider

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hermetic settings: clear any ambient provider keys so tests don't depend on the
    developer/CI environment, and reset the cached Settings instance. anthropic_api_key/
    mongo_url now resolve through the secrets shim (app/secrets/), which has its own short-TTL
    cache independent of get_settings' — reset_secrets_provider() must be cleared alongside it or
    a value set by an earlier test would still be served."""
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "MONGO_URL", "LLM_BACKEND"):
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()
    reset_secrets_provider()
    yield
    get_settings.cache_clear()
    reset_secrets_provider()


def test_health_ok() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok", "service": "agents", "version": __version__}


def test_status_reports_seams() -> None:
    resp = client.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "agents"
    assert body["orchestration"] == "stub"
    assert "oracle" in body["pipeline_stages"]
    assert body["llm_configured"] is False  # no Mongo means no live provider object
    assert body["llm_error"] is not None
    assert body["mongo_configured"] is False


def test_status_reports_mongo_ready_when_url_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONGO_URL", "mongodb://mongo:27017/content_machine")
    get_settings.cache_clear()
    body = client.get("/api/status").json()
    assert body["mongo_configured"] is True


def test_status_reports_llm_ready_when_key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    # Live readiness requires both a configured backend and a real provider object. The
    # object is only constructed in the Mongo-configured lifespan branch, so we need a fresh
    # TestClient after setting the env vars (changing env does not re-run the lifespan).
    monkeypatch.setenv("MONGO_URL", "mongodb://mongo:27017/content_machine")
    monkeypatch.setenv("LLM_BACKEND", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    get_settings.cache_clear()
    with TestClient(app) as fresh_client:
        body = fresh_client.get("/api/status").json()
    assert body["llm_configured"] is True
    assert body.get("llm_error") is None


def test_status_never_leaks_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    # Even with a key configured, no secret VALUE or secret field name appears in responses (D14).
    monkeypatch.setenv("ANTHROPIC_API_KEY", "super-secret-value")
    get_settings.cache_clear()
    raw = client.get("/api/status").text.lower()
    assert "super-secret-value" not in raw
    for forbidden in ("api_key", "apikey", "mongo_url", "secret", "password"):
        assert forbidden not in raw


def test_build_returns_baked_metadata_or_safe_fallback() -> None:
    """The /build route returns only build identity (baked at image build via Dockerfile ARG).
    In source tree (no baked file) it safely falls back; in a real image the baked JSON is served.
    Local verification that would catch missing metadata: `docker build --build-arg BUILD_COMMIT=$(git rev-parse HEAD) -t cmw-agents-test ./agents && docker run --rm cmw-agents-test cat /app/cmw-build.json`
    """
    resp = client.get("/build")
    assert resp.status_code == 200
    body = resp.json()
    assert body["component"] == "agents"
    assert "commit" in body
    assert "shortCommit" in body
    assert "builtAt" in body
    # In test env (no baked file) we expect the unknown fallback; real image has real commit.
    assert body["commit"] in ("unknown",) or len(body["commit"]) >= 7
