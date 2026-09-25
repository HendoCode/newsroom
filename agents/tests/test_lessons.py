"""Lessons-loop service tests (D12; domain model §1.18; cmw-context-assembly report §9).

Covers, per the acceptance criteria:
- the structural final-vs-published diff (via git, not the model);
- proposing generalizable, deduped, per-voice lessons from the diff, Opus-tiered, landing in
  Mongo as ``proposed``;
- the human accept/edit/reject gate — only ``accept`` reaches Git, per-voice, and the machine
  never self-commits;
- the context-assembly recipe (§9-b): engine doc + voice-guide/style-guide in the stable prefix,
  the diff + existing content-lessons.md + JSON-output contract in the variable tail.

Zero external deps: the LLM path runs on a tiny fake provider (no ``anthropic`` package, no key,
no network); Git runs against the real brain copied into a throwaway repo (``conftest.brain_repo``);
Mongo runs against ``mongomock-motor`` (``conftest.store``).
"""

from __future__ import annotations

import json

import pytest

from app.git import GitBrain, GitContentStore
from app.lessons.diff import compute_diff
from app.lessons.errors import LessonNotPending, LessonsParseError, NotInLessonsStage
from app.lessons.prompts import build_lessons_prompt, parse_candidates
from app.lessons.service import LessonsService
from app.llm.pricing import Usage, cost_usd
from app.llm.provider import LLMProvider, LLMResult
from app.llm.tiering import MODEL_GLM5, PipelineStep
from app.models import Lesson, LessonStatus, Piece, PieceStage
from app.repositories import WorkStateStore

SLUG = "token-vs-storage"


class FakeLessonsProvider(LLMProvider):
    """Records the assembled call and returns a canned JSON-array response."""

    def __init__(self, response_text: str = "[]") -> None:
        self.response_text = response_text
        self.calls: list[dict[str, object]] = []

    async def complete(self, *, step, model, system, messages, max_tokens, effort=None, cache=False, budget=None):
        if budget is not None:
            budget.check()
        self.calls.append(
            {"step": step, "model": model, "system": system, "messages": messages}
        )
        usage = Usage(input_tokens=500, output_tokens=100)
        if budget is not None:
            budget.charge(model, usage)
        return LLMResult(
            text=self.response_text,
            model=model,
            stop_reason="end_turn",
            usage=usage,
            cost_usd=cost_usd(model, usage),
        )

    def stream(self, **kwargs):
        raise NotImplementedError("lessons only ever uses complete()")

    async def count_tokens(self, *, model, system, messages):
        return 0


def _lessons_json(*pairs: tuple[str, str]) -> str:
    return json.dumps(
        [{"observed_change": change, "generalizable_rule": rule} for change, rule in pairs]
    )


async def _piece(store: WorkStateStore, *, stage: PieceStage, latest_revision: str | None) -> Piece:
    return await store.pieces.insert(
        Piece(slug=SLUG, voice="demo-mira", stage=stage, latest_revision=latest_revision)
    )


# --- diff.compute_diff (structural, via git) ------------------------------------------------


def test_compute_diff_empty_when_identical():
    assert compute_diff("same text\n", "same text\n") == ""


def test_compute_diff_shows_the_change():
    diff = compute_diff("Line one.\nLine two.\n", "Line one.\nLine two, revised.\n")
    assert "Line two." in diff
    assert "Line two, revised." in diff
    assert "diff --git" in diff


# --- prompts.build_lessons_prompt (context report §9-b recipe) ------------------------------


