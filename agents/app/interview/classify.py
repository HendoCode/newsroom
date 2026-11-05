"""5b — D6 bounded input classification (context-assembly report §5b; open-decisions D6).

Free-form interviewee input is classified into a **bounded** op set so "any invokable move must
be a defined move" (docs/design.md:260-261) — no silent drops:

- ``answer``        — a direct response to the current question (editable afterward, D16b).
- ``research-this``  — "/research ...", "dig on that", "verify that" (routes to the sidecar).
- ``meta-command``   — a control instruction about the interview itself, not its content. The
  bounded vocabulary (§5b): add-interviewer, drop-interviewer, restart, stop-for-the-day, go-back,
  skip, switch-piece. A command that doesn't match one of these still classifies as meta-command
  with ``meta_command=other`` and a ``note`` — never invented into a different op, never dropped.
- ``tangent``        — a genuine change of subject; routes to the Vault, never discarded.

Sonnet 5 (✓ D14 "classification"): lean, bounded, latency-sensitive. Deliberately minimal context
(§5b-d) — no transcript, no voice pack, no draft — just the bounded rubric and a small state
banner so context-dependent meta-commands ("go back") can resolve. Structured output is done via
an instructed-JSON contract (parsed + validated below) rather than a provider-level schema
feature, since the shared :class:`~app.llm.provider.LLMProvider` seam exposes no structured-output
knob yet; a malformed response is an engine failure (:class:`ClassificationParseError`), not a
classification this module should guess at.
"""

from __future__ import annotations

import json
import re
from enum import Enum

from pydantic import BaseModel, ValidationError

from app.llm.budget import RunBudget
from app.llm.provider import LLMProvider
from app.llm.tiering import PipelineStep, model_for_step

DEFAULT_CLASSIFY_MAX_TOKENS = 200
# Sonnet 5 runs adaptive thinking even with no `thinking` field at all (unlike Opus 4.8, which
# only thinks if asked) — this classifier's bounded budget must say so explicitly or the model
# can spend the whole call thinking and leave nothing for the visible JSON.
_THINKING_DISABLED: dict[str, object] = {"type": "disabled"}
# One retry at double budget if the ceiling was hit for a legitimate reason (unusually long free
# text) rather than thinking eating it — cheap insurance before surfacing a token-ceiling hit to
# a human as an opaque parse failure.
_MAX_TOKENS_RETRY_MULTIPLIER = 2


class InputOp(str, Enum):
    answer = "answer"
    research_this = "research-this"
    meta_command = "meta-command"
    tangent = "tangent"


class MetaCommand(str, Enum):
    """The D6 meta-command vocabulary (context-assembly report §5b)."""

    add_interviewer = "add-interviewer"
    drop_interviewer = "drop-interviewer"
    restart = "restart"
    stop_for_the_day = "stop-for-the-day"
    go_back = "go-back"
    skip = "skip"
    switch_piece = "switch-piece"
    other = "other"  # a novel move — recorded as a note, never a silent no-op (D6)


class ClassifiedInput(BaseModel):
    op: InputOp
    meta_command: MetaCommand | None = None
    note: str | None = None  # e.g. a persona name for add/drop-interviewer, or a free description


class ClassificationParseError(RuntimeError):
    """The classifier's response could not be parsed into a :class:`ClassifiedInput`.

    An engine failure mode, not a legitimate classification outcome — callers should raise/retry
    rather than guess the interviewee's intent from a malformed model response.
    """


_RUBRIC = """You are the interview input classifier (D6). Classify the interviewee's free-form \
input into exactly one bounded operation.

Operations:
- "answer": a direct response to the current question — even partial, vague, or a refusal to
  answer. It is still their answer; classify it as "answer", never invent a different label.
- "research-this": the interviewee wants something looked up or verified before they answer
  (e.g. "/research ...", "dig on that", "verify that").
- "meta-command": an instruction about running the interview itself, not its content. Set
  "meta_command" to exactly one of: add-interviewer, drop-interviewer, restart, stop-for-the-day,
  go-back, skip, switch-piece. If it is a control instruction that matches none of these, still
  classify it as "meta-command" with "meta_command": "other" and put your best short description
  in "note" — never invent a different top-level operation and never drop it silently.
- "tangent": a genuine change of subject, unrelated to the current question or the interview
  controls — material worth keeping, but not an answer to what was asked.

For add-interviewer / drop-interviewer, put the exact persona name mentioned (lowercase, hyphenated
if multi-word) in "note".

Respond with ONLY a JSON object, no prose, no code fence, matching exactly:
{"op": "answer" | "research-this" | "meta-command" | "tangent",
 "meta_command": null or one of "add-interviewer" | "drop-interviewer" | "restart" | \
"stop-for-the-day" | "go-back" | "skip" | "switch-piece" | "other",
 "note": null or a short string}"""

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _state_banner(*, active_piece: str, active_persona: str, current_question: str | None) -> str:
    return (
        f"State: piece={active_piece} persona={active_persona} "
        f"question={current_question or '(none)'}"
    )


def _parse(raw: str) -> ClassifiedInput:
    cleaned = _FENCE_RE.sub("", raw).strip()
    try:
        data = json.loads(cleaned)
        return ClassifiedInput.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ClassificationParseError(f"could not parse classifier output: {raw!r}") from exc


async def classify_input(
    provider: LLMProvider,
    *,
    text: str,
    active_piece: str,
    active_persona: str,
    current_question: str | None,
    max_tokens: int = DEFAULT_CLASSIFY_MAX_TOKENS,
    budget: RunBudget | None = None,
) -> ClassifiedInput:
    """Classify ``text`` into the D6 bounded op set. Raises :class:`ClassificationParseError` if
    the model's response doesn't parse — never silently mis-routes a malformed response."""
    banner = _state_banner(
        active_piece=active_piece, active_persona=active_persona, current_question=current_question
    )
    tail = f"{banner}\nInput: {text}"

    async def _call(tokens: int):
        return await provider.complete(
            step=PipelineStep.INTERVIEW_CLASSIFY,
            model=model_for_step(PipelineStep.INTERVIEW_CLASSIFY),
            system=[_RUBRIC],
            messages=[{"role": "user", "content": tail}],
            max_tokens=tokens,
            thinking=_THINKING_DISABLED,
            budget=budget,
        )

    result = await _call(max_tokens)
    if result.stop_reason == "max_tokens":
        # A hit token ceiling reads very differently from the model returning prose — retry once
        # at a larger budget before ever treating this as a malformed response.
        retry_tokens = max_tokens * _MAX_TOKENS_RETRY_MULTIPLIER
        result = await _call(retry_tokens)
        if result.stop_reason == "max_tokens":
            raise ClassificationParseError(
                f"classifier hit the {retry_tokens}-token ceiling twice in a row "
                f"(stop_reason=max_tokens) — this is a truncated response, not a malformed one"
            )
    return _parse(result.text)
