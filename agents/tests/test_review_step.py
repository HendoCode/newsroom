"""IncorporateStep tests, end to end (feedback-intake.md; open-decisions Item 7; §1.9).

Covers the acceptance bar directly: collect + classify (Sonnet) + apply (Opus) + route (no silent
drops) + re-council + explicit round boundaries, with the provider and Docs API mocked/guarded.
"""

from __future__ import annotations

import json

import pytest

from app.llm.budget import RunBudget
from app.llm.pricing import Usage, cost_usd
from app.llm.provider import LLMProvider, LLMResult
from app.llm.tiering import MODEL_GLM5, MODEL_OPUS, MODEL_SONNET, PipelineStep
from app.models import (
    DocRef,
    FeedbackStatus,
    FeedbackType,
    Job,
    JobStatus,
    JobType,
    Piece,
    PieceStage,
    ReviewRound,
    ReviewRoundStatus,
    ShareMode,
)
from app.orchestration import JobRunner, PieceMachine, StepRegistry
from app.orchestration.retry import PermanentStepError, RefusalError
from app.orchestration.steps import StepContext
from app.orchestration.stub_step import StubStep
from app.render.editorial import strip_editorial_block
from app.review.docs_client import CommentThread
from app.review.step import IncorporateStep

GOOD_REWRITE = """<!DOCTYPE html>
<html><head><title>t</title></head><body>
<article><h1>Title</h1><p>Tightened prose.</p></article>
<hr>
<section class="editorial" aria-label="Editorial annotations, not for publication">
<h3>Editorial annotations</h3>
<p><span class="tag">[GAP]</span> still need X</p>
</section>
</body></html>"""


class FakeDocsClient:
    def __init__(self, comments: list[CommentThread], document_html: str) -> None:
        self._comments = comments
        self._document_html = document_html
        self.replies: list[tuple[str, str, str]] = []

    async def list_comments(self, doc_id: str) -> list[CommentThread]:
        return self._comments

    async def get_document_html(self, doc_id: str) -> str:
        return self._document_html

    async def reply_to_comment(self, doc_id: str, comment_id: str, reply: str) -> None:
        self.replies.append((doc_id, comment_id, reply))


class FailingReplyDocsClient(FakeDocsClient):
    async def reply_to_comment(self, doc_id: str, comment_id: str, reply: str) -> None:
        raise RuntimeError("Drive API hiccup")


class QueuedProvider(LLMProvider):
    """Returns queued results in call order; records ``step``/``model`` for assertions."""

    def __init__(self, results: list[LLMResult]) -> None:
        self._results = list(results)
        self.calls: list[dict[str, object]] = []

    async def complete(
        self, *, step, model, system, messages, max_tokens, effort=None, thinking=None, tools=None, cache=False, budget=None
    ):
        if budget is not None:
            budget.check()
        self.calls.append(
            {"step": step, "model": model, "system": system, "messages": messages, "thinking": thinking}
        )
        result = self._results.pop(0)
        if budget is not None:
            budget.charge(model, result.usage)
        return result

    def stream(self, **kwargs):
        raise NotImplementedError

    async def count_tokens(self, *, model, system, messages):
        return 0


async def _piece(store, *, stage: PieceStage = PieceStage.incorporating, **extra) -> Piece:
    piece = Piece(slug="the-board-on-the-wall", voice="demo-mira", stage=stage, **extra)
    return await store.pieces.insert(piece)


async def _open_round(
    store,
    piece: Piece,
    content_store,
    *,
    doc_id: str | None = "doc-1",
    share_mode: ShareMode = ShareMode.internal,
) -> ReviewRound:
    sha = content_store.revision_history(piece.slug, max_count=1)[0].sha
    round_ = ReviewRound(
        piece_id=piece.id,
        round_number=1,
        minted_from_revision=sha,
        doc=DocRef(doc_id=doc_id, url="https://docs.google.com/x", share_mode=share_mode),
        status=ReviewRoundStatus.open,
    )
    return await store.review_rounds.insert(round_)


def _ctx(store, piece: Piece, provider, brain, content, *, budget=None) -> StepContext:
    job = Job(type=JobType.incorporate, piece_id=piece.id, status=JobStatus.running)
    return StepContext(
        job=job, store=store, budget=budget or RunBudget(), piece=piece, provider=provider, brain=brain, content=content
    )


