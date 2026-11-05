"""Council fan-out primitive (context report §7, §10).

The council's editors all score the *same* revision against the *same* source, so the shared
context (framing + voice pack + partner files + current revision + transcript, ~10–14K tokens) is
one cached prefix read by every editor — the single largest cost lever in the pipeline
(~71% off the shared input at N=6). But the claude-api concurrent-request rule bites: a cache
entry is readable only *after the first response begins streaming*, so firing all N editors at
once makes all N pay the full cache write.

The fix, and the whole reason this primitive exists: **fire one editor, await its first streamed
token (the cache write has begun), then fan out the remaining N−1** — they read the shared prefix
at ~0.1× instead of full price. The council *step* is a later ticket; this reusable primitive
lives in the shared LLM layer so that step (and any other same-prefix fan-out) just calls it.
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel

from app.llm.budget import RunBudget
from app.llm.provider import LLMProvider, LLMResult, Message, SystemPrompt
from app.llm.tiering import MODEL_OPUS, PipelineStep


class FanoutCall(BaseModel):
    """One editor's per-call variable tail (T2): its rubric + prior-round feedback, as the
    ``messages`` after the shared cached prefix. ``label`` is the editor persona name, carried
    through for telemetry / the per-editor result mapping."""

    label: str
    messages: list[Message]


class FanoutResult(BaseModel):
    """One editor's completed scoring call, tagged with its ``label``."""

    label: str
    result: LLMResult


async def council_fanout(
    provider: LLMProvider,
    *,
    system: SystemPrompt,
    editors: list[FanoutCall],
    max_tokens: int,
    model: str = MODEL_OPUS,
    effort: str | None = None,
    cache: bool = False,
    budget: RunBudget | None = None,
    step: PipelineStep = PipelineStep.COUNCIL,
) -> list[FanoutResult]:
    """Score a round's editors against one shared, cached ``system`` prefix.

    ``system`` is the assembler's T0+T1 output with the ``cache_control`` breakpoint at its end
    (build it with :meth:`PromptAssembler.assemble` and ``cache=True``). Each ``FanoutCall`` in
    ``editors`` carries only that editor's T2 tail in its ``messages``.

    Fires the first editor as a stream, awaits its first token (cache write started), then runs
    the rest concurrently reading the now-warm prefix. Results are returned in ``editors`` order.
    Charges ``budget`` per call if supplied (a run-ceiling breach raises before/at the offending
    call). Returns ``[]`` for no editors.
    """
    if not editors:
        return []

    first, rest = editors[0], editors[1:]

    def _complete(call: FanoutCall) -> asyncio.Future[LLMResult]:
        return asyncio.ensure_future(
            provider.complete(
                step=step,
                model=model,
                system=system,
                messages=call.messages,
                max_tokens=max_tokens,
                effort=effort,
                cache=cache,
                budget=budget,
            )
        )

    async with provider.stream(
        step=step,
        model=model,
        system=system,
        messages=first.messages,
        max_tokens=max_tokens,
        effort=effort,
        cache=cache,
        budget=budget,
    ) as first_stream:
        # Await the first token, not the full response: once it streams, the shared prefix cache
        # is being written and the fanned-out siblings can read it.
        await first_stream.wait_first_token()
        rest_futures = [_complete(call) for call in rest]
        first_result = await first_stream.final()
        rest_results = await asyncio.gather(*rest_futures) if rest_futures else []

    results = [FanoutResult(label=first.label, result=first_result)]
    results.extend(
        FanoutResult(label=call.label, result=result)
        for call, result in zip(rest, rest_results, strict=True)
    )
    return results
