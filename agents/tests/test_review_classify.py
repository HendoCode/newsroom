"""CLASSIFY tests (feedback-intake.md; context report §8a): bounded 4-way, batched, Sonnet tier."""

from __future__ import annotations

import pytest

from app.llm.provider import LLMProvider
from app.llm.tiering import MODEL_GLM5
from app.models import FeedbackType, Piece
from app.review.classify import classify_feedback
from app.review.collect import RawFeedbackItem
from app.review.errors import FeedbackClassificationError


class RecordingProvider(LLMProvider):
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict[str, object]] = []

    async def complete(self, *, step, model, system, messages, max_tokens, effort=None, thinking=None, tools=None, cache=False, budget=None):
        from app.llm.pricing import Usage
        from app.llm.provider import LLMResult

        self.calls.append(
            {
                "step": step,
                "model": model,
                "system": system,
                "messages": messages,
                "max_tokens": max_tokens,
                "thinking": thinking,
            }
        )
        return LLMResult(text=self.text, model=model, stop_reason="end_turn", usage=Usage(), cost_usd=0.0)

    def stream(self, **kwargs):
        raise NotImplementedError

    async def count_tokens(self, *, model, system, messages):
        return 0


class SequencedProvider(LLMProvider):
    """Returns one (text, stop_reason) pair per call, in order — for exercising the
    stop_reason == "max_tokens" retry path without a real model call."""

    def __init__(self, responses: list[tuple[str, str]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    async def complete(self, *, step, model, system, messages, max_tokens, effort=None, thinking=None, tools=None, cache=False, budget=None):
        from app.llm.pricing import Usage
        from app.llm.provider import LLMResult

        text, stop_reason = self.responses[len(self.calls)]
        self.calls.append({"max_tokens": max_tokens, "thinking": thinking})
        return LLMResult(text=text, model=model, stop_reason=stop_reason, usage=Usage(), cost_usd=0.0)

    def stream(self, **kwargs):
        raise NotImplementedError

    async def count_tokens(self, *, model, system, messages):
        return 0


def _piece(**overrides) -> Piece:
    return Piece(slug="token-vs-storage", voice="demo-mira", **overrides)


async def test_classify_empty_items_short_circuits_without_calling_the_model():
    provider = RecordingProvider(text="[]")
    result = await classify_feedback(provider, piece=_piece(), items=[])

    assert result.items == []
    assert provider.calls == []


async def test_classify_happy_path_parses_types_in_order():
    provider = RecordingProvider(
        text='[{"type": "editorial-fix"}, {"type": "info-gap"}, '
        '{"type": "clearance"}, {"type": "out-of-scope"}]'
    )
    items = [
        RawFeedbackItem(ask="tighten this sentence"),
        RawFeedbackItem(ask="what was the actual dollar figure?"),
        RawFeedbackItem(ask="can we name this company publicly?"),
        RawFeedbackItem(ask="unrelated question about a different piece"),
    ]

    result = await classify_feedback(provider, piece=_piece(open_gaps=1, open_clearances=1), items=items)

    assert [c.type for c in result.items] == [
        FeedbackType.editorial_fix,
        FeedbackType.info_gap,
        FeedbackType.clearance,
        FeedbackType.out_of_scope,
    ]
    assert [c.raw for c in result.items] == items

    # Sonnet tier requested via the seam, never hardcoded (D14).
    assert provider.calls[0]["model"] == MODEL_GLM5  # FEEDBACK_CLASSIFY now GLM5 live default
    # one batched call for the whole round, not one per item.
    assert len(provider.calls) == 1
    tail = provider.calls[0]["messages"][0]["content"]
    assert "KNOWN OPEN GAPS: 1" in tail
    assert "KNOWN OPEN CLEARANCES: 1" in tail
    # Sonnet 5 runs adaptive thinking by default even with no `thinking` field at all — this call
    # must disable it explicitly, or the bounded budget can be spent entirely on invisible
    # thinking tokens before any visible JSON (the live truncation this module used to hit).
    assert provider.calls[0]["thinking"] == {"type": "disabled"}


async def test_classify_retries_once_after_hitting_the_token_ceiling():
    """A stop_reason of "max_tokens" is a truncated response, not a malformed one — the first
    call here returns no usable text at all (thinking consumed the whole budget, as it did live),
    and the second (retried) call at a larger budget succeeds."""
    provider = SequencedProvider(
        responses=[
            ("", "max_tokens"),
            ('[{"type": "editorial-fix"}]', "end_turn"),
        ]
    )
    result = await classify_feedback(provider, piece=_piece(), items=[RawFeedbackItem(ask="x")])

    assert [c.type for c in result.items] == [FeedbackType.editorial_fix]
    assert len(provider.calls) == 2
    assert provider.calls[1]["max_tokens"] > provider.calls[0]["max_tokens"]
    assert provider.calls[1]["thinking"] == {"type": "disabled"}


async def test_classify_raises_a_distinct_error_when_the_ceiling_is_hit_twice():
    """Hitting stop_reason == "max_tokens" on the retry too means it's genuinely too little
    budget, not a fluke — this must raise a *different*, clearer message than the JSON-parse
    failure so an operator isn't told the model returned malformed prose when it never got that
    far."""
    provider = SequencedProvider(
        responses=[
            ("", "max_tokens"),
            ("", "max_tokens"),
        ]
    )
    with pytest.raises(FeedbackClassificationError, match="stop_reason=max_tokens"):
        await classify_feedback(provider, piece=_piece(), items=[RawFeedbackItem(ask="x")])
    assert len(provider.calls) == 2


async def test_classify_strips_code_fence():
    provider = RecordingProvider(text='```json\n[{"type": "editorial-fix"}]\n```')
    result = await classify_feedback(provider, piece=_piece(), items=[RawFeedbackItem(ask="x")])

    assert result.items[0].type == FeedbackType.editorial_fix


async def test_classify_raises_on_malformed_json():
    provider = RecordingProvider(text="not json")
    with pytest.raises(FeedbackClassificationError):
        await classify_feedback(provider, piece=_piece(), items=[RawFeedbackItem(ask="x")])


async def test_classify_raises_on_length_mismatch():
    provider = RecordingProvider(text='[{"type": "editorial-fix"}]')
    with pytest.raises(FeedbackClassificationError):
        await classify_feedback(
            provider, piece=_piece(), items=[RawFeedbackItem(ask="x"), RawFeedbackItem(ask="y")]
        )


async def test_classify_raises_on_unknown_type():
    provider = RecordingProvider(text='[{"type": "not-a-real-type"}]')
    with pytest.raises(FeedbackClassificationError):
        await classify_feedback(provider, piece=_piece(), items=[RawFeedbackItem(ask="x")])