# --- happy path -----------------------------------------------------------------------------


async def test_incorporate_happy_path_applies_fixes_routes_others_and_archives(
    store, git_brain, content_store
):
    piece = await _piece(store)
    round_ = await _open_round(store, piece, content_store)
    unchanged_html = content_store.read_draft(piece.slug)
    docs = FakeDocsClient(
        comments=[
            CommentThread(comment_id="c1", author="Alice", content="tighten the opening", resolved=False),
            CommentThread(comment_id="c2", author="Bob", content="unrelated tangent", resolved=False),
        ],
        document_html=unchanged_html,  # no diff-detected edits — deterministic item count
    )
    provider = QueuedProvider(
        [
            LLMResult(
                text='[{"type": "editorial-fix"}, {"type": "out-of-scope"}]',
                model=MODEL_SONNET,
                stop_reason="end_turn",
                usage=Usage(input_tokens=10, output_tokens=5),
                cost_usd=0.0,
            ),
            LLMResult(
                text=GOOD_REWRITE,
                model=MODEL_OPUS,
                stop_reason="end_turn",
                usage=Usage(input_tokens=100, output_tokens=50),
                cost_usd=0.0,
            ),
        ]
    )
    step = IncorporateStep(docs_client=docs, brain=git_brain, content=content_store)
    ctx = _ctx(store, piece, provider, git_brain, content_store)

    result = await step.run(ctx)

    assert provider.calls[0]["step"] == PipelineStep.FEEDBACK_CLASSIFY
    assert provider.calls[0]["model"] == MODEL_GLM5  # FEEDBACK_CLASSIFY now GLM5 live default
    assert provider.calls[1]["step"] == PipelineStep.REWRITE
    assert provider.calls[1]["model"] == MODEL_GLM5  # REWRITE now GLM5 live default
    assert result.usage.input_tokens == 110

    updated = await store.pieces.get(piece.id)
    assert updated.latest_revision and updated.latest_revision != round_.minted_from_revision
    assert updated.open_gaps == 1
    assert content_store.read_draft(piece.slug) == GOOD_REWRITE

    items = await store.feedback.by_round(round_.id)
    assert len(items) == 2
    fix = next(i for i in items if i.type == FeedbackType.editorial_fix)
    scope = next(i for i in items if i.type == FeedbackType.out_of_scope)
    assert fix.status == FeedbackStatus.applied
    assert scope.status == FeedbackStatus.rejected

    vault = await store.spikes.vault()
    assert len(vault) == 1  # the out-of-scope item parked, never discarded

    archived = await store.review_rounds.get(round_.id)
    assert archived.status == ReviewRoundStatus.archived
    assert any("editorial-fix" in line for line in archived.routing_log)
    assert any("out-of-scope" in line for line in archived.routing_log)

    # close the loop: both comments were replied to.
    assert {c[1] for c in docs.replies} == {"c1", "c2"}
    assert any("committed revision" in n for n in result.notes)


# --- cmw-internal-round-editorial-diff-asymmetry: the editorial block must never read as reviewer
# feedback on an internal round, and external rounds must stay unaffected -------------------------


async def test_incorporate_internal_round_editorial_block_is_not_phantom_feedback(
    store, git_brain, content_store
):
    """An internal round's Doc genuinely keeps the editorial block (its wrapper doesn't survive
    the round trip, but the child elements do). Before this fix, IncorporateStep's diff base always
    stripped the Git side regardless of share mode, so an untouched internal round would classify
    its own GAP notes as reviewer feedback and route/rewrite off them."""
    piece = await _piece(store)
    await _open_round(store, piece, content_store, share_mode=ShareMode.internal)
    unchanged_html = content_store.read_draft(piece.slug)  # raw revision — block kept, as-is
    docs = FakeDocsClient(comments=[], document_html=unchanged_html)
    provider = QueuedProvider([])  # popping would IndexError — proves no call happens
    step = IncorporateStep(docs_client=docs, brain=git_brain, content=content_store)

    result = await step.run(_ctx(store, piece, provider, git_brain, content_store))

    assert provider.calls == []  # no phantom feedback item ever reached classify
    assert any("no comments/edits collected" in n for n in result.notes)


