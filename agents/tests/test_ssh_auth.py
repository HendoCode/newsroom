"""SSH deploy-key auth (agents/app/git/ssh_auth.py + the GitRepo/config wiring around it).

Everything here is mocked or filesystem-only — no real network call, no real GitHub key. The
``SshDeployKey`` tests exercise real file writes (permissions/content matter for security), but
never touch a socket; the ``GitRepo``/``ensure_brain_available``/``open_brain`` tests fully mock
``subprocess.run`` (or the ``GitRepo.clone`` seam) to prove the deploy key is threaded through to
the right place, without ever shelling out to a real ``ssh``/``git`` network operation.
"""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path

import pytest

from app.config import get_settings
from app.git import GitError, ensure_brain_available, open_brain, open_content_store
from app.git.repo import GitRepo
from app.git.ssh_auth import SshDeployKey, get_ssh_deploy_key
from app.secrets import reset_secrets_provider

_FAKE_KEY = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\nnot-a-real-key-just-test-fixture-data\n"
    "-----END OPENSSH PRIVATE KEY-----"
)


# --- SshDeployKey: on-disk materialization ---------------------------------------------------


def test_writes_private_key_with_owner_only_permissions() -> None:
    key = SshDeployKey(_FAKE_KEY)
    assert key.key_path.read_text(encoding="utf-8") == _FAKE_KEY + "\n"
    mode = stat.S_IMODE(key.key_path.stat().st_mode)
    assert mode == stat.S_IRUSR | stat.S_IWUSR  # 0600 — group/other get no access


def test_known_hosts_pins_githubs_published_host_keys() -> None:
    key = SshDeployKey(_FAKE_KEY)
    known_hosts = key.known_hosts_path.read_text(encoding="utf-8")
    assert "github.com ssh-ed25519 " in known_hosts
    assert "github.com ecdsa-sha2-nistp256 " in known_hosts
    assert "github.com ssh-rsa " in known_hosts


def test_git_ssh_command_is_strict_and_scoped_to_this_key() -> None:
    key = SshDeployKey(_FAKE_KEY)
    command = key.git_ssh_command
    assert f"-i {key.key_path}" in command
    assert f"-o UserKnownHostsFile={key.known_hosts_path}" in command
    assert "-o StrictHostKeyChecking=yes" in command
    assert "-o IdentitiesOnly=yes" in command
    assert "-o BatchMode=yes" in command


def test_get_ssh_deploy_key_caches_by_key_value() -> None:
    a1 = get_ssh_deploy_key("test-cache-key-alpha")
    a2 = get_ssh_deploy_key("test-cache-key-alpha")
    assert a1 is a2  # same key material -> the same on-disk materialization, not rewritten


# --- GitRepo: the GIT_SSH_COMMAND env override on network-touching ops ------------------------


class _FakeCompletedProcess:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_push_carries_deploy_key_ssh_command_in_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[list[str], dict]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> _FakeCompletedProcess:
        calls.append((cmd, kwargs))
        first_arg = cmd[3] if len(cmd) > 3 else None
        if first_arg == "remote" and len(cmd) == 4:
            return _FakeCompletedProcess(stdout="origin\n")
        if first_arg == "rev-parse":
            return _FakeCompletedProcess(stdout="main\n")
        return _FakeCompletedProcess()

    monkeypatch.setattr(subprocess, "run", fake_run)
    repo = GitRepo(tmp_path, ssh_deploy_key=_FAKE_KEY)
    repo.push()

    push_calls = [c for c in calls if len(c[0]) > 3 and c[0][3] == "push"]
    assert len(push_calls) == 1
    env = push_calls[0][1]["env"]
    assert env is not None and "GIT_SSH_COMMAND" in env
    assert "StrictHostKeyChecking=yes" in env["GIT_SSH_COMMAND"]

    # Local ops (has_remote/current_branch) never need the deploy key's env override.
    remote_call = next(c for c in calls if c[0][3:4] == ["remote"])
    assert remote_call[1]["env"] is None


