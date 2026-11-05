"""Token usage + cost accounting (D14 — capture ``usage``; show cost as a courtesy).

Every call captures the four Anthropic ``usage`` counters (input / output / cache-creation /
cache-read) and turns them into a USD estimate for the per-piece cost readout. Cost is a
**courtesy** number (D14), not a billing system — the pricing table is the documented public
rate (context report §2), and the estimate is deterministic so tests and the readout agree.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.llm.tiering import (
    MODEL_GLM5,
    MODEL_GLM47,
    MODEL_GLM47_FLASH,
    MODEL_GPT56_TERRA,
    MODEL_OPENROUTER_DEFAULT,
    MODEL_OPUS,
    MODEL_SONNET,
)

# Cache-token cost multipliers relative to the base input rate (context report §2; claude-api
# prompt-caching table). Read is ~0.1× input; a 5-minute write is 1.25× input; a 1-hour write is
# 2×. The assembler defaults to the 5-minute TTL (§10), so that is the write multiplier here.
_CACHE_READ_MULTIPLIER = 0.1
_CACHE_WRITE_MULTIPLIER = 1.25


class ModelPricing(BaseModel):
    """Per-1M-token USD rates for one model (context report §2)."""

    input_per_mtok: float
    output_per_mtok: float


# Anthropic rates (research sidecar + legacy tests). GLM rates from AWS Price List API
# (us-east-1 on-demand STANDARD, 2026-08-14 query): zai.glm-5 $1.00/$3.20, zai.glm-4.7 $0.60/$2.20,
# zai.glm-4.7-flash $0.07/$0.40 per 1M tokens. Never understate (same convention as Anthropic rates).
MODEL_PRICING: dict[str, ModelPricing] = {
    MODEL_OPUS: ModelPricing(input_per_mtok=5.0, output_per_mtok=25.0),
    MODEL_SONNET: ModelPricing(input_per_mtok=3.0, output_per_mtok=15.0),
    MODEL_GLM5: ModelPricing(input_per_mtok=1.0, output_per_mtok=3.2),
    MODEL_GLM47: ModelPricing(input_per_mtok=0.6, output_per_mtok=2.2),
    MODEL_GLM47_FLASH: ModelPricing(input_per_mtok=0.07, output_per_mtok=0.4),
    MODEL_GPT56_TERRA: ModelPricing(input_per_mtok=2.0, output_per_mtok=12.0),
    # OpenRouter slug for the same GLM-5 tier — same rates as the Bedrock ID; an overridden
    # OPENROUTER_DEFAULT_MODEL_ID with no entry here falls through to 0.0 ("no estimate").
    MODEL_OPENROUTER_DEFAULT: ModelPricing(input_per_mtok=1.0, output_per_mtok=3.2),
}


class Usage(BaseModel):
    """The four Anthropic ``usage`` counters captured from every call (D14)."""

    input_tokens: int = 0  # uncached input processed at full rate
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0  # written to cache (~1.25× input, 5-min TTL)
    cache_read_input_tokens: int = 0  # served from cache (~0.1× input)

    @property
    def total_input_tokens(self) -> int:
        """Full prompt size = uncached + cache-write + cache-read (claude-api: ``input_tokens``
        is only the uncached remainder)."""
        return (
            self.input_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_creation_input_tokens=self.cache_creation_input_tokens
            + other.cache_creation_input_tokens,
            cache_read_input_tokens=self.cache_read_input_tokens
            + other.cache_read_input_tokens,
        )


def cost_usd(model: str, usage: Usage) -> float:
    """USD cost estimate for ``usage`` on ``model`` (context report §2 rates + cache multipliers).

    Unknown models cost ``0.0`` — the readout degrades to "no estimate" rather than raising, so a
    future model tier never breaks a cost display. Cache reads bill at 0.1× and cache writes at
    1.25× the base input rate; output bills at the output rate.
    """
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        return 0.0
    in_rate = pricing.input_per_mtok
    dollars = (
        usage.input_tokens * in_rate
        + usage.cache_read_input_tokens * in_rate * _CACHE_READ_MULTIPLIER
        + usage.cache_creation_input_tokens * in_rate * _CACHE_WRITE_MULTIPLIER
        + usage.output_tokens * pricing.output_per_mtok
    ) / 1_000_000
    return dollars
