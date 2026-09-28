"""Git brain/content access tests.

These run against a temp git repo seeded with a copy of the fixture brain
(``agents/tests/fixtures/brain/``, see ``conftest.brain_repo``), so they prove the module reads the
true on-disk layout and can commit revisions / transcripts / accepted lessons to Git (D2/D4), with
history + rollback. The clone/push/pull tests below use a local bare repo as a stand-in remote
(no network) to prove the brain-as-clone plumbing without depending on GitHub.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.git import GitBrain, GitContentStore, NothingToCommit, apply_lesson_rule
from app.git.repo import GitRepo, discover_repo

# The fixture brain's pieces (see agents/tests/fixtures/brain/drafts/ — a snapshot of the pinned
# brain ref): two carry a draft.html, one is still mid-interview with no draft yet.
PIECE_WITH_DRAFT = "rehearse-the-rollback"
PIECE_WITHOUT_DRAFT = "idempotency-is-the-whole-job"

# --- brain reads ---------------------------------------------------------------------------


def test_lists_and_reads_real_voices(git_brain: GitBrain) -> None:
    voices = git_brain.list_voices()
    assert {"demo-mira", "demo-dana"}.issubset(set(voices))
    mira = git_brain.read_voice("demo-mira")
    assert mira.voice_guide and mira.style_guide and mira.content_lessons
    # The brain is the neutral demo suite: it ships no personal branding for either voice (§1.1),
    # which is what the render path's plain-token fallback exists for.
    assert mira.visual_identity is None and mira.brand_guidelines is None
    team = git_brain.read_voice("demo-dana")
    assert team.voice_guide and team.style_guide and team.content_lessons
    assert team.visual_identity is None and team.brand_guidelines is None


def test_brand_files_are_read_when_the_brain_carries_them(branded_git_brain: GitBrain) -> None:
    """A branded brain (the Hendo Code voice pack) does carry the team-only files (§1.1)."""
    team = branded_git_brain.read_voice("demo-dana")
    assert team.visual_identity is not None and team.brand_guidelines is not None
    # ...and they stay demo-dana-only: the other voice has no brand files even there.
    assert branded_git_brain.read_voice("demo-mira").visual_identity is None


def test_lists_and_reads_personas(git_brain: GitBrain) -> None:
    editors = git_brain.list_personas("editor")
    interviewers = git_brain.list_personas("interviewer")
    assert {"slop-allergist", "voice-guardian"}.issubset(set(editors))
    assert {"skeptic", "architect", "operator"}.issubset(set(interviewers))
    # The per-directory README is prose for humans, never a persona.
    assert "README" not in editors and "README" not in interviewers
    persona = git_brain.read_persona("editor", "cold-reader")
    assert persona.kind == "editor" and persona.body


def test_read_engine_and_partners(git_brain: GitBrain) -> None:
    oracle = git_brain.read_engine("1-oracle")
    assert oracle  # engine step doc is readable
    partners = git_brain.list_partners()
    assert "meridian-cloudworks" in partners and "README" not in partners
    assert git_brain.read_partner("meridian-cloudworks")


def test_unknown_persona_kind_raises(git_brain: GitBrain) -> None:
    with pytest.raises(ValueError):
        git_brain.list_personas("nonsense")


# --- voice pack edit / history / rollback (voice-kit screen, D12) ---------------------------


def test_write_voice_file_and_history(git_brain: GitBrain) -> None:
    original = git_brain.read_voice("demo-mira").voice_guide
    assert original is not None
    sha1 = git_brain.write_voice_file(
        "demo-mira", "voice_guide", original + "\n\n- new DNA rule A\n",
        message="tighten voice-guide", author_name="Alex", author_email="alex@example.com",
    )
    sha2 = git_brain.write_voice_file(
        "demo-mira", "voice_guide", original + "\n\n- new DNA rule B\n", message="tighten again",
    )
    assert sha1 != sha2
    history = git_brain.voice_file_history("demo-mira", "voice_guide")
    assert history[0].sha == sha2  # newest first
    assert history[0].message == "tighten again"
    assert history[1].author_email == "alex@example.com"
    # Reading a past version returns that version's content, not current.
    assert "rule A" in git_brain.read_voice_file_at("demo-mira", "voice_guide", sha1)
    assert "rule B" not in git_brain.read_voice_file_at("demo-mira", "voice_guide", sha1)


def test_write_voice_file_defaults_to_brain_author(git_brain: GitBrain) -> None:
    original = git_brain.read_voice("demo-dana").style_guide
    assert original is not None
    sha = git_brain.write_voice_file("demo-dana", "style_guide", original + "\n- x\n", message="edit")
    history = git_brain.voice_file_history("demo-dana", "style_guide", max_count=1)
    assert history[0].sha == sha
    assert history[0].author_email == git_brain.author_email


def test_rollback_voice_file_creates_forward_commit(git_brain: GitBrain) -> None:
    original = git_brain.read_voice("demo-mira").style_guide
    assert original is not None
    sha1 = git_brain.write_voice_file("demo-mira", "style_guide", original + "\n<!-- v1 -->\n", message="v1")
    git_brain.write_voice_file("demo-mira", "style_guide", original + "\n<!-- v2 -->\n", message="v2")
    rollback_sha = git_brain.rollback_voice_file("demo-mira", "style_guide", sha1)
    pack = git_brain.read_voice("demo-mira")
    assert pack.style_guide is not None
    assert "<!-- v1 -->" in pack.style_guide
    assert "<!-- v2 -->" not in pack.style_guide
    history = git_brain.voice_file_history("demo-mira", "style_guide")
    assert history[0].sha == rollback_sha
    assert len(history) >= 3  # v1, v2, rollback all retained


def test_write_voice_file_unknown_file_key_raises(git_brain: GitBrain) -> None:
    with pytest.raises(ValueError):
        git_brain.write_voice_file("demo-mira", "nonsense", "x", message="x")


def test_write_team_only_file(branded_git_brain: GitBrain) -> None:
    original = branded_git_brain.read_voice("demo-dana").visual_identity
    assert original is not None
    sha = branded_git_brain.write_voice_file(
        "demo-dana", "visual_identity", original + "\n<!-- retouch -->\n", message="retouch palette"
    )
    assert sha
    assert "<!-- retouch -->" in branded_git_brain.read_voice("demo-dana").visual_identity


# --- content reads -------------------------------------------------------------------------


def test_read_piece_files_real_layout(content_store: GitContentStore) -> None:
    slugs = content_store.list_pieces()
    assert {PIECE_WITH_DRAFT, PIECE_WITHOUT_DRAFT, "the-board-on-the-wall"} == set(slugs)
    files = content_store.read_piece_files(PIECE_WITH_DRAFT)
    assert files.draft_html and files.transcript_md and files.sources_md and files.piece_md


def test_read_piece_files_tolerates_a_draftless_piece(content_store: GitContentStore) -> None:
    """A piece still in the interview has transcript + sources but no draft.html."""
    files = content_store.read_piece_files(PIECE_WITHOUT_DRAFT)
    assert files.transcript_md and files.sources_md and files.piece_md


# --- commit a revision, then history / rollback --------------------------------------------


def test_commit_revision_and_history(content_store: GitContentStore) -> None:
    slug = PIECE_WITH_DRAFT
    original = content_store.read_draft(slug)
    sha1 = content_store.commit_revision(
        slug,
        original + "\n<!-- rev A -->\n",
        message="rev A",
        author_name="Demo-mira",
        author_email="demo-mira@example.com",
    )
    sha2 = content_store.commit_revision(
        slug,
        original + "\n<!-- rev B -->\n",
        message="rev B",
        author_name="Demo-mira",
        author_email="demo-mira@example.com",
    )
    assert sha1 != sha2
    history = content_store.revision_history(slug)
    assert history[0].sha == sha2  # newest first
    assert history[0].message == "rev B"
    assert history[0].author_email == "demo-mira@example.com"
    # Reading a past revision returns that revision's content.
    assert "<!-- rev A -->" in content_store.read_revision(slug, sha1)
    assert "<!-- rev B -->" not in content_store.read_revision(slug, sha1)


def test_rollback_creates_forward_commit(content_store: GitContentStore) -> None:
    slug = PIECE_WITH_DRAFT
    original = content_store.read_draft(slug)
    sha1 = content_store.commit_revision(slug, original + "\n<!-- v1 -->\n", message="v1")
    content_store.commit_revision(slug, original + "\n<!-- v2 -->\n", message="v2")
    rollback_sha = content_store.rollback_revision(slug, sha1)
    # Working tree now matches v1 again, but via a NEW commit (history preserved).
    assert "<!-- v1 -->" in content_store.read_draft(slug)
    assert "<!-- v2 -->" not in content_store.read_draft(slug)
    history = content_store.revision_history(slug)
    assert history[0].sha == rollback_sha
    assert len(history) >= 3  # v1, v2, rollback all retained


def test_commit_transcript(content_store: GitContentStore) -> None:
    slug = PIECE_WITH_DRAFT
    body = content_store.read_transcript(slug) + "\n\n## Gap interview\nQ: ...\nA: ...\n"
    sha = content_store.commit_transcript(slug, body, message="append gap interview turns")
    assert sha
    assert "Gap interview" in content_store.read_transcript(slug)


def test_no_op_commit_raises(content_store: GitContentStore) -> None:
    slug = PIECE_WITH_DRAFT
    unchanged = content_store.read_draft(slug)
    with pytest.raises(NothingToCommit):
        content_store.commit_revision(slug, unchanged, message="no change")


# --- accepted lesson crosses the D12 gate into the brain -----------------------------------


def test_commit_accepted_lesson_appends_per_voice(content_store: GitContentStore) -> None:
    rule = "Prefer a named company over an adjective when a specific exists."
    sha = content_store.commit_accepted_lesson(
        "demo-mira", rule, author_name="Alex", author_email="alex@example.com"
    )
    assert sha
    # The rule lands in demo-mira's file...
    mira_lessons = content_store.repo.read_text(
        content_store._p("voice", "demo-mira", "content-lessons.md")
    )
    assert rule in mira_lessons
    # ...and never in another voice's file (per-voice invariant, §1.18).
    dana_lessons = content_store.repo.read_text(
        content_store._p("voice", "demo-dana", "content-lessons.md")
    )
    assert rule not in dana_lessons


def test_preview_accepted_lesson_matches_commit_bytes(content_store: GitContentStore) -> None:
    rule = "Never bury the number in a clause."
    path, before, after = content_store.preview_accepted_lesson("demo-mira", rule)
    assert path.endswith("voice/demo-mira/content-lessons.md")
    assert after == apply_lesson_rule(before, rule)
    assert rule not in before
    assert f"- {rule}" in after
    # Preview must not write.
    on_disk = content_store.repo.read_text(path)
    assert on_disk == before

    content_store.commit_accepted_lesson("demo-mira", rule)
    committed = content_store.repo.read_text(path)
    assert committed == after


def test_apply_lesson_rule_inserts_separator_only_when_needed() -> None:
    assert apply_lesson_rule("", "A") == "- A\n"
    assert apply_lesson_rule("- existing\n", "A") == "- existing\n- A\n"
    assert apply_lesson_rule("- existing", "A") == "- existing\n- A\n"


# --- repo discovery ------------------------------------------------------------------------


def test_discover_repo_computes_prefix_for_own_repo_root(brain_repo) -> None:
    # brain_repo IS the git root now (the brain-as-clone shape) — prefix is empty.
    repo, prefix = discover_repo(str(brain_repo))
    assert prefix == ""
    assert repo.is_repo()


def test_discover_repo_computes_prefix_when_nested(brain_repo) -> None:
    # discover_repo still supports a brain nested inside a larger repo (e.g. a dev who prefers to
    # keep it vendored) — prove that shape independently of the primary brain_repo fixture.
    nested = brain_repo / "vendor" / "newsroom-agent"
    nested.mkdir(parents=True)
    (nested / "PANEL.md").write_text("nested\n")
    subprocess.run(["git", "-C", str(brain_repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(brain_repo), "-c", "user.email=t@test", "-c", "user.name=test",
         "commit", "-q", "-m", "nest a copy"],
        check=True,
    )
    repo, prefix = discover_repo(str(nested))
    assert prefix == "vendor/newsroom-agent"
    assert repo.root == brain_repo.resolve()


# --- remote operations: clone / pull / push (brain-as-clone) --------------------------------


@pytest.fixture
def bare_remote(tmp_path: Path) -> Path:
    """A local bare repo standing in for the real ``masthead`` GitHub remote."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    return remote


