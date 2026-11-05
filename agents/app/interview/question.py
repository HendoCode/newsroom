"""5a — generating the next persona question (context-assembly report §5a).

Opus 4.8 (extraction quality gates the whole funnel, §3). One question per turn, never stacked,
never drafting. The stable prefix (T0) is the active interviewer persona rubric plus the active
voice's ``style-guide.md`` only — interviewers are voice-neutral (§1.2), so the voice pack is
*target* context ("who we're writing for"), never register; the full voice pack (guide + lessons)
belongs to drafting, not here. The growing prefix (T1) is the sacred transcript so far, sent
whole and verbatim — this is the biggest lever (§5a-d): it prevents re-asking and lets the persona
follow the live thread. Cached (the interview reuse locus, §10): the breakpoint sits at the end of
T0+T1 so each new turn reads the prior conversation from cache once the transcript clears the
floor; below the floor the call still works, it just doesn't pay for caching yet.
"""

from __future__ import annotations

from app.interview.transcript import read_transcript
from app.llm.assembler import PromptAssembler
from app.llm.budget import RunBudget
from app.llm.provider import LLMProvider
from app.llm.tiering import PipelineStep, model_for_step

DEFAULT_QUESTION_MAX_TOKENS = 300

_THINKING_DISABLED: dict[str, object] = {"type": "disabled"}


async def ask_next_question(
    provider: LLMProvider,
    assembler: PromptAssembler,
    *,
    piece_slug: str,
    voice_slug: str,
    persona_name: str,
    accepted_research: str | None = None,
    max_tokens: int = DEFAULT_QUESTION_MAX_TOKENS,
    budget: RunBudget | None = None,
) -> str:
    """The next single question for ``persona_name``, given the transcript so far.

    ``accepted_research`` is the short sourced answer a just-accepted research-sidecar call
    returned (§5c/§5a) — data for this turn, never a new instruction, folded into the variable
    tail only (never the cached T0/T1 prefix).
    """
    persona_block = assembler.persona_block("interviewer", persona_name)
    voice_pack = assembler.brain.read_voice(voice_slug)
    t0 = [persona_block]
    if voice_pack.style_guide:
        t0.append(voice_pack.style_guide)
    transcript_so_far = read_transcript(assembler.content, piece_slug)
    t1 = [transcript_so_far] if transcript_so_far else []

    instruction = (
        f"You are {persona_name}. Generate the next single question for this interview — one "
        "question only. Do not stack multiple questions. Do not draft or summarize content."
    )
    if accepted_research:
        instruction += f"\n\nResearch just accepted into this thread:\n{accepted_research}"

    prompt = assembler.assemble(t0=t0, t1=t1, t2=instruction, cache=True)
    result = await provider.complete(
        step=PipelineStep.INTERVIEW_QUESTION,
        model=model_for_step(PipelineStep.INTERVIEW_QUESTION),
        system=prompt.system,
        messages=prompt.messages,
        max_tokens=max_tokens,
        thinking=_THINKING_DISABLED,
        cache=prompt.cache,
        budget=budget,
    )
    return result.text.strip()
