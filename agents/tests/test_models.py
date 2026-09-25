"""Model-level tests: identities, attributes, and the invariants from domain model §1."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app import models as m


def test_source_rejects_credentials_in_config() -> None:
    # D14: credentials are server-side only, never in the registry doc.
    with pytest.raises(ValidationError):
        m.Source(
            display_name="Slack",
            kind=m.SourceKind.slack,
            classification=m.SourceClassification.read_as_needed,
            config={"api_token": "xoxb-secret"},
        )
    # A non-credential config is fine.
    ok = m.Source(
        display_name="Slack",
        kind=m.SourceKind.slack,
        classification=m.SourceClassification.read_as_needed,
        config={"channels": ["#eng", "#product"]},
    )
    assert ok.config["channels"] == ["#eng", "#product"]


def test_source_linkedin_is_always_read_as_needed() -> None:
    # D8: linkedin-x-clip is always read-as-needed (credential-free, no scraper).
    with pytest.raises(ValidationError):
        m.Source(
            display_name="LinkedIn clips",
            kind=m.SourceKind.linkedin_x_clip,
            classification=m.SourceClassification.scraped_periodically,
        )
    ok = m.Source(
        display_name="LinkedIn clips",
        kind=m.SourceKind.linkedin_x_clip,
        classification=m.SourceClassification.read_as_needed,
    )
    assert ok.lookback_default_days == 7  # settled default (D7)


def test_spike_tangent_has_no_convergence_score() -> None:
    # §5-Q2: a parked tangent has no OracleRun and no convergence score.
    with pytest.raises(ValidationError):
        m.Spike(
            headline="a parked idea",
            creator="a@b.com",
            origin=m.SpikeOrigin(kind=m.SpikeOriginKind.tangent),
            convergence_score=0.5,
        )
    tangent = m.Spike(
        headline="a parked idea",
        creator="a@b.com",
        origin=m.SpikeOrigin(kind=m.SpikeOriginKind.tangent),
    )
    assert tangent.convergence_score is None
    assert tangent.status == m.SpikeStatus.proposed


def test_piece_state_machine_transitions() -> None:
    # The settled 10-state machine (§1.9, now with `released`): only declared edges are legal.
    assert m.can_transition(m.PieceStage.interviewing, m.PieceStage.drafting)
    assert m.can_transition(m.PieceStage.drafting, m.PieceStage.council)
    assert m.can_transition(m.PieceStage.council, m.PieceStage.review)
    assert m.can_transition(m.PieceStage.review, m.PieceStage.finalizing)
    assert m.can_transition(m.PieceStage.finalized, m.PieceStage.lessons)
    assert m.can_transition(m.PieceStage.review, m.PieceStage.paused)
    # Illegal jumps.
    assert not m.can_transition(m.PieceStage.interviewing, m.PieceStage.finalized)
    assert not m.can_transition(m.PieceStage.drafting, m.PieceStage.review)
    assert not m.can_transition(m.PieceStage.lessons, m.PieceStage.drafting)


def test_released_is_a_terminal_state_independent_of_lessons() -> None:
    # finalized -> released is legal, alongside the pre-existing finalized -> lessons edge.
    # Terminal stage: no edge leads out of `released`. Additional Publication Releases are not a
    # stage transition. Legacy `published` coerces to the same member.
    assert m.can_transition(m.PieceStage.finalized, m.PieceStage.released)
    assert m.can_transition(m.PieceStage.finalized, m.PieceStage.lessons)
    assert m.ALLOWED_TRANSITIONS[m.PieceStage.released] == frozenset()
    assert not m.can_transition(m.PieceStage.released, m.PieceStage.finalized)
    assert not m.can_transition(m.PieceStage.released, m.PieceStage.lessons)
    assert m.PieceStage("published") is m.PieceStage.released
    assert m.is_released_stage("published")
    assert m.is_released_stage(m.PieceStage.released)
    assert m.can_transition(m.PieceStage.lessons, m.PieceStage.finalized)


def test_council_requires_mandatory_editors_once_populated() -> None:
    # §1.13: slop-allergist, voice-guardian are never skipped.
    with pytest.raises(ValidationError):
        m.Council(
            piece_id="p1",
            revision="rev-1",
            editor_scores=[m.EditorScore(editor="slop-allergist", score=8)],
        )
    council = m.Council(
        piece_id="p1",
        revision="rev-1",
        editor_scores=[
            m.EditorScore(editor="slop-allergist", score=9, hard_cap_applied=False),
            m.EditorScore(editor="voice-guardian", score=9),
        ],
        aggregate=9.0,
    )
    assert council.meets_bar()
    assert m.MANDATORY_EDITORS.issubset({s.editor for s in council.editor_scores})


def test_council_score_range_enforced() -> None:
    with pytest.raises(ValidationError):
        m.EditorScore(editor="slop-allergist", score=11)


def test_council_empty_is_allowed_and_below_bar() -> None:
    # An unpopulated council (no scores yet) is valid and does not meet the bar.
    council = m.Council(piece_id="p1", revision="rev-1")
    assert not council.meets_bar()


def test_lesson_starts_proposed() -> None:
    # §1.18 / §5-Q4: the machine never self-commits — a lesson starts as a proposal in Mongo.
    lesson = m.Lesson(
        voice="demo-mira",
        observed_change="tightened the intro",
        generalizable_rule="never open by asserting a common belief to knock it down",
    )
    assert lesson.status == m.LessonStatus.proposed


def test_distribution_intent_carried_on_narrative_spike_piece() -> None:
    # §5-Q5: intent is first-class on Narrative and carried onto Spike/Piece.
    intent = m.DistributionIntent(audience="platform engineers", angle="cost, drawn to scale")
    narrative = m.Narrative(author="a@b.com", seed_text="seed", intent=intent)
    spike = m.Spike(
        headline="h",
        creator="a@b.com",
        origin=m.SpikeOrigin(kind=m.SpikeOriginKind.narrative, ref="n1"),
        intent=intent,
    )
    piece = m.Piece(slug="s", voice="demo-mira", intent=intent)
    assert narrative.intent.audience == "platform engineers"
    assert spike.intent.angle == "cost, drawn to scale"
    assert piece.intent.audience == "platform engineers"


def test_mongo_id_alias_roundtrip() -> None:
    piece = m.Piece(slug="s", voice="demo-mira", _id="deadbeef")
    doc = piece.model_dump(by_alias=True)
    assert doc["_id"] == "deadbeef"
    assert doc["stage"] == "interviewing"  # enum stored as plain string value
    assert m.Piece.model_validate(doc).id == "deadbeef"
