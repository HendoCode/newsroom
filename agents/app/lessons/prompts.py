"""Lessons-call context assembly (cmw-context-assembly report §9; engine/4-lessons-loop.md).

Follows the report's recipe exactly:

- **T0 (stable):** ``engine/4-lessons-loop.md`` + the voice's ``voice-guide.md``/``style-guide.md``
  (~1,000 tok). Content-lessons.md is deliberately **not** in T0 here — the report places it in the
  variable tail alongside the diff, and since this is a single call per piece there is no reuse to
  cache anyway (§9-b: "single call per piece → skip").
- **T2 (variable):** the pre-computed diff, the voice's *existing* content-lessons.md (the #1 lever
  — dedupe against it, §9-d-1), and light piece context, plus the JSON-output contract this module
  also parses back in :func:`parse_candidates`.

No caching (``cache=False``) — the sub-floor prefix would not cache anyway (§9-b/§10).
"""

from __future__ import annotations

import json

from app.git.brain import GitBrain, VoicePack
from app.git.content import GitContentStore
from app.lessons.errors import LessonsParseError
from app.llm.assembler import AssembledPrompt, PromptAssembler
from app.models import Piece

MAX_TOKENS = 1024  # small output — a short list of candidate lessons (§9-e)


def build_lessons_prompt(
    brain: GitBrain,
    content: GitContentStore,
    piece: Piece,
    voice: VoicePack,
    diff_text: str,
) -> AssembledPrompt:
    """Assemble the lessons-call ``system``/``messages`` per the recipe above."""
    t0: list[str] = [brain.read_engine("4-lessons-loop")]
    if voice.voice_guide:
        t0.append(voice.voice_guide)
    if voice.style_guide:
        t0.append(voice.style_guide)

    existing_lessons = voice.content_lessons or "(no existing lessons yet for this voice)"
    piece_context = (
        f"Piece: {piece.title or piece.slug!r} "
        f"(voice: {piece.voice}, target: {piece.target or 'unspecified'})"
    )
    instructions = (
        "Diff of the machine's final draft (before) vs the author's actually-published/edited "
        "version (after), computed structurally by git:\n\n"
        f"{diff_text}\n\n"
        f"{piece_context}\n\n"
        "Existing content-lessons.md for this voice — do NOT repropose any rule already covered "
        "here, even if phrased differently:\n\n"
        f"{existing_lessons}\n\n"
        "For each meaningful change in the diff, decide: what changed, why (most likely — a word "
        "choice, a cut, a reordering, a softened claim), and whether it is a GENERALIZABLE rule or "
        "a one-off edit. Keep only the generalizable keepers. Phrase each keeper the way the "
        "existing lessons are phrased — a short, direct rule.\n\n"
        "Respond with ONLY a JSON array (no prose, no markdown fence). Each element: "
        '{"observed_change": "...", "generalizable_rule": "..."}. If nothing is generalizable, '
        "respond with an empty array []."
    )

    # T1 (per-piece revision/transcript/sources) is unused here — the lessons call's per-piece
    # input is the pre-computed diff, assembled above into the T2 tail — but the assembler still
    # needs a real GitContentStore handle (it never touches it when T1 is omitted).
    assembler = PromptAssembler(brain, content)
    return assembler.assemble(t0=t0, t2=instructions, cache=False)


def parse_candidates(text: str) -> list[dict[str, str]]:
    """Parse the model's proposed-lessons JSON array, tolerating a stray prose/code-fence wrapper.

    Raises :class:`LessonsParseError` if no valid JSON array of candidates can be recovered —
    callers should treat that as a failed call, not silently propose nothing.
    """
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise LessonsParseError(f"model did not return a JSON array: {text!r}")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LessonsParseError(f"invalid JSON from lessons call: {exc}") from exc
    if not isinstance(data, list):
        raise LessonsParseError(f"expected a JSON array, got {type(data).__name__}")

    candidates: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        rule = str(item.get("generalizable_rule", "")).strip()
        change = str(item.get("observed_change", "")).strip()
        if rule:
            candidates.append({"observed_change": change, "generalizable_rule": rule})
    return candidates
