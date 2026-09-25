"""CLASSIFY: the bounded 4-way feedback classification (feedback-intake.md; context report §8a).

    editorial fix   → the machine can apply it (wording, structure, tone).
    information gap → only the author/owner can fill → route to a targeted interview.
    clearance       → a name/figure/number needing owner sign-off → route to the named owner.
    out-of-scope    → park in the Vault; note why it's not being applied (no silent drops).

Sonnet 5 (✓ D14 "classification"; :data:`~app.llm.tiering.PipelineStep.FEEDBACK_CLASSIFY`): lean,
bounded, batched into ONE call for the whole round (context report §8a: "batch the items into one
call to amortize"). Structured output is an instructed-JSON contract, same convention as
:mod:`app.interview.classify` — the shared :class:`~app.llm.provider.LLMProvider` seam has no
schema knob yet, so a malformed/short response is an engine failure
(:class:`~app.review.errors.FeedbackClassificationError`), never guessed at.

The one enrichment worth the tokens (§8a-d): the piece's open GAP/clearance counts, so a comment
answering a known GAP classifies as ``info-gap`` and a figure-reuse question classifies as
``clearance`` — otherwise deliberately lean (no draft, no voice, no transcript).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.llm.budget import RunBudget
from app.llm.pricing import Usage
from app.llm.provider import LLMProvider, LLMResult
from app.llm.tiering import PipelineStep, model_for_step
from app.models import FeedbackType, Piece
from app.review.collect import RawFeedbackItem
from app.review.errors import FeedbackClassificationError

_MIN_MAX_TOKENS = 256
_PER_ITEM_TOKENS = 40
# Sonnet 5 runs adaptive thinking even with no `thinking` field at all (unlike Opus 4.8, which
# only thinks if asked) — a bounded classify budget this tight must say so explicitly or the
# model can spend the whole call thinking and leave nothing for the visible JSON (see the
# `stop_reason == "max_tokens"` handling below).
_THINKING_DISABLED: dict[str, object] = {"type": "disabled"}
# One retry at double budget if the ceiling was hit for a legitimate reason (a genuinely large
# round) rather than thinking eating it — cheap insurance now that thinking is off, before ever
# surfacing a token-ceiling hit to a human as an opaque parse failure.
_MAX_TOKENS_RETRY_MULTIPLIER = 2

_RUBRIC = """You are the review-feedback classifier for a content-machine review round \
(engine/feedback-intake.md). Classify EACH numbered review item into exactly one of four buckets:

- "editorial-fix": wording, structure, or tone the machine can apply directly to the draft.
- "info-gap": a fact only the piece's author/owner can supply — the reviewer is asking for new \
information, not a style change. If an item appears to answer one of the piece's KNOWN OPEN GAPS \
below, classify it "info-gap".
- "clearance": a name/figure/number that needs owner sign-off before it can be published (e.g. \
"can we name this company publicly?", "is this number cleared for external use?"). If an item \
references one of the piece's KNOWN OPEN CLEARANCES below, classify it "clearance".
- "out-of-scope": not applicable to this piece or round at all — a tangent, an unrelated request, \
or something outside what this piece covers. Never silently drop an item; if it doesn't fit the \
other three buckets, it is "out-of-scope".

Respond with ONLY a JSON array, no prose, no code fence — exactly one object per item, IN THE SAME \
ORDER given, each: {"type": "editorial-fix" | "info-gap" | "clearance" | "out-of-scope"}"""

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


@dataclass(frozen=True)
class ClassifiedFeedback:
    raw: RawFeedbackItem
    type: FeedbackType


@dataclass(frozen=True)
class ClassifyResult:
    items: list[ClassifiedFeedback] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)


def _build_tail(piece: Piece, items: list[RawFeedbackItem]) -> str:
    lines = [
        f"KNOWN OPEN GAPS: {piece.open_gaps}",
        f"KNOWN OPEN CLEARANCES: {piece.open_clearances}",
        "",
        "Items:",
    ]
    for i, item in enumerate(items, start=1):
        location = f" (re: {item.location})" if item.location else ""
        reviewer = item.reviewer or "unknown reviewer"
        lines.append(f"{i}. [{reviewer}]{location}: {item.ask}")
    return "\n".join(lines)


def _parse_types(text: str, *, expected: int) -> list[FeedbackType]:
    cleaned = _FENCE_RE.sub("", text).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise FeedbackClassificationError(f"could not parse classifier output: {text!r}") from exc
    if not isinstance(data, list) or len(data) != expected:
        raise FeedbackClassificationError(
            f"expected a JSON array of {expected} classification(s), got: {text!r}"
        )
    types: list[FeedbackType] = []
    for entry in data:
        if not isinstance(entry, dict) or "type" not in entry:
            raise FeedbackClassificationError(f"malformed classification entry: {entry!r}")
        try:
            types.append(FeedbackType(entry["type"]))
        except ValueError as exc:
            raise FeedbackClassificationError(f"unknown feedback type: {entry['type']!r}") from exc
    return types


async def _classify_call(
    provider: LLMProvider,
    *,
    piece: Piece,
    items: list[RawFeedbackItem],
    tokens: int,
    budget: RunBudget | None,
) -> LLMResult:
    return await provider.complete(
        step=PipelineStep.FEEDBACK_CLASSIFY,
        model=model_for_step(PipelineStep.FEEDBACK_CLASSIFY),
        system=[_RUBRIC],
        messages=[{"role": "user", "content": _build_tail(piece, items)}],
        max_tokens=tokens,
        thinking=_THINKING_DISABLED,
        budget=budget,
    )


async def classify_feedback(
    provider: LLMProvider,
    *,
    piece: Piece,
    items: list[RawFeedbackItem],
    max_tokens: int | None = None,
    budget: RunBudget | None = None,
) -> ClassifyResult:
    """Classify every collected item in ONE batched Sonnet call. Empty ``items`` short-circuits
    without calling the model at all — nothing to classify, nothing to spend."""
    if not items:
        return ClassifyResult()

    tokens = max_tokens or max(_MIN_MAX_TOKENS, _PER_ITEM_TOKENS * len(items))
    result = await _classify_call(
        provider, piece=piece, items=items, tokens=tokens, budget=budget
    )
    if result.stop_reason == "max_tokens":
        # A hit token ceiling reads very differently from the model returning prose — retry once
        # at a larger budget before ever treating this as a malformed response.
        retry_tokens = tokens * _MAX_TOKENS_RETRY_MULTIPLIER
        result = await _classify_call(
            provider, piece=piece, items=items, tokens=retry_tokens, budget=budget
        )
        if result.stop_reason == "max_tokens":
            raise FeedbackClassificationError(
                f"classifier hit the {retry_tokens}-token ceiling twice in a row "
                f"(stop_reason=max_tokens) — this is a truncated response, not a malformed one"
            )
    types = _parse_types(result.text, expected=len(items))
    classified = [
        ClassifiedFeedback(raw=item, type=t) for item, t in zip(items, types, strict=True)
    ]
    return ClassifyResult(items=classified, usage=result.usage)
