"""Council step (engine/3-revision-loop.md; cmw-context-assembly report §7) — bounded autonomy.

Scores the current revision, then autonomously revises up to a configured ceiling, stopping
when any of the following is true:

* the aggregate clears the configured ``quality_bar``;
* an information gap or clearance is identified and the policy says it requires a human;
* the iteration ceiling is reached;
* the per-run cost ceiling is reached (caught and surfaced as a stop reason, not a crash).

Each scoring iteration records its own :class:`~app.models.Council` record under the same
``round_number`` with an incrementing ``iteration``. The final iteration carries
``stop_reason``/``stop_message`` explaining why the loop stopped. A successful stop still
commits the best revision produced and advances council → review through the unchanged
:class:`~app.orchestration.machine.PieceMachine`.

Plugs into the batch-step seam (:mod:`app.orchestration.steps`) for ``JobType.council``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings
    from app.content_workflow.store import WorkflowState
    from app.git import GitBrain, GitContentStore

from app.git import open_brain, open_content_store
from app.llm import (
    FanoutCall,
    Message,
    PipelineStep,
    PromptAssembler,
    RunBudgetExceeded,
    Usage,
    council_fanout,
    model_for_step,
)
from app.llm.budget import RunBudget
from app.derivatives.quality import derivative_council_editors
from app.models import QUALITY_BAR, Council, EditorScore, Job, JobType, Piece, PieceRole
from app.orchestration.draft_step import (
    DraftStep,
    _assert_no_inline_gaps,
    _count_open_gaps,
    _transcript_or_grounding,
)
from app.orchestration.retry import PermanentStepError, RefusalError
from app.orchestration.steps import BatchStep, StepContext, StepResult

if TYPE_CHECKING:  # avoid a hard import cycle / optional Git deps at runtime (mirrors steps.py)
    from app.git import GitBrain, GitContentStore

# slop-allergist / technical-reviewer can cap the AGGREGATE regardless of other editors' merit — a
# single unflagged slop tell (or an uncorrected technical error) caps at 6 (engine/3-revision-loop.md
# ":29-31"). Any OTHER editor's ``hard_cap_applied`` claim is recorded on its own EditorScore for
# audit but never applied to the aggregate — only these two personas carry that authority.
HARD_CAP_EDITORS: frozenset[str] = frozenset({"slop-allergist", "technical-reviewer"})
HARD_CAP_CEILING = 6.0

# Canonical iteration order for the mandatory editors (must stay in sync with MANDATORY_EDITORS).
_MANDATORY_ORDER: tuple[str, ...] = ("slop-allergist", "voice-guardian")

_JSON_CONTRACT = (
    "Score the draft in the shared context above per your judgment criteria. Respond with ONLY a "
    "JSON object (no prose, no markdown fence) matching exactly:\n"
    '{"score": <number 0-10>, "hard_cap_applied": <true|false>, "editorial_fixes": ["...", ...], '
    '"information_gaps": ["...", ...], "clearances": ["...", ...]}\n'
    "- score: your N/10 for this draft.\n"
    "- hard_cap_applied: true ONLY if you are slop-allergist or technical-reviewer AND you found a "
    "hard-fail that caps scoring regardless of merit (engine/3-revision-loop.md); false otherwise.\n"
    "- editorial_fixes: specific, actionable textual fixes the machine can apply directly to the "
    "HTML in place.\n"
    "- information_gaps: facts only the author can supply — never invented — that route back to a "
    "targeted interview.\n"
    "- clearances: claims, permissions, or legal/policy checks that require explicit human "
    "approval before publication.\n"
    "Use empty arrays when you have none of a kind."
)

_APPLY_INSTRUCTIONS_TEMPLATE = (
    "Apply the following council-approved changes to the draft.html revision in the shared context "
    "above. Edit the HTML in place — do not rebuild or rephrase anything the council did not flag, "
    "and do not change the article's meaning beyond what a fix asks for.\n\n"
    "{fixes_block}"
    "{gaps_block}"
    "{clearances_block}"
    "Rules:\n"
    "- Apply each editorial fix directly in the body prose where it belongs.\n"
    "- For each information gap, add ONE new line inside the existing trailing "
    '<section class="editorial"> block (never inline in the body) in this exact form: '
    '<p><span class="tag">[GAP: <short description>]</span> <one-sentence explanation></p>. '
    "Do not duplicate a gap already present in that block, and do not alter or remove any existing "
    "[GAP]/[GAP CLOSED]/[NOTE] entry.\n"
    "- For each clearance, add ONE new line inside the existing trailing <section class=\"editorial\"> "
    'block in this exact form: <p><span class="tag">[CLEARANCE: <short description>]</span> '
    "<one-sentence explanation></p>.\n"
    "- If the editorial block is missing entirely, do not invent one unless there is at least one "
    "gap or clearance to record — then add a minimal "
    '<section class="editorial" aria-label="Editorial annotations, not for publication"> at the '
    "very end of the document containing just the new line(s).\n"
    "Respond with ONLY the complete, revised HTML document — no prose, no markdown fence."
)


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")
    return bool(value)


def _dedup(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in items:
        item = raw.strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


class CouncilParseError(PermanentStepError):
    """An editor's (or the apply call's) response could not be parsed — deterministic, not retried."""

    code = "council_parse_error"


def _parse_editor_response(editor: str, text: str) -> EditorScore:
    """Parse one editor's JSON scoring response (§_JSON_CONTRACT) into an :class:`EditorScore`."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise CouncilParseError(f"{editor}: model did not return a JSON object: {text!r}")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise CouncilParseError(f"{editor}: invalid JSON from council call: {exc}") from exc
    if not isinstance(data, dict):
        raise CouncilParseError(f"{editor}: expected a JSON object, got {type(data).__name__}")

    try:
        score = float(data.get("score", 0))
    except (TypeError, ValueError) as exc:
        raise CouncilParseError(f"{editor}: non-numeric score {data.get('score')!r}") from exc
    score = max(0.0, min(10.0, score))

    fixes = [str(x).strip() for x in data.get("editorial_fixes", []) or [] if str(x).strip()]
    gaps = [str(x).strip() for x in data.get("information_gaps", []) or [] if str(x).strip()]
    clearances = [str(x).strip() for x in data.get("clearances", []) or [] if str(x).strip()]
    return EditorScore(
        editor=editor,
        score=score,
        editorial_fixes=fixes,
        information_gaps=gaps,
        clearances=clearances,
        hard_cap_applied=_as_bool(data.get("hard_cap_applied", False)),
    )