def test_push_uses_ambient_env_without_a_configured_deploy_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[list[str], dict]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> _FakeCompletedProcess:
        calls.append((cmd, kwargs))
        first_arg = cmd[3] if len(cmd) > 3 else None
        if first_arg == "remote" and len(cmd) == 4:
            return _FakeCompletedProcess(stdout="origin\n")
        if first_arg == "rev-parse":
            return _FakeCompletedProcess(stdout="main\n")
        return _FakeCompletedProcess()

    monkeypatch.setattr(subprocess, "run", fake_run)
    repo = GitRepo(tmp_path)  # no deploy key configured — the local-dev / ambient-SSH-agent path
    repo.push()

    push_calls = [c for c in calls if len(c[0]) > 3 and c[0][3] == "push"]
    assert push_calls[0][1]["env"] is None


def test_clone_carries_deploy_key_ssh_command_in_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[list[str], dict]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> _FakeCompletedProcess:
        calls.append((cmd, kwargs))
        return _FakeCompletedProcess()

    monkeypatch.setattr(subprocess, "run", fake_run)
    dest = tmp_path / "cloned-brain"
    GitRepo.clone(
        "git@github.com:HendoCode/content-machine-brain.git", dest, ssh_deploy_key=_FAKE_KEY
    )

    assert len(calls) == 1
    cmd, kwargs = calls[0]
    assert cmd == ["git", "clone", "git@github.com:HendoCode/content-machine-brain.git", str(dest.resolve())]
    env = kwargs["env"]
    assert env is not None and "GIT_SSH_COMMAND" in env


# --- config -> app.git wiring: the deploy key reaches GitRepo/GitBrain/GitContentStore --------


@pytest.fixture(autouse=True)
def _clean_settings_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("BRAIN_REPO_URL", "BRAIN_DEPLOY_KEY", "BRAIN_ROOT"):
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()
    reset_secrets_provider()
    yield
    get_settings.cache_clear()
    reset_secrets_provider()


def test_ensure_brain_available_clones_with_deploy_key_from_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BRAIN_REPO_URL", "git@github.com:HendoCode/content-machine-brain.git")
    monkeypatch.setenv("BRAIN_DEPLOY_KEY", "fake-deploy-key-material")
    monkeypatch.setenv("BRAIN_ROOT", str(tmp_path / "brain"))
    get_settings.cache_clear()
    reset_secrets_provider()

    captured: dict[str, object] = {}

    def fake_clone(
        url: str, dest: object, *, ssh_deploy_key: str | None = None, ref: str | None = None
    ) -> GitRepo:
        captured["url"] = url
        captured["ssh_deploy_key"] = ssh_deploy_key
        raise GitError("network mocked away — this is what ensure_brain_available swallows")

    monkeypatch.setattr(GitRepo, "clone", staticmethod(fake_clone))
    ensure_brain_available()  # must not raise — GitError is swallowed by design

    assert captured["url"] == "git@github.com:HendoCode/content-machine-brain.git"
    assert captured["ssh_deploy_key"] == "fake-deploy-key-material"


def test_open_brain_and_content_store_pass_deploy_key_through(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BRAIN_DEPLOY_KEY", "fake-deploy-key-material")
    get_settings.cache_clear()
    reset_secrets_provider()

    root = tmp_path / "brain"
    subprocess.run(["git", "init", "-q", str(root)], check=True)

    brain = open_brain(str(root))
    content = open_content_store(str(root))
    assert brain.repo._ssh_deploy_key == "fake-deploy-key-material"
    assert content.repo._ssh_deploy_key == "fake-deploy-key-material"


def test_open_brain_has_no_deploy_key_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "brain"
    subprocess.run(["git", "init", "-q", str(root)], check=True)

    brain = open_brain(str(root))
    assert brain.repo._ssh_deploy_key is None
