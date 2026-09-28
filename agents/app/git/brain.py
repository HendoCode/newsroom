"""Git brain reader + voice-pack writer (domain model §1.1, §1.2 — Voices & Personas; §7 Git-brain
store).

Reads the agent-native brain layout under the ``newsroom-agent/`` tree:

    voice/<slug>/{voice-guide,style-guide,content-lessons}.md
    voice/demo-dana/{visual-identity,brand-guidelines}.md   (demo-dana only)
    interviewers/<name>.md   editors/<name>.md
    engine/<name>.md         partners/<name>.md

Voices and Personas are Git-owned (D1/D2): Git *is* the versioning, so there is no status field —
reads return current working-tree content. Personas/engine/partners stay read-only here. Voice
pack files are the one part of the brain a human edits directly (the voice-kit screen, D12: any
employee may edit any kit, courtesy note only, never a gate) — ``write_voice_file`` /
``voice_file_history`` / ``read_voice_file_at`` / ``rollback_voice_file`` give that screen the
same commit/history/rollback discipline ``app.git.content`` already gives piece Revisions.
Accepting a *lesson* still lives in ``app.git.content`` (``commit_accepted_lesson``) so the D12
gate-crossing stays in one place.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.git.repo import Commit, GitRepo, discover_repo

# Voice pack file names (§1.1). The last two exist for demo-dana only.
_CORE_VOICE_FILES = {
    "voice_guide": "voice-guide.md",
    "style_guide": "style-guide.md",
    "content_lessons": "content-lessons.md",
}
_TEAM_VOICE_FILES = {
    "visual_identity": "visual-identity.md",
    "brand_guidelines": "brand-guidelines.md",
}
# Every known voice-pack file key -> filename, for the generic write/history/rollback affordances.
_ALL_VOICE_FILES = {**_CORE_VOICE_FILES, **_TEAM_VOICE_FILES}


class VoicePack(BaseModel):
    slug: str
    voice_guide: str | None = None
    style_guide: str | None = None
    content_lessons: str | None = None
    # demo-dana only (§1.1).
    visual_identity: str | None = None
    brand_guidelines: str | None = None


class Persona(BaseModel):
    # kind: "interviewer" (extraction) or "editor" (judgment) — both voice-neutral (§1.2).
    kind: str
    name: str
    body: str


class GitBrain:
    """View over the Git brain: read-only for Personas/engine/partners, read+write for Voice
    packs (the voice-kit screen's edit/commit/rollback surface)."""

    def __init__(
        self,
        brain_root: str,
        repo: GitRepo | None = None,
        prefix: str = "",
        *,
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

    # --- voices ---------------------------------------------------------------------------

    def list_voices(self) -> list[str]:
        voice_dir = self.repo.abspath(self._p("voice"))
        if not voice_dir.exists():
            return []
        return sorted(d.name for d in voice_dir.iterdir() if d.is_dir())

    def read_voice(self, slug: str) -> VoicePack:
        def _read(filename: str) -> str | None:
            rel = self._p("voice", slug, filename)
            return self.repo.read_text(rel) if self.repo.exists(rel) else None

        pack = VoicePack(slug=slug)
        for attr, filename in _CORE_VOICE_FILES.items():
            setattr(pack, attr, _read(filename))
        for attr, filename in _TEAM_VOICE_FILES.items():
            setattr(pack, attr, _read(filename))
        return pack

    def _voice_file_path(self, slug: str, file_key: str) -> str:
        if file_key not in _ALL_VOICE_FILES:
            raise ValueError(
                f"unknown voice pack file {file_key!r} (expected one of {sorted(_ALL_VOICE_FILES)})"
            )
        return self._p("voice", slug, _ALL_VOICE_FILES[file_key])

    def _author(self, name: str | None, email: str | None) -> tuple[str, str]:
        return name or self.author_name, email or self.author_email

    # --- voice pack edit / history / rollback (voice-kit screen) --------------------------

    def write_voice_file(
        self,
        slug: str,
        file_key: str,
        content: str,
        *,
        message: str,
        author_name: str | None = None,
        author_email: str | None = None,
    ) -> str:
        """Write one voice-pack file and commit it — a human edit, never a machine self-commit
        (D12; the machine only ever reaches ``content-lessons.md`` via the lessons accept gate,
        ``app.git.content.commit_accepted_lesson``). Returns the new commit SHA."""
        path = self._voice_file_path(slug, file_key)
        self.repo.write_text(path, content)
        return self.repo.commit([path], message, *self._author(author_name, author_email))

    def voice_file_history(self, slug: str, file_key: str, max_count: int = 0) -> list[Commit]:
        """Git history of one voice-pack file, newest first."""
        return self.repo.log(self._voice_file_path(slug, file_key), max_count=max_count)

    def read_voice_file_at(self, slug: str, file_key: str, sha: str) -> str:
        """The content of one voice-pack file as of a past commit ``sha`` (for diff/rollback
        preview)."""
        return self.repo.show(sha, self._voice_file_path(slug, file_key))

    def rollback_voice_file(
        self,
        slug: str,
        file_key: str,
        sha: str,
        *,
        message: str | None = None,
        author_name: str | None = None,
        author_email: str | None = None,
    ) -> str:
        """Roll a voice-pack file back to an earlier commit by restoring and committing forward
        (history-preserving, same discipline as ``app.git.content.rollback_revision``)."""
        path = self._voice_file_path(slug, file_key)
        self.repo.restore_from(sha, path)
        msg = message or f"rollback {slug}/{_ALL_VOICE_FILES[file_key]} to {sha[:8]}"
        return self.repo.commit([path], msg, *self._author(author_name, author_email))

    # --- personas -------------------------------------------------------------------------

    def list_personas(self, kind: str) -> list[str]:
        """``kind`` is 'interviewer' or 'editor'. Returns persona names (filenames sans .md),
        excluding README and other non-persona files that may live in the same folder."""
        folder = self.repo.abspath(self._p(self._persona_dir(kind)))
        if not folder.exists():
            return []
        return sorted(
            f.stem for f in folder.glob("*.md")
            if f.stem not in ("README",)
        )

    def read_persona(self, kind: str, name: str) -> Persona:
        rel = self._p(self._persona_dir(kind), f"{name}.md")
        return Persona(kind=kind, name=name, body=self.repo.read_text(rel))

    @staticmethod
    def _persona_dir(kind: str) -> str:
        if kind == "interviewer":
            return "interviewers"
        if kind == "editor":
            return "editors"
        raise ValueError(f"unknown persona kind {kind!r} (expected 'interviewer' or 'editor')")

    # --- engine steps & partners ----------------------------------------------------------

    def read_engine(self, name: str) -> str:
        """Read an engine step doc, e.g. '1-oracle', '2-draft', 'feedback-intake'."""
        return self.repo.read_text(self._p("engine", f"{name}.md"))

    def list_partners(self) -> list[str]:
        folder = self.repo.abspath(self._p("partners"))
        if not folder.exists():
            return []
        return sorted(f.stem for f in folder.glob("*.md") if f.stem != "README")

    def read_partner(self, name: str) -> str:
        return self.repo.read_text(self._p("partners", f"{name}.md"))