async def test_incorporate_external_round_editorial_block_still_stripped_from_diff_base(
    store, git_brain, content_store
):
    """External rounds are unaffected by this fix — the Doc never had the editorial block, so the
    diff base must still strip it, exactly as before."""
    piece = await _piece(store)
    await _open_round(store, piece, content_store, share_mode=ShareMode.external)
    unchanged_html = strip_editorial_block(content_store.read_draft(piece.slug))
    docs = FakeDocsClient(comments=[], document_html=unchanged_html)
    provider = QueuedProvider([])
    step = IncorporateStep(docs_client=docs, brain=git_brain, content=content_store)

    result = await step.run(_ctx(store, piece, provider, git_brain, content_store))

    assert provider.calls == []
    assert any("no comments/edits collected" in n for n in result.notes)


# --- empty / all-routed rounds: no wasted LLM calls -----------------------------------------


async def test_incorporate_empty_round_skips_calls_and_archives(store, git_brain, content_store):
    piece = await _piece(store)
    round_ = await _open_round(store, piece, content_store)
    unchanged_html = content_store.read_draft(piece.slug)
    docs = FakeDocsClient(comments=[], document_html=unchanged_html)
    provider = QueuedProvider([])  # popping would IndexError — proves no call happens
    step = IncorporateStep(docs_client=docs, brain=git_brain, content=content_store)

    result = await step.run(_ctx(store, piece, provider, git_brain, content_store))

    assert provider.calls == []
    assert any("no comments/edits collected" in n for n in result.notes)
    updated = await store.pieces.get(piece.id)
    assert updated.latest_revision is None
    archived = await store.review_rounds.get(round_.id)
    assert archived.status == ReviewRoundStatus.archived


async def test_incorporate_all_non_fix_items_skips_rewrite(store, git_brain, content_store):
    piece = await _piece(store)
    await _open_round(store, piece, content_store)
    unchanged_html = content_store.read_draft(piece.slug)
    docs = FakeDocsClient(
        comments=[CommentThread(comment_id="c1", content="unrelated")], document_html=unchanged_html
    )
    provider = QueuedProvider(
        [LLMResult(text='[{"type": "out-of-scope"}]', model=MODEL_SONNET, stop_reason="end_turn", usage=Usage(), cost_usd=0.0)]
    )
    step = IncorporateStep(docs_client=docs, brain=git_brain, content=content_store)

    result = await step.run(_ctx(store, piece, provider, git_brain, content_store))

    assert len(provider.calls) == 1  # classify only — rewrite never called
    assert any("no editorial-fix items to apply this round" in n for n in result.notes)
    updated = await store.pieces.get(piece.id)
    assert updated.latest_revision is None


# --- failure paths ---------------------------------------------------------------------------


async def test_incorporate_raises_when_no_review_round_exists(store, git_brain, content_store):
    piece = await _piece(store)
    step = IncorporateStep(docs_client=FakeDocsClient([], ""), brain=git_brain, content=content_store)

    with pytest.raises(PermanentStepError):
        await step.run(_ctx(store, piece, QueuedProvider([]), git_brain, content_store))


async def test_incorporate_raises_when_round_already_archived(store, git_brain, content_store):
    piece = await _piece(store)
    round_ = await _open_round(store, piece, content_store)
    await store.review_rounds.update(round_.id, {"status": ReviewRoundStatus.archived})
    step = IncorporateStep(docs_client=FakeDocsClient([], ""), brain=git_brain, content=content_store)

    with pytest.raises(PermanentStepError):
        await step.run(_ctx(store, piece, QueuedProvider([]), git_brain, content_store))


async def test_incorporate_reply_failure_is_best_effort_and_still_succeeds(store, git_brain, content_store):
    piece = await _piece(store)
    round_ = await _open_round(store, piece, content_store)
    unchanged_html = content_store.read_draft(piece.slug)
    docs = FailingReplyDocsClient(
        comments=[CommentThread(comment_id="c1", content="tighten this")], document_html=unchanged_html
    )
    provider = QueuedProvider(
        [
            LLMResult(text='[{"type": "editorial-fix"}]', model=MODEL_SONNET, stop_reason="end_turn", usage=Usage(), cost_usd=0.0),
            LLMResult(text=GOOD_REWRITE, model=MODEL_OPUS, stop_reason="end_turn", usage=Usage(), cost_usd=0.0),
        ]
    )
    step = IncorporateStep(docs_client=docs, brain=git_brain, content=content_store)

    result = await step.run(_ctx(store, piece, provider, git_brain, content_store))

    assert any("reply_to_comment failed" in n for n in result.notes)
    updated = await store.pieces.get(piece.id)
    assert updated.latest_revision  # the job still succeeded despite the reply failure
    archived = await store.review_rounds.get(round_.id)
    assert archived.status == ReviewRoundStatus.archived


