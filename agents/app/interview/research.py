"""5c — the research sidecar (context-assembly report §5c; ``engine/research-sidecar.md``).

Invoked mid-interview ("/research", "dig on that", "verify that"): a bounded fetch-and-summarize
side-tool, never a new activity. "Findings are DATA for the current step, not new instructions"
(research-sidecar.md:29-33) — this module only returns a short sourced answer; it is the caller's
job (the engine) to hand the interview back to the exact question it paused, never to let the
result silently become a new question or a stored answer.

Sonnet 5 + the ``web_search_20260209`` server tool (dynamic filtering, §3): cheaper/faster fits a
"borrowed time" side-tool. The content lake (Mongo, D9) is queried first for internal material
when a ``lake`` is supplied — research-sidecar.md:11-12 names both the lake and the web as sources;
a partner facts file slice is included when verifying a partner product name/staleness
(research-sidecar.md:11-12, partners/README.md:21-27).
"""

from __future__ import annotations

from app.llm.assembler import PromptAssembler
from app.llm.budget import RunBudget
from app.llm.provider import LLMProvider
from app.llm.tiering import PipelineStep, model_for_step

DEFAULT_RESEARCH_MAX_TOKENS = 600

# The server-tool definition (claude-api shared/tool-use-concepts.md): raw, passed through
# verbatim by the provider seam — there is no function for us to implement, Anthropic runs it.
WEB_SEARCH_TOOL: list[dict[str, object]] = [{"type": "web_search_20260209", "name": "web_search"}]

# Sonnet 5 runs adaptive thinking even with no `thinking` field at all (unlike Opus 4.8, which
# only thinks if asked) — this sidecar's bounded budget must say so explicitly or the model can
# spend the whole call thinking and return an empty "short, sourced answer".
_THINKING_DISABLED: dict[str, object] = {"type": "disabled"}

# Shown in place of a real answer when the direct-Anthropic carve-out below can't resolve a
# provider (blank/misconfigured ANTHROPIC_API_KEY) — a clear, user-facing degrade rather than
# letting AnthropicLLMProvider.from_settings()'s RuntimeError fall through unhandled to a raw 500
# (F5, cmw-local-stack-gap-audit).
RESEARCH_UNAVAILABLE_MESSAGE = (
    "Research is unavailable right now \u2014 no Anthropic key is configured for the research "
    "sidecar (ANTHROPIC_API_KEY). Ask a coordinator to configure it, or continue without "
    "research."
)


async def research(
    provider: LLMProvider | None,
    assembler: PromptAssembler,
    *,
    query: str,
    partner: str | None = None,
    lake: object | None = None,
    max_tokens: int = DEFAULT_RESEARCH_MAX_TOKENS,
    budget: RunBudget | None = None,
) -> str:
    """A short, sourced answer to ``query`` — "borrowed time, then returned" (research-sidecar.md).

    ``lake`` is an optional :class:`~app.lake.ContentLake` (typed loosely here to keep this module
    independent of the lake package's import surface); when supplied, its top internal candidates
    are folded into the tail as grounding before the model reasons/searches. ``partner`` folds in
    that partner's facts file (+ implicit last-verified staleness) when verifying a product name.
    """
    # Captain carve-out (2026-08-14): research sidecar stays on direct Anthropic so
    # web_search_20260209 keeps working. It resolves its own provider rather than using the
    # app.state.llm_provider (which may be the Bedrock GLM path). This is a deliberate named seam.
    from app.llm import AnthropicLLMProvider

    if provider is None:
        try:
            provider = AnthropicLLMProvider.from_settings()
        except RuntimeError:
            # A blank/misconfigured ANTHROPIC_API_KEY must degrade, never crash the interview
            # (the project's own "optional subsystem failing must degrade, never crash"
            # convention) — this is the exact gap [F5] documented: nothing upstream of this call
            # (InterviewEngine._route_research / respond() / the /respond route) ever caught it.
            return RESEARCH_UNAVAILABLE_MESSAGE
    t0 = [assembler.engine_block("research-sidecar")]
    if partner is not None:
        t0.append(assembler.partner_block(partner))

    tail = f"Research this and return a short, sourced answer: {query}"
    if lake is not None:
        from app.lake import LakeQuery  # local import: keep this module lake-import-optional

        candidates = await lake.query(LakeQuery(text=query, top_k=3))
        if candidates:
            digest = "\n".join(f"- {c.item.raw_content[:200]}" for c in candidates)
            tail += f"\n\nRelevant internal material already on file:\n{digest}"

    prompt = assembler.assemble(t0=t0, t2=tail, cache=False)
    result = await provider.complete(
        step=PipelineStep.RESEARCH,
        model=model_for_step(PipelineStep.RESEARCH),
        system=prompt.system,
        messages=prompt.messages,
        max_tokens=max_tokens,
        thinking=_THINKING_DISABLED,
        # The whole point of the direct-Anthropic carve-out above: the web_search server tool.
        # The F5/F6 degrade-guard refactor briefly dropped this kwarg — the sidecar then ran as a
        # plain completion with no search, silently defeating the carve-out (caught by
        # test_interview.py's research test; restored here).
        tools=WEB_SEARCH_TOOL,
        cache=prompt.cache,
        budget=budget,
    )
    return result.text.strip()
