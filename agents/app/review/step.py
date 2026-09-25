"""The ``incorporating`` batch step (feedback-intake.md; open-decisions Item 7; §1.9).

Plugs :class:`IncorporateStep` into the ``BatchStep`` seam for ``JobType.incorporate``. The human
"reviews done" trigger (:meth:`~app.orchestration.machine.PieceMachine.reviews_done`) has already
moved the piece into ``incorporating`` and dispatched this job by the time :meth:`run` is called;
on success the (unmodified) machine advances ``incorporating → council`` (re-running the council on
the new revision) — this step never touches piece stage itself.

The round-trip, end to end, per round:

1. **Find the open round** — no open :class:`~app.models.ReviewRound` means "reviews done" fired
   with nothing minted; a deterministic failure (flag, don't retry), never a silent no-op.
2. **Collect** — every comment + diff-detected inline edit (:mod:`app.review.collect`), best-effort
   on the edit-diff half only.
3. **Classify** — one batched Sonnet call (:mod:`app.review.classify`). Empty round → skip straight
   to archiving (Item 7's "empty round... warns but allows it — re-council on the unchanged
   revision").
4. **Apply** — the ``editorial-fix`` items go to the Opus rewrite (:mod:`app.review.rewrite`); a new
   Revision commits to Git **only on success** (D4/D16b), and the open-GAP count mirrors onto the
   Piece the same way the draft step does.
4a. **Propose lessons from applied edits** (cmw-reviewer-can-edit-doc; reviewers can now edit the
   Doc directly, not just comment on it — :mod:`app.review.mint`): among the applied fixes, the
   diff-detected ones (``channel="google-docs-edit"``, a demonstrated rewrite, not a plain
   instruction) go to :meth:`~app.lessons.service.LessonsService.propose_from_review_edits`.
   Best-effort (:meth:`_propose_edit_lessons`) — a lessons-call hiccup here must never undo the
   rewrite/routing that already succeeded above, mirroring point 6's own best-effort discipline.
5. **Route** — every other item (:mod:`app.review.routing`): info-gap → targeted interview,
   clearance → owner, out-of-scope → Vault. No silent drops.
6. **Close the loop** — ``replyToComment`` on every Doc-anchored item, best-effort (a Docs hiccup
   here never fails the whole job — mirrors Item 4's "one editor's failure completes-with-gap").
   A diff-detected edit has no comment thread to reply to (``comment_id=None``) and gets no
   individual or summary acknowledgement at all — a deliberate, accepted trade-off (Hendo,
   cmw-reviewer-can-edit-doc: "the lack of reviewer edits and comments [being acknowledged] is OK
   for the org I work for"), not an oversight.
7. **Archive the round** — the Doc stops being authoritative; the routing log is appended to
   :class:`~app.models.ReviewRound.routing_log` for the piece-detail activity log to read back.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.git import open_brain, open_content_store
from app.lessons.service import LessonsService
from app.llm.pricing import Usage
from app.models import (
    FeedbackItem,
    FeedbackStatus,
    FeedbackType,
    JobType,
    Piece,
    ReviewRoundStatus,
    ShareMode,
)
from app.orchestration.retry import PermanentStepError
from app.orchestration.steps import BatchStep, StepContext, StepResult
from app.review.classify import ClassifiedFeedback, classify_feedback
from app.review.collect import RawFeedbackItem, gather_raw_items
from app.review.docs_client import ReviewDocsClient
from app.review.rewrite import count_open_gaps, rewrite_revision
from app.review.routing import route_non_fix_items

if TYPE_CHECKING:
    from app.git import GitBrain, GitContentStore


class IncorporateStep(BatchStep):
    job_type = JobType.incorporate

    def __init__(
        self,
        *,
        docs_client: ReviewDocsClient,
        brain: GitBrain | None = None,
        content: GitContentStore | None = None,
        max_tokens: int = 8192,
        effort: str | None = None,
    ) -> None:
        self.docs_client = docs_client
        self._brain = brain
        self._content = content
        self._max_tokens = max_tokens
        self._effort = effort

    async def run(self, ctx: StepContext) -> StepResult:
        piece = ctx.piece
        if piece is None or piece.id is None:
            raise PermanentStepError(
                "incorporate step requires a persisted piece (incorporate is never pieceless)"
            )
        if ctx.provider is None:
            raise PermanentStepError("no LLM provider configured for the incorporate step")

        brain = self._brain or ctx.brain or open_brain()
        content = self._content or ctx.content or open_content_store()

        round_ = await ctx.store.review_rounds.latest_for_piece(piece.id)
        if round_ is None or ReviewRoundStatus(round_.status) != ReviewRoundStatus.open:
            raise PermanentStepError(
                f"no open review round for piece {piece.slug!r} — mint a Doc before "
                "firing 'reviews done'"
            )
        assert round_.id is not None

        await ctx.beat()
        notes: list[str] = []
        routing_log: list[str] = []
        replies: list[tuple[str, str]] = []
        usage = Usage()

        raw_items: list[RawFeedbackItem] = []
        if round_.doc.doc_id:
            minted_html = content.read_revision(piece.slug, round_.minted_from_revision)
            raw_items, diff_ok = await gather_raw_items(
                self.docs_client,
                doc_id=round_.doc.doc_id,
                minted_from_html=minted_html,
                share_mode=ShareMode(round_.doc.share_mode),
            )
            if not diff_ok:
                notes.append("edit-diff detection degraded this round — comments still collected")

        if not raw_items:
            notes.append(
                f"round {round_.round_number}: no comments/edits collected — re-council on the "
                "unchanged revision"
            )
        else:
            await ctx.beat()
            classified = await classify_feedback(
                ctx.provider, piece=piece, items=raw_items, budget=ctx.budget
            )
            usage = usage + classified.usage

            fixes = [c for c in classified.items if c.type == FeedbackType.editorial_fix]
            others = [c for c in classified.items if c.type != FeedbackType.editorial_fix]

            # Run every LLM call that can still raise (classify above, rewrite here) BEFORE any
            # persistence below. A rewrite refusal/inline-GAP-leak must leave nothing written —
            # otherwise a human retry of "reviews done" on the still-open round would re-route
            # `others` a second time (duplicate Interviews/Spikes/FeedbackItems), which is worse
            # than the failure itself (D4/D16b: a step's persistence lands only on success).
            rewrite = None
            if fixes:
                await ctx.beat()
                rewrite = await rewrite_revision(
                    ctx.provider,
                    brain=brain,
                    content=content,
                    piece=piece,
                    fixes=[c.raw.ask for c in fixes],
                    round_number=round_.round_number,
                    max_tokens=self._max_tokens,
                    effort=self._effort,
                    budget=ctx.budget,
                )
                usage = usage + rewrite.usage

            if others:
                outcome = await route_non_fix_items(ctx.store, piece, round_.id, others)
                routing_log.extend(outcome.routing_log)
                replies.extend(outcome.replies)

            if rewrite is not None:
                sha = content.commit_revision(
                    piece.slug,
                    rewrite.draft_html,
                    message=f"incorporate: {piece.slug} round {round_.round_number} (job {ctx.job.id})",
                )
                open_gaps = count_open_gaps(rewrite.draft_html)
                await ctx.store.pieces.update(
                    piece.id, {"latest_revision": sha, "open_gaps": open_gaps}
                )
                for c in fixes:
                    await ctx.store.feedback.insert(
                        FeedbackItem(
                            piece_id=piece.id,
                            review_round_id=round_.id,
                            reviewer=c.raw.reviewer,
                            channel=c.raw.channel,
                            location=c.raw.location,
                            ask=c.raw.ask,
                            type=FeedbackType.editorial_fix,
                            status=FeedbackStatus.applied,
                            notes=f"applied to revision {sha[:8]}",
                        )
                    )
                    if c.raw.comment_id:
                        replies.append((c.raw.comment_id, f"Applied in revision {sha[:8]}."))
                routing_log.append(
                    f"{len(fixes)} editorial-fix item(s) applied → revision {sha[:8]}"
                )
                notes.append(f"committed revision {sha[:8]} for round {round_.round_number}")

                edit_fixes = [
                    c for c in fixes if c.raw.channel == "google-docs-edit" and c.raw.before is not None
                ]
                if edit_fixes:
                    await self._propose_edit_lessons(ctx, piece, brain, content, edit_fixes, notes)
            else:
                notes.append("no editorial-fix items to apply this round")

        await self._close_the_loop(round_.doc.doc_id, replies, notes)

        await ctx.store.review_rounds.update(
            round_.id,
            {
                "status": ReviewRoundStatus.archived,
                "routing_log": [*round_.routing_log, *routing_log],
            },
        )

        return StepResult(usage=usage, notes=[*notes, *routing_log])

    async def _close_the_loop(
        self, doc_id: str | None, replies: list[tuple[str, str]], notes: list[str]
    ) -> None:
        """``replyToComment`` on every Doc-anchored item — best-effort (Item 4: one failure warns
        and continues, it never fails the whole incorporate job)."""
        if not doc_id:
            return
        for comment_id, reply in replies:
            try:
                await self.docs_client.reply_to_comment(doc_id, comment_id, reply)
            except Exception as exc:  # noqa: BLE001 — closing the loop is best-effort
                notes.append(f"reply_to_comment failed for {comment_id}: {exc}")

    async def _propose_edit_lessons(
        self,
        ctx: StepContext,
        piece: Piece,
        brain: GitBrain,
        content: GitContentStore,
        edit_fixes: list[ClassifiedFeedback],
        notes: list[str],
    ) -> None:
        """Point 4a of the module docstring: propose lessons from this round's diff-detected,
        applied edits (Hendo, cmw-reviewer-can-edit-doc — "the edit is described to the model,
        which rewrites it in voice, and proposes a lesson"). Best-effort, like
        :meth:`_close_the_loop`'s ``reply_to_comment`` — this runs strictly *after* the round's
        revision/FeedbackItems already committed above, so a raise here (including a
        :class:`RunBudgetExceeded`) must never propagate: a human retry on a still-open round would
        re-run classify+rewrite+persist from scratch and duplicate them (the exact hazard the
        rewrite call's own pre-persistence ordering, above, already guards against). Swallowing the
        ceiling here doesn't weaken D14's "one hard stop" — ``budget.check()`` still raises before
        this call spends anything, so no extra spend occurs; it only means this one enrichment is
        skipped rather than failing an otherwise-successful round."""
        lessons_service = LessonsService(
            ctx.store, brain, content, ctx.provider, budget_factory=ctx.budget_factory
        )
        edits = [(c.raw.before, c.raw.after) for c in edit_fixes]
        try:
            proposed = await lessons_service.propose_from_review_edits(
                piece.id, edits=edits, budget=ctx.budget
            )
        except Exception as exc:  # noqa: BLE001 — lesson extraction is best-effort here
            notes.append(f"lesson proposal failed for {len(edit_fixes)} reviewer edit(s): {exc}")
            return
        if proposed:
            notes.append(f"{len(proposed)} lesson(s) proposed from reviewer edits this round")