async def test_incorporate_failed_rewrite_leaves_no_partial_routing(store, git_brain, content_store):
    """A rewrite refusal must leave zero side effects — not even the OTHER (non-fix) items in the
    same round, since a human retry on the still-open round would otherwise re-route them a second
    time (duplicate Interviews/Spikes/FeedbackItems)."""
    piece = await _piece(store, owner="owner@x.com")
    round_ = await _open_round(store, piece, content_store)
    unchanged_html = content_store.read_draft(piece.slug)
    docs = FakeDocsClient(
        comments=[
            CommentThread(comment_id="c1", content="tighten this"),
            CommentThread(comment_id="c2", content="can we name this company publicly?"),
        ],
        document_html=unchanged_html,
    )
    provider = QueuedProvider(
        [
            LLMResult(
                text='[{"type": "editorial-fix"}, {"type": "clearance"}]',
                model=MODEL_SONNET, stop_reason="end_turn", usage=Usage(), cost_usd=0.0,
            ),
            LLMResult(text="", model=MODEL_OPUS, stop_reason="refusal", usage=Usage(), cost_usd=0.0),
        ]
    )
    step = IncorporateStep(docs_client=docs, brain=git_brain, content=content_store)

    with pytest.raises(RefusalError):
        await step.run(_ctx(store, piece, provider, git_brain, content_store))

    assert await store.feedback.by_round(round_.id) == []
    assert await store.spikes.vault() == []
    assert (await store.interviews.by_piece(piece.id)) == []
    assert docs.replies == []  # nothing was routed, so nothing was replied to either
    still_open = await store.review_rounds.get(round_.id)
    assert still_open.status == ReviewRoundStatus.open
    updated = await store.pieces.get(piece.id)
    assert updated.latest_revision is None


# --- review-edit-sourced lesson proposals (cmw-reviewer-can-edit-doc) ------------------------

EDITED_PHRASE_OLD = (
    "A schedule is not a list of sailings. It is an argument about who is where, and the board was\n"
    "  the form that argument took. Everybody in the building could read the state of it without asking\n"
    "  anybody for anything."
)
EDITED_PHRASE_NEW = (
    "A schedule is not a list of sailings. It is an argument about who is where, and the board was\n"
    "  the form that argument took. Anyone in the building could read its state without asking\n"
    "  anybody for anything."
)


def _lessons_json(*pairs: tuple[str, str]) -> str:
    return json.dumps(
        [{"observed_change": change, "generalizable_rule": rule} for change, rule in pairs]
    )


def _edited_docs(content_store, piece: Piece) -> FakeDocsClient:
    """A Doc whose live HTML differs from the frozen revision by exactly one paragraph edit —
    a real diff-detected, structural-diff-eligible change (channel="google-docs-edit")."""
    unchanged_html = content_store.read_draft(piece.slug)
    assert EDITED_PHRASE_OLD in unchanged_html
    edited_html = unchanged_html.replace(EDITED_PHRASE_OLD, EDITED_PHRASE_NEW)
    return FakeDocsClient(comments=[], document_html=edited_html)


