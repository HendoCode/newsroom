"""Git content store (domain model §1.9/§1.10 Piece & Revision; §1.18 accepted Lesson; §7).

Reads and commits the agent-native content for a piece folder ``drafts/<slug>/``:

    piece.md  draft.html  transcript.md  sources.md  feedback.md  assets/*

Per D2/D4 **Git is the versioning**: a Revision is a commit of ``draft.html`` (+ ``sources.md`` /
assets), written **only on job success**, and the module exposes read / commit-a-revision /
history / rollback affordances over that lineage. It also crosses the D12 store boundary the one
honest way: an **accepted** Lesson is appended to ``voice/<voice>/content-lessons.md`` and
committed to the brain (the machine never self-commits — a human accepts first, §1.18).

Work-state (stage, counts, cost) never lives here — that is Mongo (``app.repositories``). This
store touches content + brain files only, keeping the §3 split honest.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.git.repo import Commit, GitError, GitRepo, discover_repo


def apply_lesson_rule(existing: str, rule_text: str) -> str:
    """The exact bytes ``commit_accepted_lesson`` will write for this rule.

    Kept as a module-level function so preview and commit cannot drift, and so the voice-kit
    Git-diff preview can mirror it (``web/lib/voice-kit/lesson-preview.ts`` — keep in lockstep).
    """
    separator = "" if existing.endswith("\n") or existing == "" else "\n"
    return f"{existing}{separator}- {rule_text}\n"


class PieceFiles(BaseModel):
    """The current working-tree content of a piece folder (missing files → ``None``)."""

    slug: str
    piece_md: str | None = None
    draft_html: str | None = None
    transcript_md: str | None = None
    sources_md: str | None = None
    feedback_md: str | None = None
    # Brain-side structured metadata some brain-authored drafts carry alongside piece.md (the
    # 2026-08-31 AWS×Hendo briefs); never written by this webapp.
    meta_json: str | None = None


class GitContentStore:
    def __init__(
        self,
        brain_root: str,
        *,
        repo: GitRepo | None = None,
        prefix: str = "",
        author_name: str = "newsroom-agent",
        author_email: str = "agent@newsroom.local",
        ssh_deploy_key: str | None = None,
    ) -> None:
        if repo is None:
            repo, prefix = discover_repo(brain_root, ssh_deploy_key=ssh_deploy_key)
        self.repo = repo
        self.prefix = prefix
        self.author_name = author_name
        self.author_email = author_email

    def _p(self, *parts: str) -> str:
        segments = [self.prefix, *parts] if self.prefix else list(parts)
        return "/".join(segments)

    def _piece(self, slug: str, filename: str) -> str:
        return self._p("drafts", slug, filename)

    def _author(self, name: str | None, email: str | None) -> tuple[str, str]:
        return name or self.author_name, email or self.author_email

    # --- reads ----------------------------------------------------------------------------

    def list_pieces(self) -> list[str]:
        drafts = self.repo.abspath(self._p("drafts"))
        if not drafts.exists():
            return []
        return sorted(d.name for d in drafts.iterdir() if d.is_dir())

    def _read_opt(self, rel: str) -> str | None:
        return self.repo.read_text(rel) if self.repo.exists(rel) else None

    def read_piece_files(self, slug: str) -> PieceFiles:
        return PieceFiles(
            slug=slug,
            piece_md=self._read_opt(self._piece(slug, "piece.md")),
            draft_html=self._read_opt(self._piece(slug, "draft.html")),
            transcript_md=self._read_opt(self._piece(slug, "transcript.md")),
            sources_md=self._read_opt(self._piece(slug, "sources.md")),
            feedback_md=self._read_opt(self._piece(slug, "feedback.md")),
            meta_json=self._read_opt(self._piece(slug, "meta.json")),
        )

    def read_draft(self, slug: str) -> str:
        return self.repo.read_text(self._piece(slug, "draft.html"))

    def read_transcript(self, slug: str) -> str:
        return self.repo.read_text(self._piece(slug, "transcript.md"))

    def read_sources(self, slug: str) -> str:
        return self.repo.read_text(self._piece(slug, "sources.md"))

    # --- commit a revision / transcript / feedback ----------------------------------------

    def commit_revision(
        self,
        slug: str,
        draft_html: str,
        *,
        sources_md: str | None = None,
        assets: dict[str, str] | None = None,
        message: str,
        author_name: str | None = None,
        author_email: str | None = None,
    ) -> str:
        """Write ``draft.html`` (+ optional ``sources.md`` / assets) and commit — one Revision.

        Returns the commit SHA (the Revision identity, §1.10). Callers commit only on job success
        (D4); this method just performs the atomic write+commit.
        """
        paths = [self._piece(slug, "draft.html")]
        self.repo.write_text(paths[0], draft_html)
        if sources_md is not None:
            sources_path = self._piece(slug, "sources.md")
            self.repo.write_text(sources_path, sources_md)
            paths.append(sources_path)
        for name, content in (assets or {}).items():
            asset_path = self._piece(slug, f"assets/{name}")
            self.repo.write_text(asset_path, content)
            paths.append(asset_path)
        return self.repo.commit(paths, message, *self._author(author_name, author_email))

    def commit_transcript(
        self,
        slug: str,
        transcript_md: str,
        *,
        message: str,
        author_name: str | None = None,
        author_email: str | None = None,
    ) -> str:
        """Commit the sacred ``transcript.md`` (D16b) — piece-scoped, accumulated."""
        path = self._piece(slug, "transcript.md")
        self.repo.write_text(path, transcript_md)
        return self.repo.commit([path], message, *self._author(author_name, author_email))

    def commit_feedback(
        self,
        slug: str,
        feedback_md: str,
        *,
        message: str,
        author_name: str | None = None,
        author_email: str | None = None,
    ) -> str:
        """Commit the ``feedback.md`` audit mirror (Mongo remains system-of-record, §5-Q3)."""
        path = self._piece(slug, "feedback.md")
        self.repo.write_text(path, feedback_md)
        return self.repo.commit([path], message, *self._author(author_name, author_email))

    # --- history / rollback ---------------------------------------------------------------

    def latest_folder_revision(self, slug: str) -> str | None:
        """SHA of the newest commit touching the piece folder ``drafts/<slug>/``, or ``None``.

        Folder-scoped (not ``draft.html``-scoped like :meth:`revision_history`) so brain-authored
        drafts whose content never went through a webapp Revision (no ``draft.html`` at all — see
        ``app.piece_md``/``app.brain_sync``) still have a real Git provenance pointer.
        """
        commits = self.repo.log(self._p("drafts", slug), max_count=1)
        return commits[0].sha if commits else None

    def revision_history(self, slug: str, max_count: int = 0) -> list[Commit]:
        """The Git lineage of a piece's ``draft.html``, newest first (§1.10 diffable lineage)."""
        return self.repo.log(self._piece(slug, "draft.html"), max_count=max_count)

    def read_revision(self, slug: str, sha: str) -> str:
        """The ``draft.html`` content as of a past Revision ``sha``."""
        return self.repo.show(sha, self._piece(slug, "draft.html"))

    def try_read_revision(self, slug: str, sha: str) -> str | None:
        """The ``draft.html`` content as of a past Revision ``sha``, or ``None`` when no
        ``draft.html`` exists at that revision — the brain-authored direct-authored pieces that
        carry their content in ``piece.md`` instead (see ``app.piece_md`` and
        ``app.piece_detail.draft_content_from_files``). Callers decide how to fall back; this
        never raises for the missing-file case."""
        try:
            return self.repo.show(sha, self._piece(slug, "draft.html"))
        except GitError:
            return None

    def rollback_revision(
        self,
        slug: str,
        sha: str,
        *,
        message: str | None = None,
        author_name: str | None = None,
        author_email: str | None = None,
    ) -> str:
        """Roll back ``draft.html`` to an earlier Revision by committing that old content forward.

        History-preserving: rather than rewriting history, we restore the file to ``sha`` and
        commit it as a new Revision (a diffable, attributable step, D4).
        """
        path = self._piece(slug, "draft.html")
        self.repo.restore_from(sha, path)
        msg = message or f"rollback {slug} draft.html to {sha[:8]}"
        return self.repo.commit([path], msg, *self._author(author_name, author_email))

    # --- accepted lesson → brain (D12 gate crossing) --------------------------------------

    def commit_accepted_lesson(
        self,
        voice_slug: str,
        rule_text: str,
        *,
        message: str | None = None,
        author_name: str | None = None,
        author_email: str | None = None,
    ) -> str:
        """Append an accepted lesson to ``voice/<voice>/content-lessons.md`` and commit it.

        This is the D12 human gate crossing: a proposed Lesson (Mongo) that a human accepted lands
        in the Git brain, per-voice (never another voice's file, §1.18). The machine never reaches
        this path on its own — a human acceptance triggers it.
        """
        path, _before, updated = self.preview_accepted_lesson(voice_slug, rule_text)
        self.repo.write_text(path, updated)
        msg = message or f"accept content lesson for voice {voice_slug}"
        return self.repo.commit([path], msg, *self._author(author_name, author_email))

    def preview_accepted_lesson(self, voice_slug: str, rule_text: str) -> tuple[str, str, str]:
        """Return ``(path, before, after)`` for the Git diff a human would accept.

        Does not write. The voice-kit batch-review UI renders this as a unified diff of the
        rule about to land in ``content-lessons.md``.
        """
        path = self._p("voice", voice_slug, "content-lessons.md")
        existing = self.repo.read_text(path) if self.repo.exists(path) else ""
        return path, existing, apply_lesson_rule(existing, rule_text)
