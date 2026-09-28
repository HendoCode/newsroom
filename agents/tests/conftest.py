"""Shared test fixtures.

The repository suite runs against an in-memory async Mongo (``mongomock-motor``) so it is green
with **no server**. An opt-in integration test (see ``test_repositories_integration.py``) points
at a real ``MONGO_URL`` and skips when unreachable.

The Git suite copies the checked-in **fixture brain** (``agents/tests/fixtures/brain/`` — a frozen
snapshot of the real ``HendoCode/masthead`` content) into a throwaway git repo, so we
exercise the true on-disk layout while committing safely to a temp repo (never the worktree, and
never the real brain clone). The fixture is laid out at its own repo root (no nested subdirectory)
to match production, where the brain is cloned as its own repo rather than nested under a
subdirectory of this one (``discover_repo`` then computes prefix ``""``, same as prod).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.git import GitBrain, GitContentStore
from app.lake import ContentLake, build_content_lake
from app.repositories import WorkStateStore

# agents/tests/fixtures/brain — a frozen snapshot of HendoCode/masthead's content.
FIXTURE_BRAIN = Path(__file__).resolve().parent / "fixtures" / "brain"


@pytest_asyncio.fixture
async def store() -> WorkStateStore:
    """A WorkStateStore backed by a fresh in-memory Mongo (isolated per test)."""
    db = AsyncMongoMockClient()["cmw_test"]
    return WorkStateStore(db)


@pytest_asyncio.fixture
async def lake() -> ContentLake:
    """A ContentLake on a fresh in-memory Mongo, local hybrid index + hashing embedder (D9)."""
    db = AsyncMongoMockClient()["cmw_test"]
    return build_content_lake(db)


@pytest.fixture
def brain_repo(tmp_path: Path) -> Path:
    """A temp git repo, at its own root, seeded with a copy of the fixture brain — the same shape
    as a real ``masthead`` clone (prefix ``""``)."""
    root = tmp_path / "repo"
    root.mkdir()
    # -b main: never depend on the host's init.defaultBranch (CI and local boxes differ).
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@test"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "test"], check=True)
    shutil.copytree(FIXTURE_BRAIN, root, dirs_exist_ok=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.email=t@test",
            "-c",
            "user.name=test",
            "commit",
            "-q",
            "-m",
            "seed brain",
        ],
        check=True,
    )
    return root


@pytest.fixture
def git_brain(brain_repo: Path) -> GitBrain:
    return GitBrain(str(brain_repo))


@pytest.fixture
def content_store(brain_repo: Path) -> GitContentStore:
    return GitContentStore(str(brain_repo))
