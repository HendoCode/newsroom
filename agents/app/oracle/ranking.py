"""Opus convergence-ranking prompt + response parsing for the Oracle (context report §4).

Two-stage rank per the brain's ``engine/1-oracle.md``: retrieval finds the raw material
(not a model job — the content lake does it, D9); this module's prompt drives the model's stage-2
convergence judgment over the retrieved candidates, and its response is parsed back into ranked
spike candidates for ``app.oracle.service`` to persist.

T0 (stable, but never cached here — a single call, sub-4096-token prefix, context report §4b/§4e)
is the oracle engine-step rubric verbatim plus the active voice's style-guide (who the author is /
what they may promote — needed to judge "contrarian points the author actually holds" and
customer/partner mapping). That block lives in ``app.oracle.service`` (it owns the Git brain read);
this module owns the T2 variable tail — the framed candidates + the output-format instruction —
and parsing the model's reply back into validated data.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.lake.query import RankedCandidate
from app.models.job import OracleRunParams
from app.models.narrative import Narrative
from app.orchestration.retry import PermanentStepError

# Bound each candidate's excerpt so a top-K of 40 stays one bounded Opus call (context report
# §4e: "control cost by bounding K at retrieval... not by shrinking the prompt after the fact" —
# this trims the per-candidate excerpt; the retrieval cap itself is ``top_k``, applied by the lake).
_EXCERPT_CHARS = 600

# Models sometimes fence their JSON despite being told not to; tolerate it rather than fail.
_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)

# The ~15 spikes/run ceiling from the engine rubric (``engine/1-oracle.md``: "Produce a ranked
# list of ~15 spikes") — stated to the model, not enforced after the fact; a model returning more
# is still accepted (never silently truncated — spikes are never thrown away, §1.7).
TARGET_SPIKE_COUNT = 15


class RankedSpikeCandidate(BaseModel):
    """One ranked spike as the model returns it — validated before it becomes a persisted Spike."""

    model_config = ConfigDict(extra="ignore")

    headline: str
    convergence_score: float
    customer_partner: str | None = None
    outcome_metric: str | None = None
    rank_rationale: str | None = None
    convergence_note: str | None = None
    source_item_ids: list[str] = Field(default_factory=list)


def format_candidate(index: int, candidate: RankedCandidate) -> str:
    """One compact candidate record: id/source/author/date/tags + a bounded excerpt (§4c)."""
    item = candidate.item
    excerpt = item.raw_content[:_EXCERPT_CHARS]
    if len(item.raw_content) > _EXCERPT_CHARS:
        excerpt += "…"
    meta = item.metadata
    tags = ", ".join(meta.tags) if meta.tags else "none"
    date = meta.content_date.date().isoformat() if meta.content_date else "unknown"
    return (
        f"[{index}] id={item.id} source={item.source_id} author={meta.author or 'unknown'} "
        f"date={date} tags={tags}\n"
        f"{excerpt}"
    )


def build_user_prompt(
    candidates: list[RankedCandidate],
    params: OracleRunParams,
    narrative: Narrative | None,
    *,
    top_k: int,
) -> str:
    """The T2 variable tail: entry-mode framing + candidates + the required JSON output shape."""
    lines = [
        f"Entry mode: {params.entry_mode.value}.",
        f"Lookback window: last {params.lookback_days} day(s).",
        (
            f"Candidates retrieved: {len(candidates)} (rank-and-retrieve, capped at "
            f"top_k={top_k}; this is NOT the whole lake)."
        ),
    ]
    if narrative is not None:
        lines.append(
            "This is Entry B: a narrative seeds this run. Bias your ranking toward candidates "
            "that serve its audience/angle, but do not hard-filter — a strong convergent story "
            f"outside the angle still ranks. Narrative seed: {narrative.seed_text!r}. "
            f"Audience: {narrative.intent.audience or 'none stated'}. "
            f"Angle: {narrative.intent.angle or 'none stated'}."
        )
    else:
        lines.append("This is Entry A: an open scan. Rank purely on convergence, no angle bias.")

    lines.append("\nCandidates:\n")
    lines.extend(format_candidate(i, c) for i, c in enumerate(candidates))

    lines.append(
        f"\nApply the two-stage rank from the rubric above: find the raw material, then score it "
        "up by convergence (named customer/partner, an outcome/metric, connecting threads). "
        f"Return a ranked list of at most {TARGET_SPIKE_COUNT} spikes — top of the list first — "
        "as a JSON array and nothing else (no prose, no markdown fence). Each element:\n"
        '{"headline": str, "convergence_score": number, "customer_partner": str|null, '
        '"outcome_metric": str|null, "rank_rationale": str, "convergence_note": str|null, '
        '"source_item_ids": [the id=... value(s) above this spike converges from, e.g. '
        '"item-123" — NOT the [bracketed] position number]}'
    )
    return "\n".join(lines)


def _resolve_source_item_ids(
    raw_ids: object, candidate_ids: Sequence[str | None] | None
) -> list[str]:
    """Resolve each raw model reference to the real ``source_item_id`` it names.

    ``format_candidate`` presents each candidate as ``[index] id=<real-id> ...``, and the prompt
    asks for ``id=...`` values back — but a model sometimes echoes the bracketed position instead
    (observed live: an integer ``0`` where a string id was expected). Accept either shape: a
    string that matches a real id is used as-is; an int (or a digit-only string) is treated as a
    position into ``candidate_ids`` — the same ordered list ``format_candidate`` enumerated — and
    resolved to the id at that position. Anything that resolves to neither (an out-of-range index,
    an unknown string) is dropped rather than guessed at, matching the pre-existing
    hallucinated-id-filtering discipline.
    """
    if not isinstance(raw_ids, list):
        return []
    ids = candidate_ids or []
    known_ids = {i for i in ids if i is not None}

    resolved: list[str] = []
    for ref in raw_ids:
        real_id: str | None = None
        if isinstance(ref, str):
            if ref in known_ids:
                real_id = ref
            elif ref.isdigit() and 0 <= int(ref) < len(ids):
                real_id = ids[int(ref)]
        elif isinstance(ref, int) and not isinstance(ref, bool) and 0 <= ref < len(ids):
            real_id = ids[ref]
        if real_id is not None:
            resolved.append(real_id)
    return resolved


def parse_ranked_spikes(
    text: str, *, candidate_ids: Sequence[str | None] | None = None
) -> list[RankedSpikeCandidate]:
    """Parse the model's JSON response into validated ranked spikes.

    Tolerates a ```json fenced block; raises :class:`~app.orchestration.retry.PermanentStepError`
    (deterministic — retrying the same malformed shape unchanged would not help) on anything else
    that fails to parse or validate. ``source_item_ids`` entries are resolved against
    ``candidate_ids`` (see :func:`_resolve_source_item_ids`) *before* validation, so a positional
    index the model returns instead of a real id neither crashes ``RankedSpikeCandidate``'s
    ``list[str]`` field nor gets stored as the literal digit — and a hallucinated id never lands
    in a persisted Spike.
    """
    candidate_text = text.strip()
    fence = _JSON_FENCE.search(candidate_text)
    if fence:
        candidate_text = fence.group(1).strip()

    try:
        payload = json.loads(candidate_text)
    except json.JSONDecodeError as exc:
        start, end = candidate_text.find("["), candidate_text.rfind("]")
        if start == -1 or end == -1 or end < start:
            raise PermanentStepError(
                f"oracle ranking response was not valid JSON: {exc}"
            ) from exc
        try:
            payload = json.loads(candidate_text[start : end + 1])
        except json.JSONDecodeError as exc2:
            raise PermanentStepError(
                f"oracle ranking response was not valid JSON: {exc2}"
            ) from exc2

    if not isinstance(payload, list):
        raise PermanentStepError(
            f"oracle ranking response must be a JSON array, got {type(payload).__name__}"
        )

    for item in payload:
        if isinstance(item, dict) and "source_item_ids" in item:
            item["source_item_ids"] = _resolve_source_item_ids(
                item["source_item_ids"], candidate_ids
            )

    try:
        ranked = [RankedSpikeCandidate.model_validate(item) for item in payload]
    except ValidationError as exc:
        raise PermanentStepError(f"oracle ranking response failed validation: {exc}") from exc

    return ranked
