"""Transcript turn-parsing round-trip coverage (D16b — the sacred, verbatim transcript).

Regression coverage for a defect where ``parse_turns``' answer boundary stopped only at the next
``**Q — `` line, so the cosmetic ``## <persona>`` heading ``append_turn`` inserts immediately
before a persona's first question bled into the *preceding* turn's parsed answer whenever two
consecutive turns crossed a persona change. Deliberately round-trips through the real writer
(``append_turn``) rather than hand-built markdown fixtures — a fixture written to match the
parser's assumptions is exactly what let this ship unnoticed (see the persona-change test below).
"""

from __future__ import annotations

from app.git.content import GitContentStore
from app.interview.transcript import (
    append_turn,
    edit_answer,
    parse_turns,
    read_transcript,
    strip_legacy_research_markers,
)


def test_append_turn_stores_clean_answer_with_anchor_provenance(content_store: GitContentStore) -> None:
    """A research-derived answer is stored as the interviewee's clean words — provenance lives
    ONLY in the anchor's ``research:true``, never inlined into the answer text (an earlier format
    inlined a ``[RESEARCH-DERIVED] `` marker there, which then leaked verbatim into every prompt
    that read the transcript)."""
    slug = "p-transcript-clean-storage"
    turn = append_turn(
        content_store,
        slug,
        persona="ferriss",
        question="Q?",
        answer="Researched fact.",
        research_derived=True,
    )

    raw = content_store.read_transcript(slug)  # the committed bytes, un-stripped
    assert "[RESEARCH-DERIVED]" not in raw
    assert f"<!-- turn:{turn.id} persona:ferriss research:true -->" in raw

    parsed = parse_turns(raw)[0]
    assert parsed.answer == "Researched fact."
    assert parsed.research_derived is True


def test_parse_turns_strips_legacy_marker_kept_in_stored_data(content_store: GitContentStore) -> None:
    """A marker written by the pre-fix format (no longer produced by ``append_turn``, but present
    in real stored transcripts) parses back as the clean answer, with provenance intact from the
    anchor. Deliberately hand-authored, not round-tripped: the real writer no longer emits it, so
    hand-building the legacy shape is the only way to exercise it."""
    text = (
        "## Ferriss\n\n"
        "**Q — What's the real bill?**\n"
        f"<!-- turn:{'0' * 24} persona:ferriss research:true -->\n"
        "[RESEARCH-DERIVED] Anchor: ~$230/month.\n\n"
        "**Q — A live example?**\n"
        f"<!-- turn:{'1' * 24} persona:ferriss research:false -->\n"
        "From the author's own experience: yes.\n\n"
    )

    turns = parse_turns(text)

    assert [t.answer for t in turns] == [
        "Anchor: ~$230/month.",
        "From the author's own experience: yes.",
    ]
    assert turns[0].research_derived is True
    assert turns[1].research_derived is False


def test_strip_legacy_research_markers_is_boundary_anchored() -> None:
    """The strip removes a marker only at an answer boundary (directly after an anchor or a
    ``**Q`` question line — both shapes legacy data actually used) — a mid-prose occurrence is a
    genuine mention of the marker (e.g. a transcript preamble explaining it) and must survive."""
    anchored = (
        f"<!-- turn:{'0' * 24} persona:ferriss research:true -->\n"
        "[RESEARCH-DERIVED] Researched.\n\n"
    )
    legacy_question_line = "**Q1 — Where's the money going?**\n[RESEARCH-DERIVED] Into tokens.\n\n"
    prose = "Several answers were marked [RESEARCH-DERIVED]. This is why the draft carries a [GAP]."

    stripped = strip_legacy_research_markers(anchored + legacy_question_line + prose)

    assert "[RESEARCH-DERIVED] Researched." not in stripped
    assert "[RESEARCH-DERIVED] Into tokens." not in stripped
    assert "Several answers were marked [RESEARCH-DERIVED]." in stripped