def test_build_lessons_prompt_places_tiers_per_recipe(git_brain: GitBrain, content_store: GitContentStore):
    voice = git_brain.read_voice("demo-mira")
    piece = Piece(slug=SLUG, voice="demo-mira", title="Token vs Storage", target="blog")
    diff_text = "--- a\n+++ b\n-old line\n+new line\n"

    prompt = build_lessons_prompt(git_brain, content_store, piece, voice, diff_text)
    system_texts = prompt.system

    # T0 (stable): the engine doc + voice-guide + style-guide — NOT content-lessons.
    assert any("Approval gate" in text for text in system_texts)  # 4-lessons-loop.md
    assert voice.voice_guide in system_texts
    assert voice.style_guide in system_texts
    if voice.content_lessons:
        assert not any(voice.content_lessons in text for text in system_texts)

    # T2 (variable tail): the diff + existing content-lessons (dedupe) + the JSON contract.
    tail = prompt.messages[0]["content"]
    assert diff_text in tail
    assert voice.content_lessons in tail
    assert "JSON array" in tail
    assert "Token vs Storage" in tail

    # no caching — single call per piece, sub-floor prefix (§9-b).
    assert all("cache_control" not in block for block in prompt.system)


# --- prompts.parse_candidates ----------------------------------------------------------------


def test_parse_candidates_plain_json():
    text = _lessons_json(("cut a triad", "Avoid rule-of-three lists unless each item is distinct."))
    candidates = parse_candidates(text)
    assert candidates == [
        {
            "observed_change": "cut a triad",
            "generalizable_rule": "Avoid rule-of-three lists unless each item is distinct.",
        }
    ]


def test_parse_candidates_tolerates_prose_wrapper():
    wrapped = "Here you go:\n```json\n" + _lessons_json(("x", "y")) + "\n```"
    assert parse_candidates(wrapped) == [{"observed_change": "x", "generalizable_rule": "y"}]


def test_parse_candidates_empty_array():
    assert parse_candidates("[]") == []


def test_parse_candidates_drops_items_without_a_rule():
    text = json.dumps([{"observed_change": "no rule here"}, {"generalizable_rule": "keep me"}])
    assert parse_candidates(text) == [{"observed_change": "", "generalizable_rule": "keep me"}]


def test_parse_candidates_raises_on_garbage():
    with pytest.raises(LessonsParseError):
        parse_candidates("not json at all")


def test_parse_candidates_raises_on_non_array_json():
    with pytest.raises(LessonsParseError):
        parse_candidates('{"not": "an array"}')


# --- LessonsService.propose -------------------------------------------------------------------


async def test_propose_persists_deduped_lessons_to_mongo(
    store: WorkStateStore, git_brain: GitBrain, content_store: GitContentStore
):
    final_text = content_store.read_draft(SLUG)
    sha = content_store.commit_revision(SLUG, final_text + "\n<!-- final -->\n", message="final")
    piece = await _piece(store, stage=PieceStage.lessons, latest_revision=sha)
    published = final_text + "\n<!-- final -->\n<!-- human tightened the opener -->\n"

    existing_lessons = git_brain.read_voice("demo-mira").content_lessons or ""
    existing_rule = next(
        line.lstrip("- ").strip()
        for line in existing_lessons.splitlines()
        if line.strip().startswith("-")
    )
    provider = FakeLessonsProvider(
        _lessons_json(
            ("tightened the opener", "Open with the sharpest claim, not the setup."),
            # A duplicate of a seed lesson already in demo-mira's content-lessons.md — must be
            # filtered even though the model was asked not to propose it (defensive dedupe).
            ("reused a number", existing_rule),
        )
    )
    service = LessonsService(store, git_brain, content_store, provider)

    proposed = await service.propose(piece.id, published_content=published)

    assert len(proposed) == 1
    assert proposed[0].generalizable_rule == "Open with the sharpest claim, not the setup."
    assert proposed[0].voice == "demo-mira"
    assert proposed[0].source_piece_id == piece.id
    assert LessonStatus(proposed[0].status) == LessonStatus.proposed

    stored = await store.lessons.by_piece(piece.id)
    assert len(stored) == 1

    # the call routed at the Opus tier (D14/§9-a).
    assert provider.calls[0]["step"] == PipelineStep.LESSONS
    assert provider.calls[0]["model"] == MODEL_GLM5  # LESSONS now GLM5 live default


