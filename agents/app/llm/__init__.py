"""LLM provider layer (open-decisions Item 1; cmw-context-assembly report).

The shared layer every pipeline step calls: a swappable :class:`LLMProvider` seam over direct
first-party Anthropic (:class:`AnthropicLLMProvider`), the per-step model-tiering map (D14/§3),
the three-tier prompt assembler with the prompt-caching plan (§1.2/§10), the council fan-out
primitive (§7/§10), per-run cost/iteration ceilings (D14), and ``usage``/cost capture.

No pipeline steps or UI here — this is the seam those tickets build on.
"""

from __future__ import annotations

from app.llm.anthropic_provider import (
    AnthropicLLMProvider,
    build_message_kwargs,
    result_from_message,
)
from app.llm.assembler import (
    AssembledPrompt,
    CacheInvalidatorError,
    PromptAssembler,
)
from app.llm.bedrock_glm_provider import BedrockGLMProvider
from app.llm.openai_provider import OpenAILLMProvider
from app.llm.budget import RunBudget, RunBudgetExceeded
from app.llm.council import FanoutCall, FanoutResult, council_fanout
from app.llm.pricing import MODEL_PRICING, ModelPricing, Usage, cost_usd
from app.llm.provider import (
    LLMProvider,
    LLMResult,
    LLMStream,
    Message,
    SystemPrompt,
)
from app.llm.tiering import (
    MODEL_GLM5,
    MODEL_GLM47,
    MODEL_GLM47_FLASH,
    MODEL_OPUS,
    MODEL_SONNET,
    STEP_MODEL_TIERS,
    PipelineStep,
    model_for_step,
)

__all__ = [
    "MODEL_GLM5",
    "MODEL_GLM47",
    "MODEL_GLM47_FLASH",
    "MODEL_OPUS",
    "MODEL_PRICING",
    "MODEL_SONNET",
    "STEP_MODEL_TIERS",
    "AnthropicLLMProvider",
    "AssembledPrompt",
    "BedrockGLMProvider",
    "OpenAILLMProvider",
    "CacheInvalidatorError",
    "FanoutCall",
    "FanoutResult",
    "LLMProvider",
    "LLMResult",
    "LLMStream",
    "Message",
    "ModelPricing",
    "PipelineStep",
    "PromptAssembler",
    "RunBudget",
    "RunBudgetExceeded",
    "SystemPrompt",
    "Usage",
    "build_message_kwargs",
    "cost_usd",
    "council_fanout",
    "model_for_step",
    "result_from_message",
]