def test_read_transcript_strips_legacy_markers(content_store: GitContentStore) -> None:
    """The module-level read helper returns the stored transcript with any legacy marker already
    stripped, so a consumer that reads ``read_transcript`` directly never sees it either."""
    slug = "p-transcript-read-strips"
    content_store.commit_transcript(
        slug,
        "## Ferriss\n\n"
        "**Q — Q?**\n"
        f"<!-- turn:{'0' * 24} persona:ferriss research:true -->\n"
        "[RESEARCH-DERIVED] Clean now.\n\n",
        message="test: seeded legacy-marker transcript",
    )

    assert "[RESEARCH-DERIVED]" not in read_transcript(content_store, slug)
    assert "Clean now." in read_transcript(content_store, slug)


def test_round_trip_single_persona_multiple_turns(content_store: GitContentStore) -> None:
    slug = "p-transcript-roundtrip"
    t1 = append_turn(content_store, slug, persona="ferriss", question="Q1?", answer="Answer one.")
    t2 = append_turn(content_store, slug, persona="ferriss", question="Q2?", answer="Answer two.")

    turns = parse_turns(read_transcript(content_store, slug))
    assert [t.id for t in turns] == [t1.id, t2.id]
    assert [t.answer for t in turns] == ["Answer one.", "Answer two."]
    assert [t.question for t in turns] == ["Q1?", "Q2?"]


def test_round_trip_across_a_persona_change_does_not_bleed_the_next_heading(
    content_store: GitContentStore,
) -> None:
    """The specific case that fails without the fix: turn N's answer is immediately followed by
    the ``## <next persona>`` heading ``append_turn`` writes ahead of turn N+1's question."""
    slug = "p-transcript-persona-change"
    first = append_turn(
        content_store, slug, persona="ferriss", question="Ferriss Q1?", answer="Ferriss answer."
    )
    second = append_turn(
        content_store, slug, persona="skeptic", question="Skeptic Q1?", answer="Skeptic answer."
    )

    turns = parse_turns(read_transcript(content_store, slug))
    assert len(turns) == 2

    parsed_first, parsed_second = turns
    assert parsed_first.id == first.id
    assert parsed_second.id == second.id

    # The bug: parsed_first.answer used to be "Ferriss answer.\n\n## Skeptic" — the next persona's
    # heading bled into the prior turn's answer.
    assert parsed_first.answer == "Ferriss answer."
    assert "##" not in parsed_first.answer
    assert "Skeptic" not in parsed_first.answer
    assert parsed_second.answer == "Skeptic answer."


def test_round_trip_three_personas_two_changes(content_store: GitContentStore) -> None:
    slug = "p-transcript-three-personas"
    a = append_turn(content_store, slug, persona="ferriss", question="A?", answer="Answer A.")
    b = append_turn(content_store, slug, persona="skeptic", question="B?", answer="Answer B.")
    c = append_turn(content_store, slug, persona="ferriss", question="C?", answer="Answer C.")

    turns = parse_turns(read_transcript(content_store, slug))
    assert [t.id for t in turns] == [a.id, b.id, c.id]
    assert [t.answer for t in turns] == ["Answer A.", "Answer B.", "Answer C."]
    assert [t.persona for t in turns] == ["ferriss", "skeptic", "ferriss"]


def test_edit_answer_across_a_persona_change_preserves_the_next_heading(
    content_store: GitContentStore,
) -> None:
    """``edit_answer`` shares the same "where does an answer end" boundary as ``parse_turns`` —
    editing the last turn before a persona change must not delete the next persona's heading."""
    slug = "p-transcript-edit-persona-change"
    first = append_turn(
        content_store, slug, persona="ferriss", question="Ferriss Q1?", answer="Original answer."
    )
    second = append_turn(
        content_store, slug, persona="skeptic", question="Skeptic Q1?", answer="Skeptic answer."
    )

    edit_answer(content_store, slug, first.id, "Edited answer.")

    text = read_transcript(content_store, slug)
    assert "## Skeptic" in text  # the next persona's heading must survive the splice

    turns = parse_turns(text)
    assert [t.id for t in turns] == [first.id, second.id]
    assert turns[0].answer == "Edited answer."
    assert turns[1].answer == "Skeptic answer."
    assert turns[1].persona == "skeptic"