def compute_aggregate(scores: list[EditorScore]) -> float:
    """The council's aggregate: the mean score, capped at :data:`HARD_CAP_CEILING` if a hard-cap-
    eligible editor (:data:`HARD_CAP_EDITORS`) flagged ``hard_cap_applied``."""
    if not scores:
        return 0.0
    mean = sum(s.score for s in scores) / len(scores)
    capped = any(s.hard_cap_applied for s in scores if s.editor in HARD_CAP_EDITORS)
    return round(min(mean, HARD_CAP_CEILING) if capped else mean, 4)


def _external_partners(piece: Piece) -> list[str]:
    """``piece.partners`` normalized and deduped. There is no hardcoded home company — the
    partner-brand-steward runs only for partners a piece actually names, so with none configured
    the council runs the quality editors alone."""
    return _dedup([p.strip().lower() for p in piece.partners])


def _select_editors(piece: Piece, job: Job, brain: GitBrain) -> list[str]:
    """Mandatory editors + partner-brand-steward per external partner +, for a derivative piece,
    its destination-specific council (derivative quality bar: mandatory editors + universal
    facts/safety hard-gate editors + destination judgment) + the round's fit editors.
    Unknown names are dropped, not rejected (same discipline as fit editors)."""
    selected: list[str] = list(_MANDATORY_ORDER)
    selected.extend(f"partner-brand-steward/{partner}" for partner in _external_partners(piece))

    if piece.role == PieceRole.derivative:
        # A derivative clears ITS OWN council with destination-specific judgment (never the
        # anchor's lineup/score). Validate against the brain roster like fit editors.
        available = set(brain.list_personas("editor"))
        for name in derivative_council_editors(piece.target or ""):
            if name not in selected and name in available:
                selected.append(name)

    available = set(brain.list_personas("editor"))
    seen = set(selected)
    for raw in job.council_fit_editors or []:
        name = raw.strip().lower()
        if name and name not in seen and name in available:
            seen.add(name)
            selected.append(name)
    return selected


