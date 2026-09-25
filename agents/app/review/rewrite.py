"""APPLY: fold classified editorial-fix items into the revision (context report §8b; D14).

"Fold editorial fixes into draft.html and re-run the relevant editors" — the rewrite half of
incorporate-edits. Opus 4.8 (✓ D14 "incorporate-edits is a batch Opus step";
:data:`~app.llm.tiering.PipelineStep.REWRITE`), assembled per §8b:

    T0 (stable):  engine/feedback-intake.md apply-rules + engine/2-draft.md's invent-nothing
                  discipline + the full active voice pack.
    T1 (per-piece): the CURRENT revision (edited in place, not rebuilt — "edit the HTML, don't
                  rebuild it", 3-revision-loop.md) + the sacred transcript (still the source for
                  anything new the rewrite adds) + sources.md when present. For a brain-authored
                  piece with no transcript (``brain_synced``, cmw-brain-pieces-visibility — a
                  legitimate review-stage state since that fix, not an impossible one): the shared
                  invent-nothing grounding block (``PromptAssembler.
                  grounding_block_without_transcript``, cmw-lessons-loop Ship 1) substitutes for
                  the transcript, and the revision read falls back piece.md-content-first the
                  same way mint does — never a permanent failure.
    T2 (variable): only the classified editorial-fix items — info-gaps/clearances/out-of-scope
                  never reach this call (they route elsewhere, §8b).

No caching (§8b-b: "single call per round → little benefit; skip").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.git.brain import GitBrain
from app.git.content import GitContentStore
from app.llm.assembler import PromptAssembler
from app.llm.budget import RunBudget
from app.llm.pricing import Usage
from app.llm.provider import LLMProvider
from app.llm.tiering import PipelineStep, model_for_step
from app.models import Piece
from app.orchestration.retry import PermanentStepError, RefusalError

DEFAULT_MAX_TOKENS = 8192

# Same convention as the draft step (engine/2-draft.md): GAPs live only in the trailing editorial
# block, never inline in prose. Duplicated locally (not imported from app.orchestration.draft_step)
# to keep this module's only dependency on that sibling package the shared retry error types.
_OPEN_GAP_RE = re.compile(r"\[GAP(?!\s+CLOSED)\b")
_EDITORIAL_RE = re.compile(r'<section[^>]*\bclass\s*=\s*"[^"]*\beditorial\b[^"]*"', re.IGNORECASE)


def _split_editorial(draft_html: str) -> tuple[str, str]:
    match = _EDITORIAL_RE.search(draft_html)
    if match is None:
        return draft_html, ""
    return draft_html[: match.start()], draft_html[match.start() :]


def count_open_gaps(draft_html: str) -> int:
    _body, editorial = _split_editorial(draft_html)
    return len(_OPEN_GAP_RE.findall(editorial))


def _assert_no_inline_gaps(draft_html: str) -> None:
    body, _editorial = _split_editorial(draft_html)
    if _OPEN_GAP_RE.search(body):
        raise PermanentStepError(
            "incorporate rewrite left a [GAP] marker inline in the body prose — GAPs must live "
            'only in the trailing <section class="editorial"> block (engine/2-draft.md)'
        )


@dataclass(frozen=True)
class RewriteResult:
    draft_html: str
    usage: Usage = field(default_factory=Usage)


def _build_t2(fixes: list[str], *, round_number: int) -> str:
    lines = [
        (
            f"Review round {round_number} incorporate-edits. Apply ONLY the following editorial "
            "fixes below to the current revision above. Edit the HTML in place — do not rebuild "
            "or re-draft sections that aren't touched by a fix. Invent nothing: every new "
            "sentence must still trace to the transcript or a cited figure. Return the COMPLETE "
            "updated draft.html (including its trailing editorial block), nothing else — no "
            "prose, no code fence."
        ),
        "",
        "Editorial fixes to apply:",
    ]
    lines.extend(f"{i}. {fix}" for i, fix in enumerate(fixes, start=1))
    return "\n".join(lines)


async def rewrite_revision(
    provider: LLMProvider,
    *,
    brain: GitBrain,
    content: GitContentStore,
    piece: Piece,
    fixes: list[str],
    round_number: int,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    effort: str | None = None,
    budget: RunBudget | None = None,
) -> RewriteResult:
    assembler = PromptAssembler(brain, content)
    t0 = [
        brain.read_engine("feedback-intake"),
        brain.read_engine("2-draft"),
        *assembler.voice_pack_blocks(piece.voice),
    ]
    try:
        transcript_block = assembler.transcript_block(piece.slug)
    except OSError:
        # No transcript.md — a brain-authored piece (``brain_synced``, cmw-brain-pieces-visibility)
        # reaches review with no interview transcript by design, and this used to raise a
        # PermanentStepError that wedged reviews-done for every such piece (cmw-lessons-loop
        # Ship 1). Ground the rewrite instead: the existing revision (draft.html preferred,
        # piece.md content fallback via the shared piece_md helper, the same seam mint uses) +
        # sources.md (inside the grounding block) + an explicit invent-nothing discipline —
        # the assembler owns the wording so this and the council's shared prefix can never
        # drift. Only a piece with NO readable grounding material at all still fails, loudly.
        from app.piece_detail import read_draft_content

        current_html = read_draft_content(content, piece.slug)
        if current_html is None:
            raise PermanentStepError(
                f"piece {piece.slug!r} has no interview transcript (drafts/{piece.slug}/"
                "transcript.md is missing) and no readable revision content (neither a "
                "draft.html nor a direct-authored piece.md content section), so incorporate "
                "cannot apply editorial fixes — there is no source material at all to ground "
                "any new wording in. A human needs to give this piece real content to edit "
                "before another incorporate round can succeed; retrying this job unchanged will "
                "fail the same way every time."
            )
        t1 = [current_html, assembler.grounding_block_without_transcript(piece.slug)]
    else:
        t1 = [assembler.revision_block(piece.slug), transcript_block]
        try:
            t1.append(assembler.sources_block(piece.slug))
        except OSError:
            pass  # no sources.md yet — the assembler drops missing files too

    prompt = assembler.assemble(
        t0=t0, t1=t1, t2=_build_t2(fixes, round_number=round_number), cache=False
    )

    model = model_for_step(PipelineStep.REWRITE)  # D14 tiering seam — never hardcoded here
    result = await provider.complete(
        step=PipelineStep.REWRITE,
        model=model,
        system=prompt.system,
        messages=prompt.messages,
        max_tokens=max_tokens,
        effort=effort,
        cache=prompt.cache,
        budget=budget,
    )

    if result.stop_reason == "refusal":
        raise RefusalError("incorporate-edits rewrite model refused to apply the fixes")
    draft_html = result.text.strip()
    if not draft_html:
        raise PermanentStepError("incorporate-edits rewrite model returned no content")
    _assert_no_inline_gaps(draft_html)
    return RewriteResult(draft_html=draft_html, usage=result.usage)
