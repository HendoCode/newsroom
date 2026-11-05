"""Low-level Git wrapper (D2/D4 — Git *is* the versioning).

A thin subprocess wrapper around ``git`` rooted at a working tree. No third-party Git library:
the operations we need (read a file, write + commit a change, list history, show/restore an old
revision) map cleanly onto plumbing/porcelain, and subprocess keeps the dependency surface small.

Author identity is passed **per commit** (``-c user.name``/``-c user.email``) so a real acting
user is attributed on every revision (D15/§1.17) without depending on ambient git config.

The brain now lives in its own repo (``HendoCode/masthead``), cloned read-write onto
disk rather than baked in as a subdirectory. ``clone``/``pull``/``push`` give ``GitRepo`` the three
remote operations that need: bootstrap a fresh clone, pick up hand-nurtured updates, and publish
machine-authored commits (accepted lessons, voice-kit edits, revisions). An optional SSH deploy key
(``ssh_deploy_key`` — a private key string, resolved through the secrets shim) authenticates those
operations via a **per-invocation** ``GIT_SSH_COMMAND`` environment override (see
``app.git.ssh_auth``) rather than an ambient ``~/.ssh`` or a persisted git-config credential — the
key material never touches ``.git/config`` or `git remote -v` output. When no deploy key is
configured, ambient credentials (a developer's own SSH agent) are used instead, which is the
expected path for a developer's own local clone.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.git.ssh_auth import get_ssh_deploy_key

logger = logging.getLogger(__name__)


class GitError(RuntimeError):
    """A git invocation failed."""


class NothingToCommit(GitError):
    """A commit was requested but the working tree had no staged changes."""


def _env_for(ssh_deploy_key: str | None) -> dict[str, str] | None:
    """The subprocess ``env`` override carrying ``GIT_SSH_COMMAND`` for a deploy-key-authenticated
    remote operation, or ``None`` (inherit the ambient environment unchanged) when no deploy key is
    configured — the local-dev path, where a developer's own SSH agent already authenticates."""
    if not ssh_deploy_key:
        return None
    return {**os.environ, "GIT_SSH_COMMAND": get_ssh_deploy_key(ssh_deploy_key).git_ssh_command}


@dataclass(frozen=True)
class Commit:
    sha: str
    author_name: str
    author_email: str
    # ISO-8601 author date (git %aI). Kept as a string — we never fabricate a clock here.
    date: str
    message: str


# Record separator unlikely to appear in commit metadata, for safe `git log` parsing.
_FIELD = "\x1f"
_RECORD = "\x1e"
_LOG_FORMAT = _FIELD.join(["%H", "%an", "%ae", "%aI", "%s"]) + _RECORD


