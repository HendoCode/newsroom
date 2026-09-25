"""The lessons-loop service (domain model §1.18; D12; cmw-context-assembly report §9).

Runs in the piece's ``lessons`` stage (§1.9 "batch + gate"), built on the merged state machine,
data layer, and LLM provider:

1. :meth:`propose` — diff the machine's final draft (Git, post-council/pre-human) against the
   author's actually-published/edited version (structurally, via :mod:`app.lessons.diff`), call
   Opus (D14 tier) to propose generalizable per-voice lessons deduped against the voice's existing
   ``content-lessons.md``, and persist them to Mongo as **pending** (:class:`~app.models.Lesson`,
   ``status=proposed``).
2. :meth:`propose_from_review_edits` (cmw-reviewer-can-edit-doc) — the same proposal machinery,
   entered from a **review round**'s diff-detected edits instead of a published/edited final
   draft. Hendo's decision: "the edit is described to the model, which rewrites it in voice, and
   proposes a lesson — today's behaviour plus the lesson." Proposed **immediately**, from
   :class:`~app.review.step.IncorporateStep`, while the piece is still mid-pipeline (``review``/
   ``incorporating``) rather than deferred to the piece's own ``lessons`` stage: the D12
   accept/reject gate below already operates on any pending :class:`~app.models.Lesson`
   regardless of its source piece's current stage (``GET /api/lessons/pending`` lists every
   proposal; voice-kit's accept/reject reads/writes Lesson docs directly) — deferring would only
   add a "carry this diff along until the piece happens to reach `lessons`" bookkeeping problem
   across however many review rounds/re-councils occur first, for no reader-visible benefit.
3. :meth:`accept` / :meth:`reject` — the D12 human gate. Only :meth:`accept` crosses into Git,
   via :meth:`~app.git.content.GitContentStore.commit_accepted_lesson`. **The machine never
   self-commits** — this service never calls that method except in direct response to an explicit
   human accept.

Lessons never cross voices: a proposal's ``voice`` is fixed from the source Piece at proposal time
and every Git write goes through that same voice's ``content-lessons.md`` (§1.18).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from app.git.brain import GitBrain, VoicePack
from app.git.content import GitContentStore
from app.lessons.diff import compute_diff
from app.lessons.errors import LessonNotPending, NotInLessonsStage
from app.lessons.prompts import MAX_TOKENS, build_lessons_prompt, parse_candidates
from app.llm.budget import RunBudget
from app.llm.provider import LLMProvider, LLMResult
from app.llm.tiering import PipelineStep, model_for_step
from app.models import Lesson, LessonStatus, Piece, PieceStage
from app.repositories import WorkStateStore


class LessonsService:
    """Proposes and (on human acceptance) commits per-voice content lessons for one piece."""

    def __init__(
        self,
        store: WorkStateStore,
        brain: GitBrain,
        content: GitContentStore,
        provider: LLMProvider | None = None,
        *,
        budget_factory: Callable[[], RunBudget] | None = None,
    ) -> None:
        self.store = store
        self.brain = brain
        self.content = content
        self.provider = provider
        # Each lessons proposal gets a fresh per-run ceiling. Default is unbounded; production
        # wires a real cost/token ceiling here — the one sanctioned hard block (D14).
        self._budget_factory = budget_factory or RunBudget

    async def propose(
        self,
        piece_id: str,
        *,
        published_content: str,
        budget: RunBudget | None = None,
    ) -> list[Lesson]:
        """Diff the final draft against ``published_content`` and propose deduped lessons.

        Only legal while the piece is in the ``lessons`` stage (§1.9). Returns ``[]`` without
        calling the model at all when the diff is empty — no meaningful change, nothing to learn.
        Every returned :class:`Lesson` is already persisted to Mongo with ``status=proposed``.
        """
        if self.provider is None:
            raise RuntimeError("LessonsService.propose requires an LLMProvider")
        piece = await self._get_piece(piece_id)
        if PieceStage(piece.stage) != PieceStage.lessons:
            raise NotInLessonsStage(
                f"piece {piece_id!r} is not in the lessons stage (stage={piece.stage})"
            )

        final_text = self._read_final_text(piece)
        diff_text = compute_diff(final_text, published_content)
        if not diff_text.strip():
            return []

        budget = budget or self._budget_factory()
        cost_before = budget.cost
        try:
            result, voice = await self._call_model(piece, diff_text, budget)
        finally:
            # Lands cost before the parse step below can raise (D14 — every real call is
            # counted; mirrors the interview engine's ``_charge`` and JobRunner's own
            # charge-on-failure). Only this entry point self-charges: propose_from_review_edits
            # below runs inside IncorporateStep's own JobRunner budget, which already lands the
            # whole step's spend onto the piece via PieceMachine._run_batch_chain — charging here
            # too would double-count it.
            delta = round(budget.cost - cost_before, 6)
        return await self._persist_candidates(piece, voice, result.text)

    async def propose_from_review_edits(
        self,
        piece_id: str,
        *,
        edits: list[tuple[str, str]],
        budget: RunBudget | None = None,
    ) -> list[Lesson]:
        """Propose lessons straight from a review round's diff-detected edits (Hendo,
        cmw-reviewer-can-edit-doc — see the module docstring's item 2 for the full "why now, why
        no stage gate" reasoning).

        ``edits`` is the round's ``(before, after)`` text pairs for every diff-detected edit that
        was actually applied as an editorial fix this round — comments-turned-fixes carry no such
        pair and are deliberately excluded upstream (:class:`~app.review.step.IncorporateStep`): a
        lesson needs a demonstrated rewrite, not a plain instruction. Returns ``[]`` without
        calling the model when ``edits`` is empty or nets to no meaningful diff.

        Unlike :meth:`propose`, this never self-charges ``Piece.cost_so_far`` — the caller already
        runs inside a :class:`~app.orchestration.jobs.JobRunner`-managed budget that lands the
        whole step's spend on the piece once, via the batch-chain's own accounting.
        """
        if self.provider is None:
            raise RuntimeError("LessonsService.propose_from_review_edits requires an LLMProvider")
        if not edits:
            return []
        piece = await self._get_piece(piece_id)
        before_text = "\n".join(before for before, _after in edits)
        after_text = "\n".join(after for _before, after in edits)
        diff_text = compute_diff(
            before_text, after_text, final_label="pre-edit", published_label="reviewer-edit"
        )
        if not diff_text.strip():
            return []

        result, voice = await self._call_model(piece, diff_text, budget or self._budget_factory())
        return await self._persist_candidates(piece, voice, result.text)

    async def _call_model(
        self, piece: Piece, diff_text: str, budget: RunBudget
    ) -> tuple[LLMResult, VoicePack]:
        voice = self.brain.read_voice(piece.voice)
        prompt = build_lessons_prompt(self.brain, self.content, piece, voice, diff_text)
        result = await self.provider.complete(
            step=PipelineStep.LESSONS,
            model=model_for_step(PipelineStep.LESSONS),
            system=prompt.system,
            messages=prompt.messages,
            max_tokens=MAX_TOKENS,
            cache=prompt.cache,
            budget=budget,
        )
        return result, voice

    async def _persist_candidates(
        self, piece: Piece, voice: VoicePack, response_text: str
    ) -> list[Lesson]:
        candidates = parse_candidates(response_text)
        existing_lower = (voice.content_lessons or "").lower()
        proposed: list[Lesson] = []
        for candidate in candidates:
            rule = candidate["generalizable_rule"]
            if rule.lower() in existing_lower:
                continue  # defensive dedupe backstop — the prompt already asks for this (§9-d-1)
            lesson = Lesson(
                voice=piece.voice,
                source_piece_id=piece.id,
                observed_change=candidate["observed_change"],
                generalizable_rule=rule,
                status=LessonStatus.proposed,
            )
            proposed.append(await self.store.lessons.insert(lesson))
        return proposed

    async def accept(
        self,
        lesson_id: str,
        *,
        rule_text: str | None = None,
        actor: str | None = None,
    ) -> Lesson:
        """The D12 accept gate: commit the (optionally human-edited) rule to
        ``voice/<voice>/content-lessons.md`` in Git, then flip the Mongo record to ``accepted``.

        ``rule_text`` covers the "edit" half of "accept/edit/reject in one click" — when supplied
        it overrides the proposed phrasing (and is what actually lands in Git and in Mongo).
        """
        lesson = await self._get_pending(lesson_id)
        final_rule = (rule_text if rule_text is not None else lesson.generalizable_rule).strip()
        if not final_rule:
            raise ValueError("accepted lesson rule text is empty")

        assert lesson.id is not None
        self.content.commit_accepted_lesson(
            lesson.voice,
            final_rule,
            author_name=actor,
            message=f"accept content lesson for {lesson.voice} (lesson {lesson.id})",
        )
        updated = await self.store.lessons.update(
            lesson.id,
            {"status": LessonStatus.accepted, "generalizable_rule": final_rule},
        )
        assert updated is not None
        return updated

    async def reject(self, lesson_id: str, *, actor: str | None = None) -> Lesson:
        """The D12 reject gate: mark the proposal rejected. Never touches Git."""
        lesson = await self._get_pending(lesson_id)
        assert lesson.id is not None
        updated = await self.store.lessons.update(lesson.id, {"status": LessonStatus.rejected})
        assert updated is not None
        return updated

    async def preview(
        self, lesson_id: str, *, rule_text: str | None = None
    ) -> tuple[Lesson, str, str, str, str]:
        """Git diff of the rule about to land in ``content-lessons.md``. Does not write.

        Returns ``(lesson, path, before, after, final_rule)``.
        """
        lesson = await self._get_pending(lesson_id)
        final_rule = (rule_text if rule_text is not None else lesson.generalizable_rule).strip()
        if not final_rule:
            raise ValueError("preview lesson rule text is empty")
        path, before, after = self.content.preview_accepted_lesson(lesson.voice, final_rule)
        return lesson, path, before, after, final_rule

    async def decide_batch(
        self,
        lesson_ids: list[str],
        *,
        action: Literal["accept", "reject"],
        rule_texts: dict[str, str] | None = None,
        actor: str | None = None,
    ) -> tuple[list[Lesson], list[tuple[str, str]]]:
        """Accept or reject several pending lessons. Per-item failures are collected, not raised.

        Partial success is intentional for batch review: one already-decided id must not block
        the rest of the selection. Returns ``(decided, errors)`` where each error is
        ``(lesson_id, message)``.
        """
        decided: list[Lesson] = []
        errors: list[tuple[str, str]] = []
        overrides = rule_texts or {}
        for lesson_id in lesson_ids:
            try:
                if action == "accept":
                    decided.append(
                        await self.accept(
                            lesson_id, rule_text=overrides.get(lesson_id), actor=actor
                        )
                    )
                else:
                    decided.append(await self.reject(lesson_id, actor=actor))
            except (KeyError, LessonNotPending, ValueError) as exc:
                errors.append((lesson_id, str(exc)))
        return decided, errors

    # --- internals --------------------------------------------------------------------------

    def _read_final_text(self, piece: Piece) -> str:
        """The machine's final draft: the latest committed Revision if the piece has one, else
        the current working-tree ``draft.html`` (§1.10 — a Revision is a Git commit)."""
        if piece.latest_revision:
            return self.content.read_revision(piece.slug, piece.latest_revision)
        return self.content.read_draft(piece.slug)

    async def _get_piece(self, piece_id: str) -> Piece:
        piece = await self.store.pieces.get(piece_id)
        if piece is None:
            raise KeyError(f"no piece {piece_id!r}")
        return piece

    async def _get_pending(self, lesson_id: str) -> Lesson:
        lesson = await self.store.lessons.get(lesson_id)
        if lesson is None:
            raise KeyError(f"no lesson {lesson_id!r}")
        if LessonStatus(lesson.status) != LessonStatus.proposed:
            raise LessonNotPending(
                f"lesson {lesson_id!r} is not pending (status={lesson.status})"
            )
        return lesson
