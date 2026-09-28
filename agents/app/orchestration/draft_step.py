"""Draft step (engine/2-draft.md; cmw-context-assembly report §6) — the highest-nuance step.

Turns a piece's interview transcript into a semantic ``draft.html`` revision. Plugs into the
batch-step seam (:mod:`app.orchestration.steps`) for ``JobType.draft``: on success it commits a
new Revision to Git (:class:`~app.git.GitContentStore`) and mirrors the open-GAP count onto the
Piece's Mongo work-state; the (unmodified) :class:`~app.orchestration.machine.PieceMachine` then
advances drafting → council. On failure it raises so the job runner / machine's flag-not-rollback
path takes over — this module never touches piece stage and never writes a half-finished
revision (D4/D16b).

Context assembly (cmw-context-assembly report §6), via the shared :class:`~app.llm.PromptAssembler`:

    T0 (stable): engine/2-draft.md + the active voice pack in override order (guide → style →
        lessons — lessons OVERRIDE the guide on conflict, §6d①) + the partner fact files for
        whatever partners the piece actually touches (§6d⑤ — optional, partner-driven).
    T1 (per-piece): a PURPOSE block (see below) + the FULL verbatim transcript (D16b — never
        summarized, §6d②) + sources.md when one already exists (citations + open clearances the
        drafter may use/mark).
    T2 (variable tail): target/format, plus up to a couple of on-brand finished pieces in the
        same voice as few-shot register anchors (§6d③). Also states the response-format contract
        (raw draft.html only, no other files, no markdown fence) — engine/2-draft.md's "Output"
        section describes a multi-file folder scaffold meant for an agentic session with real
        filesystem tools, so without this a single ``complete()`` call can (and, live-verified,
        does) reply with a chat-formatted multi-file dump instead of the bare HTML
        ``result.text`` is assumed to be.

**Purpose vs. evidence (cmw-draft-ignores-originating-narrative fix, 2026-08-10).** The
transcript is the piece's *evidence* — engine/2-draft.md is explicit that every claim must trace
back to it. But nothing previously carried the piece's *purpose*: the originating Spike
(``Piece.origin_spike_id`` — never read here before this fix) and the audience/angle intent it
carries forward (``Piece.intent``, formerly a two-line hint buried in the T2 tail, *after* the
full transcript and *before* whole example drafts appended after it — a demonstrably weak
position). A real piece was driven through the deployed system starting from a narrative about
insulating customers from data-centre risk across geographies/vendors; the draft came back about
an unrelated technical topic the interview transcript happened to cover, because the model
faithfully structured the transcript it was given with no signal of what that transcript was
*for*. :func:`DraftStep._purpose_block` fixes this by hydrating the Spike (+ its seeding
Narrative, if any) and the intent into a **new, separate T1 block placed first** — before the
transcript, in the same stable per-piece prefix, but never concatenated into the transcript text
itself (that would make the narrative compete with the transcript as source material, a
different error). The block carries its own explicit framing — the transcript that follows is
evidence gathered *in service of* this purpose, not the purpose itself; select/organize it
accordingly rather than transcribing it wholesale — because engine/2-draft.md itself says nothing
about this relationship and cannot be edited from this repo (it lives in
``HendoCode/masthead`` — see this fix's PR description for the recommended
brain-side addition). Best-effort like the example-piece/sources.md enrichment below: a piece
with no linked Spike, or a Spike with nothing to say, contributes no block rather than failing
the draft.

No caching (§6e): a draft is a single call per revision and the T0 prefix sits below the Opus
cache floor anyway, so this step always assembles with ``cache=False``.

The model tier is requested through the tiering seam (:func:`app.llm.model_for_step`), never
hardcoded here — D14 fixes DRAFT to Opus 4.8, but this step just asks for "whatever DRAFT's tier
is" so a re-tier never needs a code change on this side of the seam.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.git import open_brain, open_content_store
from app.llm import PipelineStep, PromptAssembler, model_for_step
from app.models import JobType, Piece, PieceStage, SpikeOriginKind
from app.orchestration.retry import PermanentStepError, RefusalError
from app.orchestration.steps import BatchStep, StepContext, StepResult

if TYPE_CHECKING:  # avoid a hard import cycle / optional Git deps at runtime (mirrors steps.py)
    from app.git import GitBrain, GitContentStore
    from app.repositories import WorkStateStore

# Other-piece stages worth mining for a register-anchor few-shot example (§6d③) — anything that
# has already been through drafting, so it reads like finished prose, not a bare transcript.
_EXAMPLE_STAGES = (PieceStage.finalized, PieceStage.review, PieceStage.council)

# An "open" GAP tag ("[GAP]" / "[GAP: need X]") — NOT "[GAP CLOSED]", which the loop already
# resolved. Mirrors the engine's own convention (engine/2-draft.md; the live token-vs-storage
# draft.html editorial block).
_OPEN_GAP_RE = re.compile(r"\[GAP(?!\s+CLOSED)\b")
# Any tag, not just <section> — nothing in the engine doc requires that specific element, only
# the "editorial" class is the load-bearing convention (engine/feedback-intake.md's external-share
# strip keys off the class too). Requiring <section> specifically was an overfit to the two
# existing example drafts that happened to use it.
_EDITORIAL_RE = re.compile(r'<[a-zA-Z][^>]*\bclass\s*=\s*"[^"]*\beditorial\b[^"]*"', re.IGNORECASE)


def _split_editorial(draft_html: str) -> tuple[str, str]:
    """Split a rendered draft into ``(body, editorial-block-onward)``.

    No editorial section found → the whole document is "body", so any GAP marker in it is
    correctly flagged as inline rather than silently uncounted.
    """
    match = _EDITORIAL_RE.search(draft_html)
    if match is None:
        return draft_html, ""
    return draft_html[: match.start()], draft_html[match.start() :]


def _require_transcript(assembler: PromptAssembler, piece: Piece, *, cannot: str) -> str:
    """Read the piece's interview transcript, or fail with a legible precondition error.

    Used ONLY by the draft step now: a draft genuinely cannot be written without source
    material, so a missing transcript remains a hard precondition there. The rewrite and
    council guards this once shared wording with (``cmw-incorporate-missing-transcript``, PR
    #82) no longer raise — a brain-authored piece (``brain_synced``, cmw-brain-pieces-visibility)
    legitimately has no transcript, so since cmw-lessons-loop Ship 1 they ground via
    :func:`_transcript_or_grounding` / ``PromptAssembler.grounding_block_without_transcript``
    instead. Keeping the explanation legible (never a raw ``FileNotFoundError`` leaking through)
    is the surviving requirement from that original fix.
    """
    try:
        return assembler.transcript_block(piece.slug)
    except OSError as exc:
        raise PermanentStepError(
            f"piece {piece.slug!r} has no interview transcript (drafts/{piece.slug}/"
            f"transcript.md is missing), so {cannot}. This piece appears to have skipped the "
            "interview stage. A human needs to give it a real transcript (for example by "
            "running a real interview) before this can succeed; retrying this job unchanged "
            "will fail the same way every time."
        ) from exc


def _transcript_or_grounding(assembler: PromptAssembler, piece: Piece) -> str:
    """The transcript block, or — for a brain-authored piece with no transcript — the shared
    invent-nothing grounding block (cmw-lessons-loop Ship 1).

    The council shared prefix uses this in place of ``_require_transcript``: unlike the draft
    step (which genuinely cannot run without source material), a council scoring pass always
    has the revision being scored to ground in, and a brain-authored piece (``brain_synced``)
    legitimately reaches ``council`` with no ``transcript.md``. The substitute block lives in
    ONE place — ``PromptAssembler.grounding_block_without_transcript`` — shared verbatim with
    the incorporate rewrite, so the two halves of a reviews-done round can never drift apart
    the way their duplicated raise-guards once shared only wording by convention.
    """
    try:
        return assembler.transcript_block(piece.slug)
    except OSError:
        return assembler.grounding_block_without_transcript(piece.slug)


def _count_open_gaps(draft_html: str) -> int:
    _body, editorial = _split_editorial(draft_html)
    return len(_OPEN_GAP_RE.findall(editorial))


def _assert_no_inline_gaps(draft_html: str) -> None:
    """GAPs live ONLY in the trailing editorial block, never inline in prose (domain model
    §1.11; engine/2-draft.md). A model that ignored the instruction fails the step rather than
    shipping a broken revision — the runner classifies this as deterministic (flag, don't retry).
    """
    body, _editorial = _split_editorial(draft_html)
    if _OPEN_GAP_RE.search(body):
        raise PermanentStepError(
            "draft contains a [GAP] marker inline in the body prose — GAPs must live only in "
            'a trailing block carrying class="editorial" (D-invariant, engine/2-draft.md)'
        )


class DraftStep(BatchStep):
    """The ``drafting`` batch step (§1.9). One Opus-tier call per revision; see the module
    docstring for the context-assembly recipe. ``brain``/``content`` default to the shared Git
    seams (:func:`app.git.open_brain` / :func:`app.git.open_content_store`) when neither an
    explicit override nor ``ctx.brain``/``ctx.content`` is supplied.
    """

    job_type = JobType.draft

    def __init__(
        self,
        *,
        brain: GitBrain | None = None,
        content: GitContentStore | None = None,
        max_tokens: int = 8192,
        effort: str | None = None,
        max_example_pieces: int = 2,
    ) -> None:
        self._brain = brain
        self._content = content
        self._max_tokens = max_tokens
        self._effort = effort
        self._max_example_pieces = max_example_pieces

    async def run(self, ctx: StepContext) -> StepResult:
        piece = ctx.piece
        if piece is None or piece.id is None:
            raise PermanentStepError(
                "draft step requires a persisted piece (draft is never pieceless)"
            )
        if ctx.provider is None:
            raise PermanentStepError("no LLM provider configured for the draft step")

        brain = self._brain or ctx.brain or open_brain()
        content = self._content or ctx.content or open_content_store()
        assembler = PromptAssembler(brain, content)

        t0 = [assembler.engine_block("2-draft"), *assembler.voice_pack_blocks(piece.voice)]
        t0.extend(self._partner_blocks(assembler, brain, piece))

        t1 = []
        purpose = await self._purpose_block(ctx.store, piece)
        if purpose:
            t1.append(purpose)
        t1.append(
            _require_transcript(
                assembler,
                piece,
                cannot=(
                    "a draft cannot be written — a draft is built directly from the interview "
                    "transcript, so there is no source material to draft from at all without it"
                ),
            )
        )
        try:
            t1.append(assembler.sources_block(piece.slug))
        except OSError:
            pass  # no sources.md yet for a fresh piece — the assembler drops missing files too

        examples = await self._example_drafts(ctx.store, content, piece)
        t2 = self._build_t2(piece, examples)

        prompt = assembler.assemble(t0=t0, t1=t1, t2=t2, cache=False)

        await ctx.beat()
        model = model_for_step(PipelineStep.DRAFT)  # D14 tiering seam — never hardcoded here
        result = await ctx.provider.complete(
            step=PipelineStep.DRAFT,
            model=model,
            system=prompt.system,
            messages=prompt.messages,
            max_tokens=self._max_tokens,
            effort=self._effort,
            cache=prompt.cache,
            budget=ctx.budget,
        )

        if result.stop_reason == "refusal":
            raise RefusalError("draft model refused to produce a draft")
        draft_html = result.text.strip()
        if not draft_html:
            raise PermanentStepError("draft model returned no content")
        _assert_no_inline_gaps(draft_html)
        open_gaps = _count_open_gaps(draft_html)

        sha = content.commit_revision(
            piece.slug, draft_html, message=f"draft: {piece.slug} (job {ctx.job.id})"
        )
        await ctx.store.pieces.update(piece.id, {"latest_revision": sha, "open_gaps": open_gaps})

        return StepResult(
            usage=result.usage,
            notes=[f"draft.html committed {sha[:8]} for {piece.slug} ({open_gaps} open GAP(s))"],
        )

    # --- context assembly helpers -----------------------------------------------------------

    @staticmethod
    async def _purpose_block(store: WorkStateStore, piece: Piece) -> str | None:
        """The piece's PURPOSE — why it exists, what it is meant to be about — as distinct from
        its EVIDENCE (the transcript block placed right after this one). Hydrates the originating
        Spike (``Piece.origin_spike_id``) + the Narrative that seeded it, if any, plus the
        audience/angle intent carried onto the piece (formerly a weak T2-tail hint — see the
        module docstring). Best-effort, like ``_example_drafts``/``sources_block``: a piece with
        no linked Spike, an unresolvable Spike/Narrative id, or nothing to say, contributes no
        block rather than failing the draft — this is enrichment, never a hard requirement.
        """
        lines: list[str] = []
        if piece.intent is not None:
            if piece.intent.audience:
                lines.append(f"Intended audience: {piece.intent.audience}")
            if piece.intent.angle:
                lines.append(f"Intended angle: {piece.intent.angle}")

        spike = await store.spikes.get(piece.origin_spike_id) if piece.origin_spike_id else None
        if spike is not None:
            lines.append(f"Originating idea: {spike.headline}")
            if spike.origin.kind == SpikeOriginKind.narrative and spike.origin.ref:
                narrative = await store.narratives.get(spike.origin.ref)
                if narrative is not None and narrative.seed_text:
                    lines.append(f"In the author's own words (the originating narrative): {narrative.seed_text}")
            if spike.rank_rationale:
                lines.append(f"Why this idea was picked: {spike.rank_rationale}")
            if spike.convergence_note:
                lines.append(f"Convergence note: {spike.convergence_note}")

        if not lines:
            return None
        return (
            "## This piece's purpose\n\n"
            "This is what the piece is FOR: its intended subject, audience, and angle. The "
            "transcript that follows is evidentiary material gathered in service of this "
            "purpose — it is not itself the purpose. Select, organize, and weight transcript "
            "content by how well it serves the purpose stated here; a transcript passage that "
            "does not serve it need not appear in the draft even if it took up a large share of "
            "the interview, and a passage that does serve it should be foregrounded even if it "
            "was a small part of the interview. Do not let transcript coverage override "
            "relevance to this purpose.\n\n" + "\n".join(lines)
        )

    @staticmethod
    def _partner_blocks(
        assembler: PromptAssembler, brain: GitBrain, piece: Piece
    ) -> list[str]:
        """The partners the piece explicitly touches (§6d⑤) — partner fact files (naming/CTA)
        hydrate only when a partner is actually configured, so this is optional by design."""
        available = set(brain.list_partners())
        slugs = [p.strip().lower() for p in piece.partners]
        seen: set[str] = set()
        blocks: list[str] = []
        for slug in slugs:
            if slug in seen or slug not in available:
                continue
            seen.add(slug)
            blocks.append(assembler.partner_block(slug))
        return blocks

    async def _example_drafts(
        self, store: WorkStateStore, content: GitContentStore, piece: Piece
    ) -> list[tuple[str, str]]:
        """Up to :attr:`_max_example_pieces` other same-voice, already-drafted pieces, as
        few-shot register anchors (§6d③). Best-effort: a missing/unreadable draft just drops
        that candidate rather than failing the whole draft."""
        if self._max_example_pieces <= 0:
            return []
        seen: set[str] = {piece.id} if piece.id else set()
        examples: list[tuple[str, str]] = []
        for stage in _EXAMPLE_STAGES:
            for candidate in await store.pieces.by_stage(stage):
                if candidate.id is None or candidate.id in seen or candidate.voice != piece.voice:
                    continue
                seen.add(candidate.id)
                try:
                    html = content.read_draft(candidate.slug)
                except OSError:
                    continue
                examples.append((candidate.slug, html))
                if len(examples) >= self._max_example_pieces:
                    return examples
        return examples

    @staticmethod
    def _build_t2(piece: Piece, examples: list[tuple[str, str]]) -> str:
        lines = [
            "Draft this piece now, following the instructions and voice pack assembled above.",
            "Your entire response must be nothing but the contents of draft.html: a single, "
            "self-contained HTML document. Do not scaffold or emit any other file (piece.md, "
            "sources.md, transcript.md, assets/) — those are handled outside this call. Do not "
            "wrap the document in a markdown code fence, and do not add any commentary, preamble, "
            "or narration before or after it — the raw text of your response is committed "
            "verbatim as draft.html.",
        ]
        if piece.target:
            lines.append(f"Target format: {piece.target}")
        # Audience/angle intent now lives in the T1 purpose block (see _purpose_block) — this
        # tail is delivery-format mechanics only, not the piece's subject-matter purpose.
        tail = "\n".join(lines)
        for slug, html in examples:
            tail += (
                f"\n\n--- Example of an on-brand finished piece ({slug}) — register/format "
                f"reference only; its facts are NOT this piece's source ---\n{html}"
            )
        return tail