class GitRepo:
    def __init__(self, root: str | Path, *, ssh_deploy_key: str | None = None) -> None:
        self.root = Path(root).resolve()
        # Kept only for the lifetime of this instance, used solely to build a per-invocation
        # `GIT_SSH_COMMAND` env override on push/pull (see module docstring) — never persisted
        # to disk beyond the one process-local key file `app.git.ssh_auth` materializes.
        self._ssh_deploy_key = ssh_deploy_key

    # --- process plumbing -----------------------------------------------------------------

    def _run(
        self, *args: str, check: bool = True, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        try:
            proc = subprocess.run(
                ["git", "-C", str(self.root), *args],
                capture_output=True,
                text=True,
                check=False,  # we inspect returncode ourselves and raise GitError with stderr
                env=env,
            )
        except FileNotFoundError as exc:
            raise GitError(f"git executable not found: {exc}") from exc
        if check and proc.returncode != 0:
            raise GitError(
                f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}"
            )
        return proc

    def is_repo(self) -> bool:
        return self._run("rev-parse", "--is-inside-work-tree", check=False).returncode == 0

    def _remote_env(self) -> dict[str, str] | None:
        """The subprocess ``env`` override for a network-touching git invocation (fetch/push),
        carrying the deploy key's ``GIT_SSH_COMMAND`` when one is configured."""
        return _env_for(self._ssh_deploy_key)

    # --- working-tree file I/O ------------------------------------------------------------

    def abspath(self, rel_path: str) -> Path:
        return self.root / rel_path

    def exists(self, rel_path: str) -> bool:
        return self.abspath(rel_path).exists()

    def read_text(self, rel_path: str) -> str:
        return self.abspath(rel_path).read_text(encoding="utf-8")

    def write_text(self, rel_path: str, content: str) -> None:
        target = self.abspath(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    # --- history-aware operations ---------------------------------------------------------

    def head_sha(self) -> str:
        return self._run("rev-parse", "HEAD").stdout.strip()

    def commit(
        self,
        paths: list[str],
        message: str,
        author_name: str,
        author_email: str,
    ) -> str:
        """Stage ``paths`` and commit them; returns the new commit SHA.

        Raises ``NothingToCommit`` if staging produced no change, so callers never create empty
        revisions (a revision is written only when content actually changed — D4).
        """
        self._run("add", "--", *paths)
        if self._run("diff", "--cached", "--quiet", check=False).returncode == 0:
            raise NothingToCommit(f"no staged changes for {paths}")
        self._run(
            "-c",
            f"user.name={author_name}",
            "-c",
            f"user.email={author_email}",
            "commit",
            "-m",
            message,
            "--",
            *paths,
        )
        sha = self.head_sha()
        try:
            self.push()
        except GitError as exc:
            # Best-effort: the commit is already durable locally (this clone's on-disk history),
            # so a transient push failure (network blip, stale credential) must not fail a write
            # that already succeeded — it would also make an identical retry misreport
            # NothingToCommit, since the working tree already matches the intended content. The
            # brain-provenance endpoint's local-vs-remote sha exposes any resulting push lag, but
            # that's a poll-for-it signal — log the real reason too, so it doesn't take a
            # dedicated investigation to notice pushes have been silently failing.
            logger.warning("push of commit %s failed (kept local-only): %s", sha, exc)
        return sha

    def log(self, rel_path: str | None = None, max_count: int = 0) -> list[Commit]:
        """Commit history, newest first, optionally restricted to a path."""
        args = ["log", f"--pretty=format:{_LOG_FORMAT}"]
        if max_count:
            args.append(f"-n{max_count}")
        if rel_path is not None:
            args += ["--", rel_path]
        out = self._run(*args).stdout
        commits: list[Commit] = []
        for record in out.split(_RECORD):
            record = record.strip("\n")
            if not record:
                continue
            sha, an, ae, date, msg = record.split(_FIELD)
            commits.append(Commit(sha=sha, author_name=an, author_email=ae, date=date, message=msg))
        return commits

    def show(self, sha: str, rel_path: str) -> str:
        """The contents of ``rel_path`` as of commit ``sha``."""
        return self._run("show", f"{sha}:{rel_path}").stdout

    def restore_from(self, sha: str, rel_path: str) -> None:
        """Restore the working-tree copy of ``rel_path`` to its state at ``sha`` (no commit)."""
        self._run("checkout", sha, "--", rel_path)

    # --- remote operations (brain-as-clone) ------------------------------------------------

    def has_remote(self, name: str = "origin") -> bool:
        """False for a bare local repo with no remote (e.g. the test fixtures' throwaway repos),
        which is exactly when ``push``/``pull`` below should no-op rather than error."""
        return name in self._run("remote", check=False).stdout.split()

    def remote_url(self, name: str = "origin") -> str | None:
        if not self.has_remote(name):
            return None
        return self._run("remote", "get-url", name).stdout.strip()

    def current_branch(self) -> str:
        return self._run("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    def push(self, *, remote: str = "origin") -> None:
        """Push the current branch to ``remote``. No-ops if no such remote is configured."""
        if not self.has_remote(remote):
            return
        branch = self.current_branch()
        self._run("push", remote, f"HEAD:{branch}", env=self._remote_env())

    def pull(self, *, remote: str = "origin") -> None:
        """Fast-forward the current branch from ``remote`` (picks up hand-nurtured brain edits).

        No-ops if no such remote is configured. Deliberately ``--ff-only``: a divergent history
        means a human/machine wrote locally without pushing, which should surface as an error
        rather than silently merge or rewrite either side.
        """
        if not self.has_remote(remote):
            return
        branch = self.current_branch()
        self._run("fetch", remote, env=self._remote_env())
        self._run("merge", "--ff-only", f"{remote}/{branch}")

    def checkout_ref(self, ref: str, *, remote: str = "origin") -> None:
        """Fetch ``ref`` (a commit SHA, tag, or branch) from ``remote`` and detach HEAD onto it.

        This is the **pin** mechanism (``BRAIN_REF`` / ``brain.lock``, see ``app.git.__init__``'s
        ``ensure_brain_available``): unlike ``pull``'s fast-forward onto the live branch tip,
        this always lands on the exact ref requested, so a build/test run is reproducible even
        while the live branch keeps moving underneath it.
        """
        self._run("fetch", remote, ref, env=self._remote_env())
        self._run("checkout", "--detach", "FETCH_HEAD")

    @staticmethod
    def clone(
        url: str, dest: str | Path, *, ssh_deploy_key: str | None = None, ref: str | None = None
    ) -> "GitRepo":
        """Clone ``url`` into ``dest`` (creating parent directories as needed) and return a
        ``GitRepo`` over it, remembering ``ssh_deploy_key`` for subsequent push/pull calls.

        If ``ref`` is given, detach HEAD onto it right after cloning (see ``checkout_ref``)
        instead of leaving the clone on the remote's default branch tip — the pinned-clone path
        build/test uses.
        """
        dest_path = Path(dest).resolve()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            ["git", "clone", url, str(dest_path)],
            capture_output=True,
            text=True,
            check=False,
            env=_env_for(ssh_deploy_key),
        )
        if proc.returncode != 0:
            raise GitError(f"git clone {url} failed ({proc.returncode}): {proc.stderr.strip()}")
        repo = GitRepo(dest_path, ssh_deploy_key=ssh_deploy_key)
        if ref:
            repo.checkout_ref(ref)
        return repo


def discover_repo(path: str | Path, *, ssh_deploy_key: str | None = None) -> tuple[GitRepo, str]:
    """Open the git repo enclosing ``path`` and return ``(repo, prefix)``.

    ``prefix`` is the POSIX path from the repo root to ``path`` (``""`` when they are the same).
    This lets the brain/content stores work identically whether the brain clone is its own git
    repo (prefix ``""`` — the normal case now that it's cloned from Masthead) or
    nested inside another repo (a nonzero prefix); all rel paths are joined onto the prefix so
    commits land at the right place either way.
    """
    resolved = Path(path).resolve()
    try:
        proc = subprocess.run(
            ["git", "-C", str(resolved), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,  # a non-repo path is reported as a GitError below, not a CalledProcessError
        )
    except FileNotFoundError as exc:
        raise GitError(f"git executable not found: {exc}") from exc
    if proc.returncode != 0:
        raise GitError(f"{resolved} is not inside a git repository: {proc.stderr.strip()}")
    top = Path(proc.stdout.strip())
    prefix = resolved.relative_to(top).as_posix()
    return GitRepo(top, ssh_deploy_key=ssh_deploy_key), ("" if prefix == "." else prefix)
