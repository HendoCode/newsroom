"""The sacred transcript (domain model §1.12; D16b) — read, append, and interviewee-edit.

The transcript is the interviewee's verbatim record, piece-scoped, accumulated across every
Interview session on that piece (§5-Q1). It lives in Git as ``drafts/<slug>/transcript.md``
(``app.git.GitContentStore``); this module owns its markdown shape and the two mutations the
engine performs on it:

- :func:`append_turn` — a persona's question + the interviewee's answer, committed as one new
  turn. Turns are grouped under a ``## <persona>`` heading (cosmetic, for a human reading the
  file) but parsed back by a machine-readable HTML-comment anchor
  (``<!-- turn:<id> persona:<slug> research:<bool> -->``) that carries the turn id, the exact
  persona slug, and whether the answer was research-derived — so parsing never depends on
  fuzzy heading text. The anchor is the SOLE record of that provenance: the stored answer
  itself is always the interviewee's clean words (an earlier format inlined a
  ``[RESEARCH-DERIVED] `` marker into the answer text, which leaked into prompts — see
  :func:`strip_legacy_research_markers`).
- :func:`edit_answer` — the interviewee's own edit of a previously stored answer (D16b: they may
  freely edit their own transcribed answers). Splices just that turn's answer text in place;
  everything else in the file, including every other turn, is untouched.

Both mutations commit through :class:`~app.git.GitContentStore`, so every change is a Git
revision (diffable, attributable) of the one sacred, verbatim file — never a summary, never
rewritten by the model (the "here's what I heard" recap in :mod:`app.interview.recap` is a
read-only confirmation view and never calls into this module).
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from app.git.content import GitContentStore
from app.models.common import new_id

# A turn id is a Mongo-style ObjectId hex string (``app.models.common.new_id``), so the anchor
# regex can match it exactly rather than guessing at an id shape.
_ID_RE = r"[0-9a-fA-F]{24}"

# An answer ends at whichever comes first: the next persona ``## `` heading, the next ``**Q — ``
# line, or end of file — ``append_turn`` inserts a heading only immediately before a persona's
# first ``**Q — `` line, never mid-turn, so stopping at either boundary (not just the latter) is
# what makes this match what the writer actually emits across a persona change.
_TURN_RE = re.compile(
    r"\*\*Q — (?P<question>.*?)\*\*\n"
    rf"<!-- turn:(?P<id>{_ID_RE}) persona:(?P<persona>[^\s]+) research:(?P<research>true|false) -->\n"
    r"(?P<answer>.*?)(?=\n## |\n\*\*Q — |\Z)",
    re.DOTALL,
)

# Legacy ``[RESEARCH-DERIVED] `` marker, kept for backward compatibility: an earlier format
# inlined it at the START of a research-sourced answer (immediately after the anchor, or after
# the question line in pre-anchor ``**Q1 — ...**`` files), but it never survived a Google Docs
# edit round trip and — worse — it leaked verbatim into every prompt that read the transcript
# (draft/council/rewrite/interview), so a single research turn misled the whole pipeline about
# the answer's provenance. Fixed (2026-08-14) by moving that provenance into the anchor alone
# (see :func:`append_turn`) and stripping any marker still present in stored data at EVERY read
# boundary (:func:`parse_turns`, :func:`read_transcript`, ``PromptAssembler.transcript_block``).
# Stripped only at an answer boundary (directly after an anchor or question line) — a mid-prose
# occurrence is a genuine mention, never a marker.
_LEGACY_RESEARCH_MARKER_RE = re.compile(
    r"(?m)^(?P<boundary>(?:"
    r"<!-- turn:[^\n]* -->"
    r"|\*\*Q[^\n]*\*\*"
    r")\n)"  # the newline belongs to the preserved boundary, so the anchor keeps its own line
    r"\[RESEARCH-DERIVED\] "
)


def strip_legacy_research_markers(text: str) -> str:
    """Remove any legacy ``[RESEARCH-DERIVED] `` answer marker from ``text``.

    Pure. Keeps the boundary line (anchor or question) intact; drops only the marker itself, so a
    marker-full stored transcript and its cleaned form differ only by the marker — never by
    dropped answer content. The anchor still records ``research:true`` for the turn, so no
    provenance is lost by the strip.
    """
    return _LEGACY_RESEARCH_MARKER_RE.sub(lambda m: m.group("boundary"), text)


class TranscriptTurn(BaseModel):
    """One parsed turn: a persona's question and the interviewee's (verbatim) answer."""

    id: str
    persona: str
    question: str
    answer: str
    research_derived: bool = False


def read_transcript(content: GitContentStore, slug: str) -> str:
    """The sacred transcript for ``slug`` — verbatim minus any legacy research marker, or ``""``
    before any turn exists yet."""
    return strip_legacy_research_markers(content.read_piece_files(slug).transcript_md or "")


def parse_turns(text: str) -> list[TranscriptTurn]:
    """Every turn in ``text``, in document order. Pure — takes/returns no Git state.

    Legacy ``[RESEARCH-DERIVED] `` markers are stripped first (see
    :func:`strip_legacy_research_markers`), so an answer from a pre-fix transcript parses back
    as the interviewee's clean words while ``research_derived`` still carries the truth from the
    anchor.
    """
    return [
        TranscriptTurn(
            id=m.group("id"),
            persona=m.group("persona"),
            question=m.group("question").strip(),
            answer=m.group("answer").strip(),
            research_derived=m.group("research") == "true",
        )
        for m in _TURN_RE.finditer(strip_legacy_research_markers(text))
    ]


def _persona_heading(persona: str) -> str:
    return persona.replace("-", " ").replace("_", " ").title()


def _last_heading(text: str) -> str | None:
    headings = re.findall(r"^## (.+)$", text, re.MULTILINE)
    return headings[-1] if headings else None


def append_turn(
    content: GitContentStore,
    slug: str,
    *,
    persona: str,
    question: str,
    answer: str,
    research_derived: bool = False,
    author_name: str | None = None,
    author_email: str | None = None,
) -> TranscriptTurn:
    """Append one new turn (persona's question + the interviewee's answer) and commit it.

    Groups consecutive turns from the same persona under one ``## <persona>`` heading (purely
    cosmetic — parsing never depends on it); the turn anchor is the single source of truth for
    ``id`` / ``persona`` / ``research_derived`` on read-back. The stored answer is always the
    interviewee's clean words — research provenance lives ONLY in the anchor's
    ``research:true``, never as a marker inlined into the answer text (see the module docstring
    and :func:`strip_legacy_research_markers`).
    """
    turn_id = new_id()
    existing = read_transcript(content, slug)
    heading = _persona_heading(persona)
    block = ""
    if _last_heading(existing) != heading:
        block += f"## {heading}\n\n"
    block += (
        f"**Q — {question}**\n"
        f"<!-- turn:{turn_id} persona:{persona} research:{'true' if research_derived else 'false'} -->\n"
        f"{answer}\n\n"
    )
    updated = f"{existing}{block}" if existing else block
    content.commit_transcript(
        slug,
        updated,
        message=f"interview: {persona} turn",
        author_name=author_name,
        author_email=author_email,
    )
    return TranscriptTurn(
        id=turn_id,
        persona=persona,
        question=question,
        answer=answer,
        research_derived=research_derived,
    )


def edit_answer(
    content: GitContentStore,
    slug: str,
    turn_id: str,
    new_answer: str,
    *,
    author_name: str | None = None,
    author_email: str | None = None,
) -> TranscriptTurn:
    """Splice the interviewee's edited text into turn ``turn_id`` (D16b) and commit.

    Only that turn's answer span changes; the question, the persona/id anchor, every other turn,
    and the rest of the file are byte-identical. An edit clears the research-derived marker — the
    interviewee is now supplying their own words. Raises ``KeyError`` if ``turn_id`` isn't found.
    """
    text = read_transcript(content, slug)
    pattern = re.compile(
        rf"(?P<head>\*\*Q — (?P<question>.*?)\*\*\n)"
        rf"<!-- turn:{re.escape(turn_id)} persona:(?P<persona>[^\s]+) research:(?:true|false) -->\n"
        rf"(?:\[RESEARCH-DERIVED\] )?.*?(?=\n## |\n\*\*Q — |\Z)",
        re.DOTALL,
    )
    match = pattern.search(text)
    if match is None:
        raise KeyError(f"no transcript turn {turn_id!r} for piece {slug!r}")
    persona = match.group("persona")
    question = match.group("question")
    # ``head`` is just "**Q — ...**\n" (the old anchor is matched separately, outside it), so the
    # replacement drops the old anchor and re-emits a fresh one with the research flag cleared.
    replacement = (
        f"{match.group('head')}"
        f"<!-- turn:{turn_id} persona:{persona} research:false -->\n{new_answer}\n\n"
    )
    updated = text[: match.start()] + replacement + text[match.end() :]
    content.commit_transcript(
        slug,
        updated,
        message=f"interview: edit turn {turn_id}",
        author_name=author_name,
        author_email=author_email,
    )
    return TranscriptTurn(id=turn_id, persona=persona, question=question.strip(), answer=new_answer)