async def test_propose_skips_the_call_when_diff_is_empty(
    store: WorkStateStore, git_brain: GitBrain, content_store: GitContentStore
):
    final_text = content_store.read_draft(SLUG)
    sha = content_store.commit_revision(SLUG, final_text + "\n<!-- final -->\n", message="final")
    piece = await _piece(store, stage=PieceStage.lessons, latest_revision=sha)
    provider = FakeLessonsProvider()
    service = LessonsService(store, git_brain, content_store, provider)

    proposed = await service.propose(piece.id, published_content=final_text + "\n<!-- final -->\n")

    assert proposed == []
    assert provider.calls == []  # no meaningful change → no wasted call


async def test_propose_falls_back_to_head_draft_without_latest_revision(
    store: WorkStateStore, git_brain: GitBrain, content_store: GitContentStore
):
    piece = await _piece(store, stage=PieceStage.lessons, latest_revision=None)
    head_draft = content_store.read_draft(SLUG)
    provider = FakeLessonsProvider(_lessons_json(("x", "a fresh generalizable rule")))
    service = LessonsService(store, git_brain, content_store, provider)

    proposed = await service.propose(piece.id, published_content=head_draft + "\nedited\n")

    assert len(proposed) == 1


async def test_propose_rejects_wrong_stage(
    store: WorkStateStore, git_brain: GitBrain, content_store: GitContentStore
):
    piece = await _piece(store, stage=PieceStage.finalized, latest_revision=None)
    service = LessonsService(store, git_brain, content_store, FakeLessonsProvider())

    with pytest.raises(NotInLessonsStage):
        await service.propose(piece.id, published_content="anything")


async def test_propose_unknown_piece_raises_keyerror(
    store: WorkStateStore, git_brain: GitBrain, content_store: GitContentStore
):
    service = LessonsService(store, git_brain, content_store, FakeLessonsProvider())
    with pytest.raises(KeyError):
        await service.propose("nonexistent", published_content="x")


async def test_propose_bad_model_output_raises_parse_error(
    store: WorkStateStore, git_brain: GitBrain, content_store: GitContentStore
):
    final_text = content_store.read_draft(SLUG)
    sha = content_store.commit_revision(SLUG, final_text + "\n<!-- final -->\n", message="final")
    piece = await _piece(store, stage=PieceStage.lessons, latest_revision=sha)
    provider = FakeLessonsProvider("not valid json")
    service = LessonsService(store, git_brain, content_store, provider)

    with pytest.raises(LessonsParseError):
        await service.propose(piece.id, published_content=final_text + "\nedited\n")


async def test_propose_without_provider_raises():
    service = LessonsService(store=None, brain=None, content=None, provider=None)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError):
        await service.propose("p1", published_content="x")


# --- LessonsService.propose_from_review_edits (cmw-reviewer-can-edit-doc) ---------------------


async def test_propose_from_review_edits_persists_deduped_lessons(
    store: WorkStateStore, git_brain: GitBrain, content_store: GitContentStore
):
    """Same proposal machinery as :meth:`propose`, entered from a review round's diff-detected
    edits instead of a published/edited final draft — and with no stage precondition: the piece
    below sits in ``review``, never ``lessons``."""
    piece = await _piece(store, stage=PieceStage.review, latest_revision=None)
    existing_lessons = git_brain.read_voice("demo-mira").content_lessons or ""
    existing_rule = next(
        line.lstrip("- ").strip()
        for line in existing_lessons.splitlines()
        if line.strip().startswith("-")
    )
    provider = FakeLessonsProvider(
        _lessons_json(
            ("tightened the opener", "Open with the sharpest claim, not the setup."),
            ("reused a number", existing_rule),  # duplicate of a seed lesson — filtered
        )
    )
    service = LessonsService(store, git_brain, content_store, provider)

    proposed = await service.propose_from_review_edits(
        piece.id,
        edits=[("The machine drafted this in its own voice.", "A reviewer rewrote this line.")],
    )

    assert len(proposed) == 1
    assert proposed[0].generalizable_rule == "Open with the sharpest claim, not the setup."
    assert proposed[0].voice == "demo-mira"
    assert proposed[0].source_piece_id == piece.id
    assert LessonStatus(proposed[0].status) == LessonStatus.proposed
    assert provider.calls[0]["step"] == PipelineStep.LESSONS
    assert provider.calls[0]["model"] == MODEL_GLM5  # LESSONS now GLM5 live default


