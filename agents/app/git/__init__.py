"""Git brain/content access layer (domain model §1.1/§1.2/§1.9/§1.10/§1.18; §7 Git stores).

Git *is* the versioning (D2/D4): this package reads the brain (Voices, Personas, engine, partners)
and reads/commits piece content (draft.html revisions, transcript.md, sources.md, feedback.md) and
accepted lessons in the agent-native layout. Work-state stays in Mongo (``app.repositories``).

The brain is a **clone** of its own repo (``HendoCode/masthead``), not a subdirectory
of this one — ``ensure_brain_available`` bootstraps/refreshes that clone; ``open_brain``/
``open_content_store`` open read/write views onto it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import Settings, get_settings
from app.git.brain import GitBrain, Persona, VoicePack
from app.git.content import GitContentStore, PieceFiles, apply_lesson_rule
from app.git.repo import Commit, GitError, GitRepo, NothingToCommit, discover_repo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BrainAvailability:
    """Outcome of the most recent :func:`ensure_brain_available` bootstrap/refresh attempt.

    A single ``connected`` boolean on ``GitBrain``/``/api/brain/status`` can't tell "no brain was
    ever configured" apart from "a brain was configured but this boot couldn't reach it" — both
    collapse to "empty." This splits that: ``configured`` is whether ``BRAIN_REPO_URL`` was set at
    all (an attempt was expected), and ``error`` is the real underlying failure message when that
    attempt (clone or pull) failed this boot, else ``None``.
    """

    configured: bool
    error: str | None = None


def refresh_brain(repo: GitRepo, *, ref: str | None) -> None:
    """Advance ``repo`` to the latest brain content from its configured remote: a fast-forward
    ``pull()`` when unpinned (the live runtime path), or a re-pin via ``checkout_ref`` when ``ref``
    is set (build/test — see the pin/bump story in ``app/git/README.md``).

    Shared by ``ensure_brain_available``'s "clone already on disk" boot branch below and the
    on-demand ``POST /api/brain/pull`` route (``app.main``), so a manual refresh of a *running*
    instance behaves identically to the refresh a restart would have performed.
    """
    if ref:
        repo.checkout_ref(ref)
    else:
        repo.pull()


def ensure_brain_available(settings: Settings | None = None) -> BrainAvailability:
    """Bootstrap/refresh the local brain clone from ``BRAIN_REPO_URL``, if configured.

    No-ops when ``brain_repo_url`` is unset — the local-dev default, where ``BRAIN_ROOT`` already
    points at a clone the developer manages themselves with their own git (manual pull/push, ambient
    SSH credentials).

    Two distinct modes, selected by ``settings.brain_ref`` (``BRAIN_REF``) — see
    ``agents/app/git/README.md`` for the full pin/bump story:

    - **Unset (runtime default).** Clones into ``BRAIN_ROOT`` on first boot, or fast-forward
      pulls an existing clone to pick up hand-nurtured updates on every subsequent boot. This is
      the live read-write loop (lessons/voice-kit edits push back to this same branch) — the
      running/prod app always takes this path, authenticating over SSH with the
      ``BRAIN_DEPLOY_KEY`` deploy key when one is configured (see ``app.git.ssh_auth``).
    - **Set (build/test).** Fetches ``brain_ref`` and detaches HEAD onto it (``GitRepo.
      checkout_ref``/``GitRepo.clone(..., ref=...)``) instead of pulling, on every call — pinning
      the clone to an exact, reproducible commit regardless of what the live branch has moved to
      since. Build/test tooling sets this from ``agents/brain.lock``'s ``ref`` (the known-good
      pin), not a default baked in here — leaving it unset must always mean "runtime, track live
      branch."

    A clone/fetch failure (``GitError`` — bad credentials, unreachable host, divergent history)
    does not crash boot: it degrades to whatever content is already on disk, same as before, but
    is now logged at ``ERROR`` with the real underlying git/SSH failure text (never the deploy key
    or any key material — that never appears in a git/ssh error message) and returned in the
    ``BrainAvailability.error`` field so ``/api/brain/status`` can report *why* rather than just
    "empty." Callers that only care about the boolean can ignore the return value entirely.
    """
    settings = settings or get_settings()
    if not settings.brain_repo_url:
        return BrainAvailability(configured=False)
    root = Path(settings.brain_root)
    deploy_key = settings.brain_deploy_key or None
    ref = settings.brain_ref or None
    try:
        if (root / ".git").exists():
            repo = GitRepo(root, ssh_deploy_key=deploy_key)
            refresh_brain(repo, ref=ref)
        else:
            GitRepo.clone(settings.brain_repo_url, root, ssh_deploy_key=deploy_key, ref=ref)
    except GitError as exc:
        logger.error("brain clone/fetch failed against %s: %s", settings.brain_repo_url, exc)
        return BrainAvailability(configured=True, error=str(exc))
    return BrainAvailability(configured=True)


def open_brain(brain_root: str | None = None) -> GitBrain:
    settings = get_settings()
    return GitBrain(
        brain_root or settings.brain_root,
        author_name=settings.git_author_name,
        author_email=settings.git_author_email,
        ssh_deploy_key=settings.brain_deploy_key or None,
    )


def open_content_store(brain_root: str | None = None) -> GitContentStore:
    settings = get_settings()
    return GitContentStore(
        brain_root or settings.brain_root,
        author_name=settings.git_author_name,
        author_email=settings.git_author_email,
        ssh_deploy_key=settings.brain_deploy_key or None,
    )


__all__ = [
    "BrainAvailability",
    "Commit",
    "GitBrain",
    "GitContentStore",
    "GitError",
    "GitRepo",
    "NothingToCommit",
    "Persona",
    "PieceFiles",
    "VoicePack",
    "apply_lesson_rule",
    "discover_repo",
    "ensure_brain_available",
    "open_brain",
    "open_content_store",
    "refresh_brain",
]