def _branch_name(repo_path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_path), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def _push_seed(brain_repo: Path, bare_remote: Path) -> str:
    """Wire ``brain_repo`` to ``bare_remote`` as ``origin`` and push its current branch. Returns
    the branch name (whatever ``init.defaultBranch`` is configured as — never assumed)."""
    branch = _branch_name(brain_repo)
    subprocess.run(["git", "-C", str(brain_repo), "remote", "add", "origin", str(bare_remote)], check=True)
    subprocess.run(["git", "-C", str(brain_repo), "push", "-q", "origin", f"HEAD:{branch}"], check=True)
    return branch


def test_has_remote_false_without_one(brain_repo: Path) -> None:
    repo, _ = discover_repo(str(brain_repo))
    assert repo.has_remote() is False
    assert repo.remote_url() is None


def test_has_remote_true_once_configured(brain_repo: Path, bare_remote: Path) -> None:
    _push_seed(brain_repo, bare_remote)
    repo, _ = discover_repo(str(brain_repo))
    assert repo.has_remote() is True
    assert repo.remote_url() == str(bare_remote)


def test_push_noop_without_remote(brain_repo: Path) -> None:
    repo, _ = discover_repo(str(brain_repo))
    repo.push()  # must not raise even though there is nothing to push to


def test_commit_auto_pushes_when_remote_configured(brain_repo: Path, bare_remote: Path) -> None:
    branch = _push_seed(brain_repo, bare_remote)
    content_store = GitContentStore(str(brain_repo))
    slug = PIECE_WITH_DRAFT
    original = content_store.read_draft(slug)
    sha = content_store.commit_revision(slug, original + "\n<!-- pushed -->\n", message="rev")
    remote_head = subprocess.run(
        ["git", "-C", str(bare_remote), "rev-parse", branch], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert remote_head == sha


def test_pull_fast_forwards_from_remote(brain_repo: Path, bare_remote: Path) -> None:
    branch = _push_seed(brain_repo, bare_remote)
    # Simulate a hand-nurtured update landing on the remote via a second clone.
    other_clone = brain_repo.parent / "other-clone"
    subprocess.run(["git", "clone", "-q", str(bare_remote), str(other_clone)], check=True)
    (other_clone / "PANEL.md").write_text("hand-nurtured update\n")
    subprocess.run(["git", "-C", str(other_clone), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(other_clone), "-c", "user.email=t@test", "-c", "user.name=test",
         "commit", "-q", "-m", "hand-nurtured edit"],
        check=True,
    )
    subprocess.run(["git", "-C", str(other_clone), "push", "-q", "origin", f"HEAD:{branch}"], check=True)

    repo, _ = discover_repo(str(brain_repo))
    repo.pull()
    assert (brain_repo / "PANEL.md").read_text() == "hand-nurtured update\n"


def test_clone_bootstraps_a_fresh_working_copy(bare_remote: Path, tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    seed.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
    (seed / "PANEL.md").write_text("hello\n")
    subprocess.run(["git", "-C", str(seed), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(seed), "-c", "user.email=t@test", "-c", "user.name=test",
         "commit", "-q", "-m", "seed"],
        check=True,
    )
    subprocess.run(["git", "-C", str(seed), "remote", "add", "origin", str(bare_remote)], check=True)
    subprocess.run(["git", "-C", str(seed), "push", "-q", "origin", "HEAD:main"], check=True)

    dest = tmp_path / "cloned-brain"
    repo = GitRepo.clone(str(bare_remote), dest)
    assert (dest / "PANEL.md").read_text() == "hello\n"
    assert repo.has_remote()