async def test_propose_from_review_edits_skips_the_call_when_edits_is_empty(
    store: WorkStateStore, git_brain: GitBrain, content_store: GitContentStore
):
    piece = await _piece(store, stage=PieceStage.review, latest_revision=None)
    provider = FakeLessonsProvider()
    service = LessonsService(store, git_brain, content_store, provider)

    proposed = await service.propose_from_review_edits(piece.id, edits=[])

    assert proposed == []
    assert provider.calls == []


async def test_propose_from_review_edits_skips_the_call_when_diff_is_empty(
    store: WorkStateStore, git_brain: GitBrain, content_store: GitContentStore
):
    piece = await _piece(store, stage=PieceStage.review, latest_revision=None)
    provider = FakeLessonsProvider()
    service = LessonsService(store, git_brain, content_store, provider)

    proposed = await service.propose_from_review_edits(
        piece.id, edits=[("same text", "same text")]
    )

    assert proposed == []
    assert provider.calls == []  # no meaningful change → no wasted call


async def test_propose_from_review_edits_unknown_piece_raises_keyerror(
    store: WorkStateStore, git_brain: GitBrain, content_store: GitContentStore
):
    service = LessonsService(store, git_brain, content_store, FakeLessonsProvider())
    with pytest.raises(KeyError):
        await service.propose_from_review_edits("nonexistent", edits=[("a", "b")])


async def test_propose_from_review_edits_without_provider_raises():
    service = LessonsService(store=None, brain=None, content=None, provider=None)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError):
        await service.propose_from_review_edits("p1", edits=[("a", "b")])


# --- LessonsService.accept / reject (D12 human gate) ------------------------------------------


async def test_accept_commits_to_git_per_voice_and_flips_mongo(
    store: WorkStateStore, git_brain: GitBrain, content_store: GitContentStore
):
    piece = await _piece(store, stage=PieceStage.lessons, latest_revision=None)
    lesson = await store.lessons.insert(
        Lesson(
            voice="demo-mira",
            source_piece_id=piece.id,
            observed_change="softened a claim",
            generalizable_rule="Draft rule before edit.",
        )
    )
    service = LessonsService(store, git_brain, content_store, provider=None)

    accepted = await service.accept(lesson.id, rule_text="The human-edited final rule.", actor="alex@example.com")

    assert LessonStatus(accepted.status) == LessonStatus.accepted
    assert accepted.generalizable_rule == "The human-edited final rule."

    mira_lessons = content_store.repo.read_text(
        content_store._p("voice", "demo-mira", "content-lessons.md")
    )
    assert "The human-edited final rule." in mira_lessons
    # per-voice: never lands in another voice's file (§1.18).
    dana_lessons = content_store.repo.read_text(content_store._p("voice", "demo-dana", "content-lessons.md"))
    assert "The human-edited final rule." not in dana_lessons


async def test_accept_without_edit_uses_the_proposed_rule(
    store: WorkStateStore, git_brain: GitBrain, content_store: GitContentStore
):
    lesson = await store.lessons.insert(
        Lesson(voice="demo-dana", observed_change="x", generalizable_rule="Use the proposed phrasing.")
    )
    service = LessonsService(store, git_brain, content_store, provider=None)

    accepted = await service.accept(lesson.id)

    assert accepted.generalizable_rule == "Use the proposed phrasing."
    dana_lessons = content_store.repo.read_text(content_store._p("voice", "demo-dana", "content-lessons.md"))
    assert "Use the proposed phrasing." in dana_lessons