def _editor_rubric(brain: GitBrain, editor_name: str) -> str:
    """This editor's persona rubric body."""
    if "/" in editor_name:
        base, partner = editor_name.split("/", 1)
        body = brain.read_persona("editor", base).body
        return (
            f"{body}\n\nYou are scoring PARTNER content for **{partner}** specifically — read "
            f"partners/{partner}.md in the shared context above for the facts you check against. "
            "Do not comment on any other partner."
        )
    return brain.read_persona("editor", editor_name).body


def _editor_messages(
    brain: GitBrain, editor_name: str, prior: EditorScore | None
) -> list[Message]:
    parts = [
        f"You are the **{editor_name}** council member for this round.",
        _editor_rubric(brain, editor_name),
    ]
    if prior is not None:
        if prior.editorial_fixes:
            parts.append(
                "Previously flagged editorial fixes — check whether each landed; do not re-flag "
                "one that is already applied:\n- " + "\n- ".join(prior.editorial_fixes)
            )
        if prior.information_gaps:
            parts.append(
                "Previously flagged information gaps — do not re-flag one already answered in the "
                "transcript above:\n- " + "\n- ".join(prior.information_gaps)
            )
        if prior.clearances:
            parts.append(
                "Previously flagged clearances — do not re-flag one already resolved:\n- "
                + "\n- ".join(prior.clearances)
            )
    parts.append(_JSON_CONTRACT)
    return [{"role": "user", "content": "\n\n".join(parts)}]


def _apply_instructions(fixes: list[str], gaps: list[str], clearances: list[str]) -> str:
    fixes_block = "Editorial fixes to apply:\n- " + "\n- ".join(fixes) + "\n\n" if fixes else ""
    gaps_block = (
        "New information gaps to record in the editorial block:\n- " + "\n- ".join(gaps) + "\n\n"
        if gaps
        else ""
    )
    clearances_block = (
        "New clearances to record in the editorial block:\n- "
        + "\n- ".join(clearances)
        + "\n\n"
        if clearances
        else ""
    )
    return _APPLY_INSTRUCTIONS_TEMPLATE.format(
        fixes_block=fixes_block, gaps_block=gaps_block, clearances_block=clearances_block
    )


def _render_summary(council: Council) -> str:
    """Human-readable mirror committed to ``sources.md``."""
    lines = [f"## Council record — round {council.round_number} · iteration {council.iteration}"]
    lines.append(" · ".join(f"{s.editor} {s.score:g}" for s in council.editor_scores))
    agg = council.aggregate if council.aggregate is not None else 0.0
    verdict = "clears the bar" if council.meets_bar() else "below the bar"
    lines.append(f"Aggregate: {agg:.1f}/10 ({verdict}, ≥ {QUALITY_BAR:g}).")
    capped_by = [
        s.editor for s in council.editor_scores if s.hard_cap_applied and s.editor in HARD_CAP_EDITORS
    ]
    if capped_by:
        lines.append(f"Hard cap applied by: {', '.join(capped_by)} (capped at {HARD_CAP_CEILING:g}).")
    if council.stop_reason:
        lines.append(f"Stop reason: {council.stop_reason} — {council.stop_message or '(no detail)'}")
    return "\n".join(lines) + "\n"


