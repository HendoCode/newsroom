"""Per-step model-tiering map (D14; cmw-context-assembly report §3, §12).

D14 fixes **Opus 4.8 for draft/council/lessons** and **Sonnet 5 for classification/light
steps**. The context report resolves the two steps D14 does not name (Oracle rank, interview
next-question) as designer calls — both Opus, because extraction/ranking quality gates the whole
funnel (§3). This module encodes that map verbatim so it can become the routing table every
pipeline step reads.

The tier is a **per-call argument**, not baked into the provider (D14, acceptance criteria):
``model_for_step`` returns the *default* tier for a step, and callers pass an explicit ``model``
to :meth:`LLMProvider.complete`. The one flagged tuning knob (§13) — interview next-question is
Opus by default but Sonnet 5 is a defensible cheaper/faster alternative — is a one-argument
override at the call site precisely because tier is not hard-wired here.
"""

from __future__ import annotations

from enum import Enum

from app.config import get_settings

_settings = get_settings()
MODEL_GLM5 = _settings.glm_5_model_id
MODEL_GLM47 = _settings.glm_4_7_model_id
MODEL_GLM47_FLASH = _settings.glm_4_7_flash_model_id
MODEL_GPT56_TERRA = _settings.gpt_56_terra_model_id

# Anthropic IDs kept for research sidecar + legacy test compat (never used by the live GLM tiers).
MODEL_OPUS = "claude-opus-4-8"
MODEL_SONNET = "claude-sonnet-5"

# OpenRouter (llm_backend == "openrouter") speaks the same GLM-5 tier but through its own
# vendor/model slug (config.openrouter_default_model_id) — the bedrock IDs ("zai.glm-5" etc.)
# don't resolve on OpenRouter. The tier map below routes every GLM slot to this slug when the
# backend is openrouter, so every pipeline step's ``model_for_step`` call stays unchanged.
MODEL_OPENROUTER_DEFAULT = _settings.openrouter_default_model_id


class PipelineStep(str, Enum):
    """Every LLM-driven step / sub-step of the pipeline (context report §4–§9, §12).

    A ``str`` enum so a step round-trips cleanly through Mongo work-state / JSON cost readouts.
    No pipeline *logic* lives here — only the identity each step routes on.
    """

    ORACLE = "oracle"  # §4 — retrieval-heavy convergence ranking
    INTERVIEW_QUESTION = "interview_question"  # §5a — next persona question
    INTERVIEW_CLASSIFY = "interview_classify"  # §5b — D6 bounded input classification
    RESEARCH = "research"  # §5c — bounded fetch-and-summarize sidecar
    RECAP = "recap"  # §5d — D16b faithful "here's what I heard" restatement
    DRAFT = "draft"  # §6 — highest-nuance drafting
    COUNCIL = "council"  # §7 — per-editor scoring (the caching hot-spot)
    FEEDBACK_CLASSIFY = "feedback_classify"  # §8a — bounded 4-way feedback classification
    REWRITE = "rewrite"  # §8b — incorporate-edits drafting-class rewrite
    LESSONS = "lessons"  # §9 — generalizable-lesson extraction


# Step → default model tier.
# GLM 5 is the live default for every step by captain decision 2026-08-14 (option A — hold any
# cheaper split until real spend data exists). RESEARCH stays on MODEL_SONNET because the
# research sidecar is deliberately carved out to the direct Anthropic path for web_search_20260209.
# MODEL_GLM47 and MODEL_GLM47_FLASH are defined and priced but deliberately unused pending that revisit.
# The Opus/Sonnet constants remain only for the carve-out and legacy tests.
# On the openrouter backend, "the GLM 5 tier" is the same model under OpenRouter's slug —
# only the ID the provider must send changes, not which tier each step routes to.
_DEFAULT_TIER = MODEL_OPENROUTER_DEFAULT if _settings.llm_backend == "openrouter" else MODEL_GLM5

STEP_MODEL_TIERS: dict[PipelineStep, str] = {
    PipelineStep.ORACLE: _DEFAULT_TIER,
    PipelineStep.INTERVIEW_QUESTION: _DEFAULT_TIER,
    PipelineStep.INTERVIEW_CLASSIFY: _DEFAULT_TIER,
    PipelineStep.RESEARCH: MODEL_SONNET,
    PipelineStep.RECAP: _DEFAULT_TIER,
    PipelineStep.DRAFT: _DEFAULT_TIER,
    PipelineStep.COUNCIL: _DEFAULT_TIER,
    PipelineStep.FEEDBACK_CLASSIFY: _DEFAULT_TIER,
    PipelineStep.REWRITE: _DEFAULT_TIER,
    PipelineStep.LESSONS: _DEFAULT_TIER,
}


def model_for_step(step: PipelineStep) -> str:
    """The default model tier for ``step`` (D14/§3). Callers may override per call — the tier is
    an argument to :meth:`LLMProvider.complete`, not a property baked into the provider."""
    return STEP_MODEL_TIERS[step]
