"""Coverage for `POST /api/brain/pull` — the on-demand refresh added so a running instance can
pick up a hand-nurtured brain edit without recreating the container.

Same discipline as `test_brain_availability.py`: real (non-mocked) local bare repos standing in
for the GitHub remote, exercised through a real `TestClient(app)` lifespan boot, no mocking of
git itself.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
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


def _seed(bare_remote: Path, tmp_path: Path, content: str = "v1\n") -> None:
    seed = tmp_path / "seed"
    seed.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
    (seed / "PANEL.md").write_text(content)
    subprocess.run(["git", "-C", str(seed), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(seed), "-c", "user.email=t@test", "-c", "user.name=test",
         "commit", "-q", "-m", "seed"],
        check=True,
    )
    subprocess.run(["git", "-C", str(seed), "remote", "add", "origin", str(bare_remote)], check=True)
    subprocess.run(["git", "-C", str(seed), "push", "-q", "origin", "HEAD:main"], check=True)


def _push_update(bare_remote: Path, tmp_path: Path, message: str, content: str) -> str:
    """Simulate a hand-nurtured brain edit landing on the remote via an independent clone (never
    the app's own clone), and return the new commit sha."""
    other = tmp_path / "other-clone"
    subprocess.run(["git", "clone", "-q", str(bare_remote), str(other)], check=True)
    (other / "PANEL.md").write_text(content)
    subprocess.run(["git", "-C", str(other), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(other), "-c", "user.email=t@test", "-c", "user.name=test",
         "commit", "-q", "-m", message],
        check=True,
    )
    subprocess.run(["git", "-C", str(other), "push", "-q", "origin", "HEAD:main"], check=True)
    sha = subprocess.run(
        ["git", "-C", str(other), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    return sha


def test_pull_route_503s_when_brain_unavailable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BRAIN_ROOT", str(tmp_path / "nonexistent"))  # no BRAIN_REPO_URL either
    get_settings.cache_clear()

    with TestClient(app) as client:
        resp = client.post("/api/brain/pull")

    assert resp.status_code == 503


def test_pull_route_noops_without_a_remote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A self-managed local-dev clone (no BRAIN_REPO_URL, developer manages their own origin — or
    none at all here) has nothing to pull from; this must report a clean no-op, not a failure."""
    root = tmp_path / "brain-root"
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    (root / "PANEL.md").write_text("v1\n")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=t@test", "-c", "user.name=test",
         "commit", "-q", "-m", "seed"],
        check=True,
    )
    monkeypatch.setenv("BRAIN_ROOT", str(root))
    get_settings.cache_clear()

    with TestClient(app) as client:
        resp = client.post("/api/brain/pull")

    assert resp.status_code == 200
    body = resp.json()
    assert body["pulled"] is False
    assert body["remote_url"] is None


def test_pull_route_fast_forwards_and_reports_the_new_commit(
    bare_remote: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(bare_remote, tmp_path)
    monkeypatch.setenv("BRAIN_REPO_URL", str(bare_remote))
    monkeypatch.setenv("BRAIN_ROOT", str(tmp_path / "brain-root"))
    get_settings.cache_clear()

    with TestClient(app) as client:
        # Boot cloned at "seed"; a hand-nurtured edit lands on the remote afterward, same as a
        # human editing content-machine-brain directly on GitHub/another checkout.
        new_sha = _push_update(bare_remote, tmp_path, "hand-nurtured edit", "v2\n")

        before = client.get("/api/brain/status").json()
        assert before["commit_message"] == "seed"

        resp = client.post("/api/brain/pull")
        assert resp.status_code == 200
        body = resp.json()
        assert body["pulled"] is True
        assert body["commit_sha"] == new_sha
        assert body["commit_message"] == "hand-nurtured edit"

        # No restart needed: the same running process now serves the updated content.
        assert (tmp_path / "brain-root" / "PANEL.md").read_text() == "v2\n"
        after = client.get("/api/brain/status").json()
        assert after["commit_sha"] == new_sha
        assert after["error"] is None


def test_pull_route_reports_failure_without_corrupting_local_state(
    bare_remote: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _seed(bare_remote, tmp_path)
    monkeypatch.setenv("BRAIN_REPO_URL", str(bare_remote))
    monkeypatch.setenv("BRAIN_ROOT", str(tmp_path / "brain-root"))
    get_settings.cache_clear()

    with TestClient(app) as client:
        before = client.get("/api/brain/status").json()
        assert before["error"] is None

        shutil.rmtree(bare_remote)  # remote now unreachable, same shape as a revoked deploy key

        with caplog.at_level(logging.ERROR, logger="app.main"):
            resp = client.post("/api/brain/pull")

        # Loud, not silent: a real error status...
        assert resp.status_code == 502
        assert str(bare_remote) in resp.json()["detail"]
        # ...logged...
        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.ERROR
        # ...and the on-disk clone is left exactly as it was, not corrupted or wiped.
        assert (tmp_path / "brain-root" / "PANEL.md").read_text() == "v1\n"

        # /api/brain/status keeps reflecting the failure after the pull call returns, not just
        # the response body of the pull itself.
        after = client.get("/api/brain/status").json()
        assert after["error"] is not None
        assert str(bare_remote) in after["error"]
        assert after["commit_message"] == "seed"  # unchanged