async def test_incorporate_proposes_lesson_from_applied_edit(store, git_brain, content_store):
    piece = await _piece(store)
    await _open_round(store, piece, content_store)
    docs = _edited_docs(content_store, piece)
    provider = QueuedProvider(
        [
            LLMResult(text='[{"type": "editorial-fix"}]', model=MODEL_SONNET, stop_reason="end_turn", usage=Usage(), cost_usd=0.0),
            LLMResult(text=GOOD_REWRITE, model=MODEL_OPUS, stop_reason="end_turn", usage=Usage(), cost_usd=0.0),
            LLMResult(
                text=_lessons_json(
                    ("tightened a transition", "Cut throwaway transition phrases; lead with the claim.")
                ),
                model=MODEL_OPUS,
                stop_reason="end_turn",
                usage=Usage(input_tokens=200, output_tokens=40),
                cost_usd=0.0,
            ),
        ]
    )
    step = IncorporateStep(docs_client=docs, brain=git_brain, content=content_store)

    result = await step.run(_ctx(store, piece, provider, git_brain, content_store))

    assert len(provider.calls) == 3  # classify, rewrite, AND the new lessons-propose call
    assert provider.calls[2]["step"] == PipelineStep.LESSONS
    assert provider.calls[2]["model"] == MODEL_GLM5  # INCORPORATE now GLM5 live default

    lessons = await store.lessons.by_piece(piece.id)
    assert len(lessons) == 1
    assert lessons[0].voice == "demo-mira"
    assert lessons[0].source_piece_id == piece.id
    assert lessons[0].generalizable_rule == "Cut throwaway transition phrases; lead with the claim."
    assert any("lesson(s) proposed" in n for n in result.notes)


async def test_incorporate_lesson_proposal_failure_is_best_effort(store, git_brain, content_store):
    """A lessons-call hiccup (here: unparseable output) must never undo the rewrite/routing that
    already succeeded above it — mirrors reply_to_comment's own best-effort discipline."""
    piece = await _piece(store)
    round_ = await _open_round(store, piece, content_store)
    docs = _edited_docs(content_store, piece)
    provider = QueuedProvider(
        [
            LLMResult(text='[{"type": "editorial-fix"}]', model=MODEL_SONNET, stop_reason="end_turn", usage=Usage(), cost_usd=0.0),
            LLMResult(text=GOOD_REWRITE, model=MODEL_OPUS, stop_reason="end_turn", usage=Usage(), cost_usd=0.0),
            LLMResult(text="not valid json", model=MODEL_OPUS, stop_reason="end_turn", usage=Usage(), cost_usd=0.0),
        ]
    )
    step = IncorporateStep(docs_client=docs, brain=git_brain, content=content_store)

    result = await step.run(_ctx(store, piece, provider, git_brain, content_store))

    assert any("lesson proposal failed" in n for n in result.notes)
    assert await store.lessons.by_piece(piece.id) == []
    updated = await store.pieces.get(piece.id)
    assert updated.latest_revision  # the round still succeeded despite the lesson-call failure
    archived = await store.review_rounds.get(round_.id)
    assert archived.status == ReviewRoundStatus.archived


# --- plugged into the real state machine ----------------------------------------------------


async def test_incorporate_plugs_into_machine_and_re_runs_council(store, git_brain, content_store):
    piece = await _piece(store, stage=PieceStage.review)
    await _open_round(store, piece, content_store)
    unchanged_html = content_store.read_draft(piece.slug)
    docs = FakeDocsClient(
        comments=[CommentThread(comment_id="c1", content="tighten this")], document_html=unchanged_html
    )
    provider = QueuedProvider(
        [
            LLMResult(text='[{"type": "editorial-fix"}]', model=MODEL_SONNET, stop_reason="end_turn", usage=Usage(), cost_usd=0.0),
            LLMResult(text=GOOD_REWRITE, model=MODEL_OPUS, stop_reason="end_turn", usage=Usage(), cost_usd=0.0),
        ]
    )
    registry = StepRegistry()
    registry.register(IncorporateStep(docs_client=docs, brain=git_brain, content=content_store))
    registry.register(StubStep(JobType.council))  # council is a separate ticket; stub stands in
    runner = JobRunner(store, registry, provider=provider)
    machine = PieceMachine(store, runner)

    updated = await machine.reviews_done(piece.id, actor="demo-mira@x")

    assert updated.stage == PieceStage.review  # incorporating -> council (stub) -> review
    assert updated.latest_revision


