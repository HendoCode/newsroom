"""The brain pin: ``GitRepo.checkout_ref``/``clone(ref=...)`` and ``ensure_brain_available``'s
``BRAIN_REF`` handling (agents/brain.lock, agents/app/git/README.md).

Everything here runs against a local bare repo standing in for the real
``masthead`` remote (no network), the same style as ``test_git.py``'s clone/pull/push
suite. The point being proven: a pinned ref always wins over "whatever the live branch tip is
now" — the mechanism build/test reproducibility depends on — while leaving ``BRAIN_REF`` unset
reproduces the pre-pin runtime behavior exactly (clone once, then fast-forward pull).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.config import Settings, get_settings
from app.git import ensure_brain_available
from app.git.repo import GitRepo
from app.secrets import reset_secrets_provider


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    for var in ("BRAIN_REPO_URL", "BRAIN_DEPLOY_KEY", "BRAIN_ROOT", "BRAIN_REF"):
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


def _commit(repo_path: Path, filename: str, content: str, message: str) -> str:
    (repo_path / filename).write_text(content)
    subprocess.run(["git", "-C", str(repo_path), "add", "-A"], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo_path), "-c", "user.email=t@test", "-c", "user.name=test",
            "commit", "-q", "-m", message,
        ],
        check=True,
    )
    return subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
    ).stdout.strip()


def _is_detached(repo_path: Path) -> bool:
    return subprocess.run(
        ["git", "-C", str(repo_path), "symbolic-ref", "-q", "HEAD"],
        capture_output=True, text=True, check=False,
    ).returncode != 0


def _seed_remote(bare_remote: Path, tmp_path: Path) -> tuple[Path, str, str]:
    """Push two commits to ``bare_remote`` on ``main`` and return (seed_repo, older_sha, newer_sha)."""
    seed = tmp_path / "seed"
    seed.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
    subprocess.run(["git", "-C", str(seed), "remote", "add", "origin", str(bare_remote)], check=True)
    older = _commit(seed, "PANEL.md", "v1\n", "v1")
    subprocess.run(["git", "-C", str(seed), "push", "-q", "origin", "HEAD:main"], check=True)
    newer = _commit(seed, "PANEL.md", "v2 — the live branch moved on\n", "v2")
    subprocess.run(["git", "-C", str(seed), "push", "-q", "origin", "HEAD:main"], check=True)
    return seed, older, newer


# --- GitRepo.checkout_ref / clone(ref=...) — the low-level pin plumbing ---------------------


def test_checkout_ref_pins_to_the_older_commit(bare_remote: Path, tmp_path: Path) -> None:
    _seed, older, _newer = _seed_remote(bare_remote, tmp_path)

    dest = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(bare_remote), str(dest)], check=True)
    repo = GitRepo(dest)

    repo.checkout_ref(older)

    assert repo.head_sha() == older
    assert _is_detached(dest)
    assert (dest / "PANEL.md").read_text() == "v1\n"


def test_clone_with_ref_pins_directly_to_the_older_commit(bare_remote: Path, tmp_path: Path) -> None:
    _seed, older, _newer = _seed_remote(bare_remote, tmp_path)

    dest = tmp_path / "pinned-clone"
    repo = GitRepo.clone(str(bare_remote), dest, ref=older)

    assert repo.head_sha() == older
    assert _is_detached(dest)
    assert (dest / "PANEL.md").read_text() == "v1\n"


def test_clone_without_ref_lands_on_the_live_branch_tip(bare_remote: Path, tmp_path: Path) -> None:
    _seed, _older, newer = _seed_remote(bare_remote, tmp_path)

    dest = tmp_path / "unpinned-clone"
    repo = GitRepo.clone(str(bare_remote), dest)

    assert repo.head_sha() == newer
    assert not _is_detached(dest)


# --- ensure_brain_available: BRAIN_REF pin vs the runtime clone/pull default -----------------


def test_ensure_brain_available_clones_at_the_pinned_ref_when_brain_ref_is_set(
    bare_remote: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed, older, _newer = _seed_remote(bare_remote, tmp_path)
    monkeypatch.setenv("BRAIN_REPO_URL", str(bare_remote))
    root = tmp_path / "brain-root"
    settings = Settings(brain_root=str(root), brain_ref=older)

    ensure_brain_available(settings)

    assert (root / "PANEL.md").read_text() == "v1\n"
    assert _is_detached(root)


def test_ensure_brain_available_repins_an_existing_clone_instead_of_pulling(
    bare_remote: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even a clone that's already on disk (and already at the live tip) gets re-pinned to
    ``BRAIN_REF`` rather than fast-forward-pulled — build/test must never silently drift onto
    whatever the live branch has since moved to."""
    _seed, older, newer = _seed_remote(bare_remote, tmp_path)
    monkeypatch.setenv("BRAIN_REPO_URL", str(bare_remote))
    root = tmp_path / "brain-root"

    # First boot with no pin: lands on the live tip, same as runtime today.
    ensure_brain_available(Settings(brain_root=str(root)))
    assert (root / "PANEL.md").read_text() == "v2 — the live branch moved on\n"
    assert not _is_detached(root)

    # A build/test run against the SAME on-disk clone, with BRAIN_REF set, re-pins backwards.
    ensure_brain_available(Settings(brain_root=str(root), brain_ref=older))
    assert (root / "PANEL.md").read_text() == "v1\n"
    assert _is_detached(root)
    assert GitRepo(root).head_sha() == older
    assert newer != older  # sanity: the two commits really differ


def test_ensure_brain_available_without_brain_ref_still_pulls_the_live_branch(
    bare_remote: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard for the runtime path: unset BRAIN_REF must behave exactly as before this
    pin was added — clone once, then fast-forward pull on every subsequent call."""
    _seed, _older, newer = _seed_remote(bare_remote, tmp_path)
    monkeypatch.setenv("BRAIN_REPO_URL", str(bare_remote))
    root = tmp_path / "brain-root"
    settings = Settings(brain_root=str(root))

    ensure_brain_available(settings)  # first boot: clone
    assert (root / "PANEL.md").read_text() == "v2 — the live branch moved on\n"

    # A further hand-nurtured commit lands on the remote...
    other_clone = tmp_path / "hand-edit"
    subprocess.run(["git", "clone", "-q", str(bare_remote), str(other_clone)], check=True)
    _commit(other_clone, "PANEL.md", "v3 — hand-nurtured\n", "v3")
    subprocess.run(["git", "-C", str(other_clone), "push", "-q", "origin", "HEAD:main"], check=True)

    ensure_brain_available(settings)  # subsequent boot: pull
    assert (root / "PANEL.md").read_text() == "v3 — hand-nurtured\n"
    assert not _is_detached(root)
    assert newer != GitRepo(root).head_sha()