async def test_accept_not_pending_raises(store: WorkStateStore, git_brain: GitBrain, content_store: GitContentStore):
    lesson = await store.lessons.insert(
        Lesson(
            voice="demo-mira",
            observed_change="x",
            generalizable_rule="y",
            status=LessonStatus.rejected,
        )
    )
    service = LessonsService(store, git_brain, content_store, provider=None)
    with pytest.raises(LessonNotPending):
        await service.accept(lesson.id)


async def test_reject_never_touches_git(store: WorkStateStore, git_brain: GitBrain, content_store: GitContentStore):
    before = content_store.repo.read_text(content_store._p("voice", "demo-mira", "content-lessons.md"))
    lesson = await store.lessons.insert(
        Lesson(voice="demo-mira", observed_change="x", generalizable_rule="a one-off, not generalizable")
    )
    service = LessonsService(store, git_brain, content_store, provider=None)

    rejected = await service.reject(lesson.id, actor="alex@example.com")

    assert LessonStatus(rejected.status) == LessonStatus.rejected
    after = content_store.repo.read_text(content_store._p("voice", "demo-mira", "content-lessons.md"))
    assert before == after  # machine never self-commits — reject writes nothing to Git


async def test_reject_not_pending_raises(store: WorkStateStore, git_brain: GitBrain, content_store: GitContentStore):
    lesson = await store.lessons.insert(
        Lesson(
            voice="demo-mira",
            observed_change="x",
            generalizable_rule="y",
            status=LessonStatus.accepted,
        )
    )
    service = LessonsService(store, git_brain, content_store, provider=None)
    with pytest.raises(LessonNotPending):
        await service.reject(lesson.id)


async def test_accept_reject_unknown_lesson_raises_keyerror(
    store: WorkStateStore, git_brain: GitBrain, content_store: GitContentStore
):
    service = LessonsService(store, git_brain, content_store, provider=None)
    with pytest.raises(KeyError):
        await service.accept("nonexistent")
    with pytest.raises(KeyError):
        await service.reject("nonexistent")


async def test_preview_returns_git_diff_without_writing(
    store: WorkStateStore, git_brain: GitBrain, content_store: GitContentStore
):
    lesson = await store.lessons.insert(
        Lesson(voice="demo-mira", observed_change="cut the caveat", generalizable_rule="Lead with the number.")
    )
    path = content_store._p("voice", "demo-mira", "content-lessons.md")
    before = content_store.repo.read_text(path)
    service = LessonsService(store, git_brain, content_store, provider=None)

    got, preview_path, preview_before, preview_after, rule = await service.preview(lesson.id)
    assert got.id == lesson.id
    assert preview_path == path
    assert preview_before == before
    assert rule == "Lead with the number."
    assert f"- {rule}" in preview_after
    assert content_store.repo.read_text(path) == before


async def test_decide_batch_accepts_some_and_collects_errors(
    store: WorkStateStore, git_brain: GitBrain, content_store: GitContentStore
):
    a = await store.lessons.insert(
        Lesson(voice="demo-mira", observed_change="a", generalizable_rule="Rule A.")
    )
    b = await store.lessons.insert(
        Lesson(voice="demo-mira", observed_change="b", generalizable_rule="Rule B.")
    )
    already = await store.lessons.insert(
        Lesson(
            voice="demo-mira",
            observed_change="c",
            generalizable_rule="Rule C.",
            status=LessonStatus.accepted,
        )
    )
    service = LessonsService(store, git_brain, content_store, provider=None)
    decided, errors = await service.decide_batch(
        [a.id, already.id, b.id], action="accept"
    )
    assert {item.generalizable_rule for item in decided} == {"Rule A.", "Rule B."}
    assert len(errors) == 1
    assert errors[0][0] == already.id
    lessons_file = content_store.repo.read_text(
        content_store._p("voice", "demo-mira", "content-lessons.md")
    )
    assert "Rule A." in lessons_file
    assert "Rule B." in lessons_file