async def test_incorporate_failure_flags_piece_back_to_review(store, git_brain, content_store):
    piece = await _piece(store, stage=PieceStage.review)
    round_ = await _open_round(store, piece, content_store)
    unchanged_html = content_store.read_draft(piece.slug)
    docs = FakeDocsClient(
        comments=[CommentThread(comment_id="c1", content="tighten this")], document_html=unchanged_html
    )
    provider = QueuedProvider(
        [
            LLMResult(text='[{"type": "editorial-fix"}]', model=MODEL_SONNET, stop_reason="end_turn", usage=Usage(), cost_usd=0.0),
            LLMResult(text="", model=MODEL_OPUS, stop_reason="refusal", usage=Usage(), cost_usd=0.0),
        ]
    )
    registry = StepRegistry()
    registry.register(IncorporateStep(docs_client=docs, brain=git_brain, content=content_store))
    runner = JobRunner(store, registry, provider=provider)
    machine = PieceMachine(store, runner)

    updated = await machine.reviews_done(piece.id, actor="demo-mira@x")

    assert updated.stage == PieceStage.review  # flagged back, round untouched (D4/D16b)
    failures = await machine.open_failures(updated.id)
    assert len(failures) == 1
    assert failures[0].error is not None and failures[0].error.code == "refusal"
    still_open = await store.review_rounds.get(round_.id)
    assert still_open.status == ReviewRoundStatus.open  # a failed rewrite never archives the round


async def test_incorporate_brain_authored_piece_without_transcript_completes_reviews_done(
    store, git_brain, content_store
):
    """cmw-lessons-loop Ship 1 regression — the live F1 permanent failure: every brain-authored
    (brain_synced) piece reaches `review` with draft prose but NO transcript.md by design, and the
    rewrite's missing-transcript guard (added by cmw-incorporate-missing-transcript when the
    state looked impossible) turned every reviews-done on such a piece into a permanent
    `retryable=False` failure — verified live on `auditing-the-wrong-line-item` (scout report
    cmw-lessons-loop). The rewrite must now ground in the existing revision + sources.md with the
    shared invent-nothing block and complete the round normally."""
    content_store.commit_revision(
        "seeded-no-transcript",
        "<html><body><article><p>seeded straight into review</p></article></body></html>",
        sources_md="- [AWS blog](https://example.com/aws) — the cited figure",
        message="seed directly into review, no interview ever run",
    )
    piece = await store.pieces.insert(
        Piece(slug="seeded-no-transcript", voice="demo-mira", stage=PieceStage.review)
    )
    round_ = await _open_round(store, piece, content_store)
    docs = FakeDocsClient(
        comments=[CommentThread(comment_id="c1", content="tighten this")],
        document_html=content_store.read_draft(piece.slug),
    )
    provider = QueuedProvider(
        [
            LLMResult(text='[{"type": "editorial-fix"}]', model=MODEL_SONNET, stop_reason="end_turn", usage=Usage(), cost_usd=0.0),
            LLMResult(text=GOOD_REWRITE, model=MODEL_OPUS, stop_reason="end_turn", usage=Usage(), cost_usd=0.0),
        ]
    )
    registry = StepRegistry()
    registry.register(IncorporateStep(docs_client=docs, brain=git_brain, content=content_store))
    runner = JobRunner(store, registry, provider=provider)
    machine = PieceMachine(store, runner)

    updated = await machine.reviews_done(piece.id, actor="demo-mira@x")

    # The round completes — no permanent failure, nothing flagged. The chain then stops at
    # `council` (no council step registered here — exactly the clean stop the machine's
    # has()-guard defines), which is what a real deploy continues into the re-council.
    assert updated.stage == PieceStage.council
    assert await machine.open_failures(updated.id) == []
    assert updated.latest_revision and updated.latest_revision != round_.minted_from_revision
    assert content_store.read_draft(piece.slug) == GOOD_REWRITE  # the rewrite committed
    archived = await store.review_rounds.get(round_.id)
    assert archived.status == ReviewRoundStatus.archived
    # The transcript really is absent — the rewrite grounded in revision + sources, not a transcript.
    with pytest.raises(OSError):
        content_store.read_transcript(piece.slug)
    rewrite_call = provider.calls[1]
    system_texts = rewrite_call["system"]
    assert any("no interview transcript" in t.lower() for t in system_texts)
    assert any("invent nothing" in t.lower() for t in system_texts)
    # The grounding block carries sources.md; the transcript it replaces is genuinely absent.
    sources_at_seed = "- [AWS blog](https://example.com/aws) — the cited figure"
    assert any(sources_at_seed in t for t in system_texts)
