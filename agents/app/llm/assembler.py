"""The three-tier prompt assembler (context report §1.2, §2, §10, §11).

Every stateless call is re-hydrated from three volatility tiers, ordered stable-first so a prompt
cache prefix is well-formed (claude-api: any byte change in the prefix invalidates everything
after it; render order ``tools → system → messages``):

    T0 — brain    : engine step prompt + persona rubric + active voice pack + partner files.
                    Changes only on a Git commit. Front of ``system``.
    T1 — per-piece: sacred transcript, current revision, sources.md. Stable within a piece.
                    After T0, still inside the cached prefix within a council round / interview.
    T2 — per-call : this editor's prior feedback, this feedback item, top-K lake candidates, the
                    current date, the format target. Changes every call → the variable tail,
                    placed in ``messages`` after the last cache breakpoint.

This module owns two things and nothing else (no pipeline logic, no step recipes):

1. *Reading* T0/T1 content through the existing Git data layer (``app.git``) — voice packs in
   override order, engine steps, personas, partner files, transcript, revision, sources — so the
   brain is never re-read ad hoc.
2. *Assembling* those tiers into the Anthropic-wire ``system`` / ``messages`` the provider sends,
   placing the single ``cache_control`` breakpoint at the end of the stable prefix when caching
   is requested, and refusing the silent cache-invalidators (§2) in the T0/T1 prefix.

Caching pays off in exactly two places (§10): the council fan-out and the multi-turn interview.
Elsewhere ``cache=False`` — the sub-floor prefixes would not cache anyway.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from app.git.brain import GitBrain
from app.git.content import GitContentStore

# --- forbidden silent cache-invalidators (context report §2, §10) --------------------------
# Dynamic values interpolated into the stable T0/T1 prefix silently break caching: the prefix
# bytes differ every call, so ``cache_read_input_tokens`` stays zero. These belong in the T2 tail.
# We refuse them structurally rather than hope callers remember.
_INVALIDATOR_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # ISO-8601 timestamp (a `datetime.now()` leak) — date alone is fine (brain files cite dates),
    # so we match only date+time.
    ("iso8601 timestamp", re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")),
    # UUID (a per-run/per-request id).
    (
        "uuid",
        re.compile(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
        ),
    ),
    # Explicit run / piece / request id assignments interpolated into the prefix.
    ("run/piece/request id", re.compile(r"\b(?:run|piece|request)[_-]?id\s*[=:]", re.IGNORECASE)),
]


class CacheInvalidatorError(ValueError):
    """Raised when a stable (T0/T1) block carries a value that would silently break caching."""


class AssembledPrompt(BaseModel):
    """Neutral prompt (plain text). ``cache`` flag is passed to provider; only Anthropic honors it."""

    system: list[str]
    messages: list[dict[str, str]]
    cache: bool = False


class PromptAssembler:
    """Reads brain/content through the Git data layer and assembles tiered prompts.

    Stateless over a request: hold one per service, or construct per call — it caches nothing
    itself (the *prompt* cache lives at the model). All reads go through :class:`GitBrain` /
    :class:`GitContentStore` so the store split (domain model §3) stays honest.
    """

    def __init__(self, brain: GitBrain, content: GitContentStore) -> None:
        self.brain = brain
        self.content = content

    # --- T0 (brain) block builders ---------------------------------------------------------

    def engine_block(self, name: str) -> str:
        """An engine step prompt, e.g. ``2-draft`` (the exact markdown bytes, D1)."""
        return self.brain.read_engine(name)

    def persona_block(self, kind: str, name: str) -> str:
        """An interviewer/editor persona rubric (voice-neutral instruction, §1.2)."""
        return self.brain.read_persona(kind, name).body

    def partner_block(self, name: str) -> str:
        """A partner facts file (naming + ``last-verified`` staleness, §5c/§7)."""
        return self.brain.read_partner(name)

    def voice_pack_blocks(self, slug: str) -> list[str]:
        """The active voice pack in **override order** — guide → style → lessons.

        content-lessons come **last** because they override the guide on conflict (2-draft.md;
        context report §6). Missing files are dropped so a partial pack still assembles. demo-dana
        extras (visual-identity / brand) are not draft-time register and are excluded here.
        """
        pack = self.brain.read_voice(slug)
        ordered = [pack.voice_guide, pack.style_guide, pack.content_lessons]
        return [block for block in ordered if block]

    # --- T1 (per-piece) block builders -----------------------------------------------------

    def transcript_block(self, slug: str) -> str:
        """The sacred verbatim transcript (D16b — always full to the drafter, never summarized).

        A legacy ``[RESEARCH-DERIVED] `` marker in stored data is stripped here too — every read
        boundary must agree, or a research-sourced answer leaks its annotation into the prompt.
        The import is function-level because ``app.interview.engine`` imports this module
        (``engine → assembler``), so a module-level ``assembler → app.interview.transcript``
        edge would be a cycle.
        """
        from app.interview.transcript import strip_legacy_research_markers

        return strip_legacy_research_markers(self.content.read_transcript(slug))

    def revision_block(self, slug: str) -> str:
        """The current ``draft.html`` revision, incl. its trailing editorial/GAP block (§7)."""
        return self.content.read_draft(slug)

    def sources_block(self, slug: str) -> str:
        """``sources.md`` — cited figures + open clearances the drafter may use/mark (§6)."""
        return self.content.read_sources(slug)

    def grounding_block_without_transcript(self, slug: str) -> str:
        """Transcript-optional grounding (cmw-lessons-loop Ship 1) — the shared substitute for
        :meth:`transcript_block` when a brain-authored piece legitimately has no transcript.

        Since ``cmw-brain-pieces-visibility`` made brain-authored drafts first-class Pieces,
        a review-stage piece can legitimately have no ``transcript.md`` (``brain_synced``
        pieces land at ``review`` directly, by design). The transcript guards in incorporate's
        rewrite and the council shared prefix used to treat that as an impossible state and
        fail permanently, which wedged reviews-done — and therefore the whole doc-to-lessons
        loop — for every brain-authored piece. This block replaces the transcript as source
        material: the revision being edited/scored (already in the prompt) plus ``sources.md``
        when present, with an explicit invent-nothing discipline that preserves D16b's spirit
        (no ungrounded invention) without a transcript.

        ONE place for the wording, shared by both halves of the reviews-done pipeline — the
        rewrite (``app.review.rewrite``) and the council shared prefix
        (``app.orchestration.draft_step._transcript_or_grounding``) — so they can never drift
        the way the duplicated raise-guards once did.
        """
        framing = (
            "## No interview transcript — grounding material\n\n"
            f"No interview transcript exists for this piece: drafts/{slug}/transcript.md is "
            "missing. This piece is brain-authored and never went through an interview — a "
            "legitimate state, not an error — and this block replaces the transcript as source "
            "material. Ground every judgment and every change strictly in the existing revision "
            "(included in this prompt) and in sources.md (below, when present). Invent nothing: "
            "every new or reworded sentence must trace to material already in the existing "
            "revision or to a fact cited in sources.md. Anywhere an instruction mentions 'the "
            "transcript', read it as this grounding material. If a requested change cannot be "
            "grounded this way, flag it as an information gap (a [GAP: ...] in the trailing "
            "editorial block) instead of inventing content."
        )
        parts = [framing]
        try:
            parts.append(self.sources_block(slug))
        except OSError:
            pass  # no sources.md — the framing above already qualifies itself with "when present"
        return "\n\n".join(parts)

    # --- assembly --------------------------------------------------------------------------

    def assemble(
        self,
        *,
        t0: list[str],
        t1: list[str] | None = None,
        t2: str | list[dict[str, object]],
        cache: bool = False,
        cache_ttl: str = "5m",
    ) -> AssembledPrompt:
        """Assemble tiers into ``system`` / ``messages``.

        ``t0`` + ``t1`` become the stable ``system`` prefix (stable-first). ``t2`` becomes the
        single user message (a string, or a list of content blocks). With ``cache=True`` a
        ``cache_control`` breakpoint is placed on the **last** stable block (the end of T0+T1) —
        one breakpoint is all the council/interview reuse loci need (§10). Empty stable tiers with
        ``cache=True`` is a programming error (nothing to cache) and raises.

        Raises :class:`CacheInvalidatorError` if a stable block carries a silent invalidator
        (§2) — those belong in ``t2``.
        """
        stable = [*t0, *(t1 or [])]
        if cache:
            if not stable:
                raise CacheInvalidatorError(
                    "cache=True with an empty stable prefix: nothing to cache"
                )
            for block in stable:
                _reject_invalidators(block)

        system: list[str] = list(stable)
        messages: list[dict[str, str]] = [{"role": "user", "content": t2}]
        return AssembledPrompt(system=system, messages=messages, cache=cache)


def _reject_invalidators(block: str) -> None:
    for label, pattern in _INVALIDATOR_PATTERNS:
        if pattern.search(block):
            raise CacheInvalidatorError(
                f"stable (T0/T1) prefix block contains a silent cache-invalidator ({label}); "
                f"dynamic values (current date/time, run/piece ids) belong in the T2 tail (§2, §10)"
            )