def _append_section(existing: str, section: str) -> str:
    if not existing.strip():
        return section
    return existing.rstrip("\n") + "\n\n" + section


class CouncilStep(BatchStep):
    """The ``council`` batch step (§1.9). Bounded autonomous revision loop over Opus-tier editor
    scoring + machine-safe fixes, stopping for human obligations or configured ceilings.

    ``brain``/``content`` default to the shared Git seams when neither an explicit override nor
    ``ctx.brain``/``ctx.content`` is supplied (mirrors :class:`DraftStep`). ``settings`` and
    ``workflow_state`` are optional; when absent, a legacy piece uses the settings default policy
    and cannot create :class:`~app.content_workflow.models.HumanObligation` records.
    """

    job_type = JobType.council

    def __init__(
        self,
        *,
        brain: GitBrain | None = None,
        content: GitContentStore | None = None,
        editor_max_tokens: int = 2048,
        apply_max_tokens: int = 8192,
        effort: str | None = None,
        settings: "Settings | None" = None,
        workflow_state: "WorkflowState | None" = None,
    ) -> None:
        self._brain = brain
        self._content = content
        self._editor_max_tokens = editor_max_tokens
        self._apply_max_tokens = apply_max_tokens
        self._effort = effort
        self._settings = settings
        self._workflow_state = workflow_state

    async def _effective_policy(self, piece: Piece) -> "CouncilPolicy":
        """Resolve the council policy for this piece: project policy when available, else
        settings, with any active quality-waiver overrides layered on top."""
        from app.config import get_settings
        from app.content_workflow.models import CouncilPolicy

        if piece.content_project_id and self._workflow_state is not None:
            project = await self._workflow_state.load_project(piece.content_project_id)
            if project is not None:
                policy = project.council_policy
                waiver = await self._workflow_state.latest_quality_waiver(
                    piece.content_project_id
                )
                if waiver is not None:
                    overrides: dict[str, object] = {}
                    if waiver.quality_bar is not None:
                        overrides["quality_bar"] = waiver.quality_bar
                    if waiver.iteration_ceiling is not None:
                        overrides["iteration_ceiling"] = waiver.iteration_ceiling
                    if waiver.cost_ceiling_usd is not None:
                        overrides["cost_ceiling_usd"] = waiver.cost_ceiling_usd
                    if overrides:
                        policy = policy.model_copy(update=overrides)
                return policy
        settings = self._settings or get_settings()
        return settings.default_council_policy()

    def _apply_cost_ceiling(self, budget: RunBudget, policy: "CouncilPolicy") -> None:
        """Tighten the shared per-run budget to the policy's cost ceiling, if one is set."""
        if policy.cost_ceiling_usd is not None and policy.cost_ceiling_usd > 0:
            current = budget.max_cost_usd
            if current is None or current > policy.cost_ceiling_usd:
                budget.max_cost_usd = policy.cost_ceiling_usd

    async def _create_human_obligations(
        self,
        piece: Piece,
        gaps: list[str],
        clearances: list[str],
    ) -> None:
        """For content-project pieces, create ``resolve_gap`` / ``grant_clearance`` obligations."""
        if not piece.content_project_id or self._workflow_state is None:
            return
        from app.content_workflow.models import (
            ActorRef,
            AuthorityKind,
            HumanObligation,
            HumanObligationKind,
            ObligationSubject,
        )

        project = await self._workflow_state.load_project(piece.content_project_id)
        if project is None:
            return

        authority_by_kind = {a.kind: a.assignee for a in project.authorities}

        def assignee_for(kind: AuthorityKind) -> ActorRef:
            return authority_by_kind.get(kind) or authority_by_kind.get(AuthorityKind.direction) or ActorRef(subject_id="operator", email="operator@example.com")

        subject = ObligationSubject(kind="piece", id=piece.id or "")
        for gap in gaps:
            await self._workflow_state.create_obligation(
                HumanObligation(
                    content_project_id=project.id,
                    kind=HumanObligationKind.resolve_gap,
                    assignee=assignee_for(AuthorityKind.input_sufficiency),
                    authority=AuthorityKind.input_sufficiency,
                    subject=subject,
                )
            )
        for clearance in clearances:
            await self._workflow_state.create_obligation(
                HumanObligation(
                    content_project_id=project.id,
                    kind=HumanObligationKind.grant_clearance,
                    assignee=assignee_for(AuthorityKind.clearance),
                    authority=AuthorityKind.clearance,
                    subject=subject,
                )
            )

    async def _score_revision(
        self,
        ctx: StepContext,
        piece: Piece,
        brain: GitBrain,
        content: GitContentStore,
        assembler: PromptAssembler,
        *,
        revision: str,
        html: str,
        round_number: int,
        iteration: int,
        prior_by_editor: dict[str, EditorScore],
    ) -> tuple[Council, Usage, float]:
        """Run one fan-out scoring pass against ``html`` and return a Council record."""
        t0 = [
            assembler.engine_block("3-revision-loop"),
            *assembler.voice_pack_blocks(piece.voice),
            *DraftStep._partner_blocks(assembler, brain, piece),
        ]
        t1 = []
        purpose = await DraftStep._purpose_block(ctx.store, piece)
        if purpose:
            t1.append(purpose)
        t1.append(html)
        # Transcript-optional since cmw-lessons-loop Ship 1: a brain-authored (brain_synced)
        # piece has no transcript by design, so this grounds in the revision being scored (already
        # in T1 above) + sources.md with an explicit invent-nothing block instead of failing.
        t1.append(_transcript_or_grounding(assembler, piece))
        assembled = assembler.assemble(
            t0=t0, t1=t1, t2="(shared context only — see each editor's own instructions)", cache=True
        )

        await ctx.beat()
        model = model_for_step(PipelineStep.COUNCIL)
        editor_names = _select_editors(piece, ctx.job, brain)

        fanout_calls = [
            FanoutCall(label=name, messages=_editor_messages(brain, name, prior_by_editor.get(name)))
            for name in editor_names
        ]
        fanout_results = await council_fanout(
            ctx.provider,
            system=assembled.system,
            editors=fanout_calls,
            max_tokens=self._editor_max_tokens,
            model=model,
            effort=self._effort,
            cache=assembled.cache,
            budget=ctx.budget,
        )

        editor_scores = [_parse_editor_response(r.label, r.result.text) for r in fanout_results]
        total_usage = Usage()
        total_cost = 0.0
        for r in fanout_results:
            total_usage = total_usage + r.result.usage
            total_cost += r.result.cost_usd

        aggregate = compute_aggregate(editor_scores)
        council = Council(
            piece_id=piece.id or "",
            revision=revision,
            round_number=round_number,
            iteration=iteration,
            editor_scores=editor_scores,
            aggregate=aggregate,
            cost=round(total_cost, 6),
        )
        council = await ctx.store.councils.insert(council)
        assert council.id is not None
        return council, total_usage, total_cost

    async def _apply_revision_changes(
        self,
        ctx: StepContext,
        system: list[str],
        cache: str | None,
        html: str,
        fixes: list[str],
        gaps: list[str],
        clearances: list[str],
        model: str,
    ) -> tuple[str, Usage, float]:
        """Apply machine-safe fixes/gaps/clearances and return the revised HTML."""
        await ctx.beat()
        apply_result = await ctx.provider.complete(
            step=PipelineStep.COUNCIL,
            model=model,
            system=system,
            messages=[{"role": "user", "content": _apply_instructions(fixes, gaps, clearances)}],
            max_tokens=self._apply_max_tokens,
            effort=self._effort,
            cache=cache,
            budget=ctx.budget,
        )
        if apply_result.stop_reason == "refusal":
            raise RefusalError("council apply-fixes call refused to produce a revision")
        final_html = apply_result.text.strip()
        if not final_html:
            raise PermanentStepError("council apply-fixes call returned no content")
        _assert_no_inline_gaps(final_html)
        return final_html, apply_result.usage, apply_result.cost_usd

    async def run(self, ctx: StepContext) -> StepResult:
        piece = ctx.piece
        if piece is None or piece.id is None:
            raise PermanentStepError(
                "council step requires a persisted piece (council is never pieceless)"
            )
        if ctx.provider is None:
            raise PermanentStepError("no LLM provider configured for the council step")
        if not piece.latest_revision:
            raise PermanentStepError("council step requires a committed revision to score")

        brain = self._brain or ctx.brain or open_brain()
        content = self._content or ctx.content or open_content_store()
        assembler = PromptAssembler(brain, content)

        policy = await self._effective_policy(piece)
        self._apply_cost_ceiling(ctx.budget, policy)

        latest_council = await ctx.store.councils.latest_for_piece(piece.id)
        round_number = (latest_council.round_number + 1) if latest_council else 1
        base_prior_by_editor = {
            s.editor: s for s in (latest_council.editor_scores if latest_council else [])
        }

        current_revision = piece.latest_revision
        current_html = content.read_revision(piece.slug, current_revision)
        model = model_for_step(PipelineStep.COUNCIL)

        iteration = 1
        total_usage = Usage()
        total_cost = 0.0
        final_council: Council | None = None
        final_html = current_html
        final_revision = current_revision
        stop_reason: str | None = None
        stop_message: str | None = None
        cumulative_gaps: list[str] = []
        cumulative_clearances: list[str] = []

        while iteration <= policy.iteration_ceiling:
            prior_by_editor = (
                base_prior_by_editor if iteration == 1 else {s.editor: s for s in final_council.editor_scores}
            ) if final_council else base_prior_by_editor

            try:
                council, score_usage, score_cost = await self._score_revision(
                    ctx,
                    piece,
                    brain,
                    content,
                    assembler,
                    revision=current_revision,
                    html=current_html,
                    round_number=round_number,
                    iteration=iteration,
                    prior_by_editor=prior_by_editor,
                )
            except RunBudgetExceeded as exc:
                stop_reason = "cost_ceiling"
                stop_message = str(exc)
                break

            total_usage = total_usage + score_usage
            total_cost += score_cost
            final_council = council
            final_html = current_html
            final_revision = current_revision

            if council.meets_bar():
                stop_reason = "quality_bar_met"
                stop_message = (
                    f"Aggregate {council.aggregate:.1f} meets the {policy.quality_bar:.1f} "
                    "quality bar."
                )
                break

            fixes = _dedup([fix for s in council.editor_scores for fix in s.editorial_fixes])
            gaps = _dedup([gap for s in council.editor_scores for gap in s.information_gaps])
            clearances = _dedup([c for s in council.editor_scores for c in s.clearances])
            cumulative_gaps.extend(g for g in gaps if g not in cumulative_gaps)
            cumulative_clearances.extend(c for c in clearances if c not in cumulative_clearances)

            if gaps and policy.gaps_require_human:
                stop_reason = "human_obligation_required"
                stop_message = f"{len(gaps)} information gap(s) require human input before revising further."
                break

            if clearances and policy.clearances_require_human:
                stop_reason = "human_obligation_required"
                stop_message = f"{len(clearances)} clearance(s) require human approval before revising further."
                break

            if not fixes and not gaps and not clearances:
                stop_reason = "no_improvement_possible"
                stop_message = (
                    "No fixes or gaps were identified; cannot reach the quality bar autonomously."
                )
                break

            # Machine-safe changes: apply fixes and any gaps/clearances that do NOT require human.
            apply_gaps = [] if policy.gaps_require_human else gaps
            apply_clearances = [] if policy.clearances_require_human else clearances

            try:
                t0 = [
                    assembler.engine_block("3-revision-loop"),
                    *assembler.voice_pack_blocks(piece.voice),
                    *DraftStep._partner_blocks(assembler, brain, piece),
                ]
                t1 = []
                purpose = await DraftStep._purpose_block(ctx.store, piece)
                if purpose:
                    t1.append(purpose)
                t1.append(current_html)
                t1.append(_transcript_or_grounding(assembler, piece))
                assembled = assembler.assemble(
                    t0=t0, t1=t1, t2="(shared context only — see each editor's own instructions)", cache=True
                )
                applied_html, apply_usage, apply_cost = await self._apply_revision_changes(
                    ctx,
                    assembled.system,
                    assembled.cache,
                    current_html,
                    fixes,
                    apply_gaps,
                    apply_clearances,
                    model,
                )
            except RunBudgetExceeded as exc:
                stop_reason = "cost_ceiling"
                stop_message = str(exc)
                break
            except (RefusalError, PermanentStepError):
                # A refusal or malformed apply output is a genuine failure: roll back this
                # iteration's Council record so the step leaves nothing committed, then let the
                # job runner flag the piece in the usual way.
                await ctx.store.councils.delete(council.id)
                raise

            total_usage = total_usage + apply_usage
            total_cost += apply_cost
            current_html = applied_html

            # Commit the revised draft so the next iteration (or the final state) has a ref.
            existing_sources = _read_sources_or_empty(content, piece.slug)
            updated_sources = _append_section(existing_sources, _render_summary(council))
            current_revision = content.commit_revision(
                piece.slug,
                current_html,
                sources_md=updated_sources,
                message=f"council: {piece.slug} round {round_number} iteration {iteration} (job {ctx.job.id})",
            )

            if iteration == policy.iteration_ceiling:
                stop_reason = "iteration_ceiling"
                stop_message = f"Reached the iteration ceiling of {policy.iteration_ceiling}."
                final_html = current_html
                final_revision = current_revision
                break

            iteration += 1

        if final_council is None:
            raise PermanentStepError("council loop produced no council record")

        if stop_reason is None:
            # Should not happen when iteration_ceiling >= 1, but guard anyway.
            stop_reason = "iteration_ceiling"
            stop_message = f"Reached the iteration ceiling of {policy.iteration_ceiling}."

        # Persist stop reason on the final council record.
        await ctx.store.councils.update(
            final_council.id,
            {"stop_reason": stop_reason, "stop_message": stop_message},
        )
        final_council.stop_reason = stop_reason
        final_council.stop_message = stop_message

        # Create human obligations for content-project pieces when stopped for them.
        if stop_reason == "human_obligation_required":
            await self._create_human_obligations(piece, cumulative_gaps, cumulative_clearances)

        # Final commit of sources.md and piece state.
        open_gaps = _count_open_gaps(final_html)
        # Count clearances from the final HTML for open_clearances mirror.
        open_clearances = final_html.lower().count("[clearance:")
        existing_sources = _read_sources_or_empty(content, piece.slug)
        updated_sources = _append_section(existing_sources, _render_summary(final_council))
        sha = content.commit_revision(
            piece.slug,
            final_html,
            sources_md=updated_sources,
            message=f"council: {piece.slug} round {round_number} (job {ctx.job.id})",
        )
        await ctx.store.pieces.update(
            piece.id,
            {
                "latest_revision": sha,
                "latest_council_id": final_council.id,
                "open_gaps": open_gaps,
                "open_clearances": open_clearances,
            },
        )

        note = (
            f"council round {round_number} scored {piece.slug}: "
            f"aggregate {final_council.aggregate:g}/10 after {iteration} iteration(s); "
            f"stopped: {stop_reason}"
        )
        return StepResult(usage=total_usage, notes=[note])


def _read_sources_or_empty(content: GitContentStore, slug: str) -> str:
    try:
        return content.read_sources(slug)
    except OSError:
        return ""
