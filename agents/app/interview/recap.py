"""5d — "here's what I heard" recap (context-assembly report §5d; D16b).

A recap is a **confirmation view over the interviewee's own words, never a separate authoritative
artifact** — it upholds "invent nothing" (D16b). Sonnet 5 (✓ D14 "light"): faithful, low-nuance
restatement. Deliberately lean context (§5d) — just the just-given answer (and the question it
answers), never the whole transcript, voice, or draft; adding register here would risk the model
"improving" the interviewee's words, the opposite of the invariant.

**Hard invariant this module upholds by construction**: it has no write access to the transcript
at all (it only calls the provider and returns text) — the stored answer is never touched here.
Regenerating a recap after an edit (:mod:`app.interview.transcript`) is just calling this again
over the new text.
"""

from __future__ import annotations

from app.llm.budget import RunBudget
from app.llm.provider import LLMProvider
from app.llm.tiering import PipelineStep, model_for_step

DEFAULT_RECAP_MAX_TOKENS = 300

# Sonnet 5 runs adaptive thinking even with no `thinking` field at all (unlike Opus 4.8, which
# only thinks if asked) — this recap's bounded budget must say so explicitly or the model can
# spend the whole call thinking and return an empty restatement.
_THINKING_DISABLED: dict[str, object] = {"type": "disabled"}

_RUBRIC = (
    'Restate the interviewee\'s answer as a confirmation view ("here\'s what I heard"). Use '
    "their own words and figures. Add nothing, infer nothing, soften nothing. Flag anything you "
    "could not ground in what they actually said."
)


async def recap_answer(
    provider: LLMProvider,
    *,
    question: str | None,
    answer: str,
    max_tokens: int = DEFAULT_RECAP_MAX_TOKENS,
    budget: RunBudget | None = None,
) -> str:
    """A faithful "here's what I heard" restatement of ``answer`` — read-only, never persisted
    over the stored transcript answer (D16b; the caller must not write this back)."""
    tail = f"Question: {question}\nAnswer: {answer}" if question else f"Answer: {answer}"
    result = await provider.complete(
        step=PipelineStep.RECAP,
        model=model_for_step(PipelineStep.RECAP),
        system=[_RUBRIC],
        messages=[{"role": "user", "content": tail}],
        max_tokens=max_tokens,
        thinking=_THINKING_DISABLED,
        budget=budget,
    )
    return result.text.strip()
