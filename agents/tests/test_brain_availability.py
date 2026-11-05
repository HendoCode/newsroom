"""Regression coverage for the brain clone/fetch failure being visible, not silent.

Confirmed defect: ``ensure_brain_available`` used to catch ``GitError`` and ``pass`` with zero
logging, so a broken deploy key (production incident: ``Permission denied (publickey)``) left the
app reporting itself healthy while every brain-backed feature quietly returned nothing. These
tests break a real (non-mocked) clone/pull the same way — pointing ``BRAIN_REPO_URL`` at a remote
that genuinely fails — and assert both that the real underlying error is logged and that
``/api/brain/status`` can tell "not configured" apart from "configured but unreachable" apart from
"connected." If either regresses to a bare ``except GitError: pass``, these tests fail.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.git import BrainAvailability, ensure_brain_available
from app.main import app
from app.secrets import reset_secrets_provider


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    for var in ("BRAIN_REPO_URL", "BRAIN_DEPLOY_KEY", "BRAIN_ROOT", "BRAIN_REF", "MONGO_URL"):
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()
    reset_secrets_provider()
    yield
    get_settings.cache_clear()
    reset_secrets_provider()


@pytest.fixture
def bare_remote(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    return remote


def _seed(bare_remote: Path, tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    seed.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
    (seed / "PANEL.md").write_text("v1\n")
    subprocess.run(["git", "-C", str(seed), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(seed), "-c", "user.email=t@test", "-c", "user.name=test",
         "commit", "-q", "-m", "seed"],
        check=True,
    )
    subprocess.run(["git", "-C", str(seed), "remote", "add", "origin", str(bare_remote)], check=True)
    subprocess.run(["git", "-C", str(seed), "push", "-q", "origin", "HEAD:main"], check=True)


# --- ensure_brain_available: the confirmed defect site --------------------------------------


def test_not_configured_reports_no_attempt_and_logs_nothing(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    settings = Settings(brain_root=str(tmp_path / "brain-root"))  # BRAIN_REPO_URL left unset

    with caplog.at_level(logging.WARNING, logger="app.git"):
        result = ensure_brain_available(settings)

    assert result == BrainAvailability(configured=False, error=None)
    assert caplog.records == []


def test_a_real_clone_failure_is_logged_with_the_real_reason_and_never_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Genuinely break the clone (point at a remote that doesn't exist — no mocking) and prove the
    failure surfaces: this is what a revoked/never-registered deploy key looks like from
    ``ensure_brain_available``'s point of view, minus the SSH transport specifics."""
    broken_remote = tmp_path / "does-not-exist.git"
    monkeypatch.setenv("BRAIN_REPO_URL", str(broken_remote))
    monkeypatch.setenv("BRAIN_DEPLOY_KEY", "-----BEGIN OPENSSH PRIVATE KEY-----\nsecret-marker\n-----END-----")
    root = tmp_path / "brain-root"
    settings = Settings(brain_root=str(root))

    with caplog.at_level(logging.ERROR, logger="app.git"):
        result = ensure_brain_available(settings)

    # The failure is reported, not swallowed...
    assert result.configured is True
    assert result.error is not None
    # ...with the real underlying git failure reason, not a generic placeholder...
    assert str(broken_remote) in result.error
    # ...surfaced through logging too, so it appears in container logs even if nothing ever
    # reads the return value...
    assert len(caplog.records) == 1
    assert caplog.records[0].levelno == logging.ERROR
    assert str(broken_remote) in caplog.records[0].message
    # ...and never leaks the deploy key material into either channel.
    assert "secret-marker" not in (result.error or "")
    assert "secret-marker" not in caplog.text
    # No partial/corrupt clone left behind.
    assert not root.exists()


def test_a_real_pull_failure_on_an_existing_clone_is_logged_and_reported(
    bare_remote: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The clone already exists on disk from a prior successful boot (the common shape once the
    brain has been running a while); this boot's refresh then fails because the remote vanished
    (stands in for e.g. a revoked deploy key on an already-cloned host)."""
    _seed(bare_remote, tmp_path)
    monkeypatch.setenv("BRAIN_REPO_URL", str(bare_remote))
    root = tmp_path / "brain-root"
    settings = Settings(brain_root=str(root))

    first = ensure_brain_available(settings)
    assert first == BrainAvailability(configured=True, error=None)
    assert (root / "PANEL.md").read_text() == "v1\n"

    shutil.rmtree(bare_remote)  # the remote is now unreachable, same shape as revoked credentials

    with caplog.at_level(logging.ERROR, logger="app.git"):
        second = ensure_brain_available(settings)

    assert second.configured is True
    assert second.error is not None
    assert len(caplog.records) == 1
    # Graceful degradation: the existing on-disk content is untouched, not wiped.
    assert (root / "PANEL.md").read_text() == "v1\n"


def test_a_successful_clone_reports_configured_with_no_error(
    bare_remote: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _seed(bare_remote, tmp_path)
    monkeypatch.setenv("BRAIN_REPO_URL", str(bare_remote))
    settings = Settings(brain_root=str(tmp_path / "brain-root"))

    with caplog.at_level(logging.ERROR, logger="app.git"):
        result = ensure_brain_available(settings)

    assert result == BrainAvailability(configured=True, error=None)
    assert caplog.records == []


# --- /api/brain/status: the three states an operator must be able to tell apart --------------


def test_status_route_reports_not_configured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BRAIN_ROOT", str(tmp_path / "nonexistent"))  # no BRAIN_REPO_URL either
    get_settings.cache_clear()

    with TestClient(app) as client:
        body = client.get("/api/brain/status").json()

    assert body["connected"] is False
    assert body["configured"] is False
    assert body["error"] is None


def test_status_route_reports_configured_but_unreachable_with_a_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    broken_remote = tmp_path / "does-not-exist.git"
    monkeypatch.setenv("BRAIN_REPO_URL", str(broken_remote))
    monkeypatch.setenv("BRAIN_ROOT", str(tmp_path / "brain-root"))
    get_settings.cache_clear()

    with TestClient(app) as client:
        body = client.get("/api/brain/status").json()

    assert body["connected"] is False
    assert body["configured"] is True
    assert body["error"]  # non-empty: the real reason, not a bare False→empty collapse
    assert str(broken_remote) in body["error"]


def test_status_route_reports_connected_with_no_error(
    bare_remote: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(bare_remote, tmp_path)
    monkeypatch.setenv("BRAIN_REPO_URL", str(bare_remote))
    monkeypatch.setenv("BRAIN_ROOT", str(tmp_path / "brain-root"))
    get_settings.cache_clear()

    with TestClient(app) as client:
        body = client.get("/api/brain/status").json()

    assert body["connected"] is True
    assert body["configured"] is True
    assert body["error"] is None
    assert body["commit_message"] == "seed"
