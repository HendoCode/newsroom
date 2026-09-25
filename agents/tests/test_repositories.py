"""Repository-layer tests against the in-memory async Mongo double.

Exercises CRUD, id/timestamp management, enum encoding, the domain queries, and the Piece
state-machine enforcement at the persistence boundary (§1.9, §3).
"""

from __future__ import annotations

import asyncio

import pytest

from app import models as m
from app.repositories import WorkStateStore


async def test_insert_assigns_id_and_timestamps(store: WorkStateStore) -> None:
    piece = await store.pieces.insert(m.Piece(slug="token-vs-storage", voice="demo-mira"))
    assert piece.id is not None
    assert piece.created_at is not None and piece.updated_at is not None
    fetched = await store.pieces.get(piece.id)
    assert fetched is not None
    assert fetched.slug == "token-vs-storage"
    assert fetched.stage == m.PieceStage.interviewing


async def test_update_sets_fields_and_touches_updated_at(store: WorkStateStore) -> None:
    piece = await store.pieces.insert(m.Piece(slug="s", voice="demo-mira"))
    changed = await store.pieces.update(piece.id, {"title": "A title", "open_gaps": 2})
    assert changed is not None
    assert changed.title == "A title"
    assert changed.open_gaps == 2
    # updated_at is refreshed on write and never predates creation (both read post-round-trip,
    # so both carry Mongo's millisecond truncation and compare fairly).
    assert changed.updated_at >= changed.created_at


async def test_delete(store: WorkStateStore) -> None:
    piece = await store.pieces.insert(m.Piece(slug="s", voice="demo-mira"))
    assert await store.pieces.delete(piece.id) is True
    assert await store.pieces.get(piece.id) is None


async def test_user_get_by_email(store: WorkStateStore) -> None:
    await store.users.insert(m.User(email="alex@example.com", display_name="Alex"))
    found = await store.users.get_by_email("alex@example.com")
    assert found is not None and found.display_name == "Alex"
    assert await store.users.get_by_email("nobody@example.com") is None


async def test_source_queries_and_enum_encoding(store: WorkStateStore) -> None:
    await store.sources.insert(
        m.Source(
            display_name="Team Drive",
            kind=m.SourceKind.gdrive,
            classification=m.SourceClassification.scraped_periodically,
            enabled=True,
        )
    )
    await store.sources.insert(
        m.Source(
            display_name="Disabled feed",
            kind=m.SourceKind.web_rss,
            classification=m.SourceClassification.scraped_periodically,
            enabled=False,
        )
    )
    enabled = await store.sources.list_enabled()
    assert [s.display_name for s in enabled] == ["Team Drive"]
    gdrives = await store.sources.by_kind(m.SourceKind.gdrive)
    assert len(gdrives) == 1 and gdrives[0].kind == m.SourceKind.gdrive


async def test_spike_vault_view(store: WorkStateStore) -> None:
    origin = m.SpikeOrigin(kind=m.SpikeOriginKind.oracle_run, ref="job1")
    await store.spikes.insert(
        m.Spike(
            headline="proposed one", creator="a@b", origin=origin, status=m.SpikeStatus.proposed
        )
    )
    await store.spikes.insert(
        m.Spike(headline="vaulted one", creator="a@b", origin=origin, status=m.SpikeStatus.vaulted)
    )
    await store.spikes.insert(
        m.Spike(headline="in flight", creator="a@b", origin=origin, status=m.SpikeStatus.in_flight)
    )
    vault = await store.spikes.vault()
    assert {s.headline for s in vault} == {"proposed one", "vaulted one"}


async def test_piece_transition_enforces_state_machine(store: WorkStateStore) -> None:
    piece = await store.pieces.insert(m.Piece(slug="s", voice="demo-mira"))
    # Legal chain: interviewing → drafting → council → review.
    piece = await store.pieces.transition(piece.id, m.PieceStage.drafting)
    assert piece.stage == m.PieceStage.drafting
    piece = await store.pieces.transition(piece.id, m.PieceStage.council)
    assert piece.stage == m.PieceStage.council
    # Illegal jump is refused at the data layer.
    with pytest.raises(ValueError):
        await store.pieces.transition(piece.id, m.PieceStage.finalized)


async def test_piece_transition_claims_expected_source_once_under_concurrency(
    store: WorkStateStore,
) -> None:
    piece = await store.pieces.insert(
        m.Piece(slug="s", voice="demo-mira", stage=m.PieceStage.review)
    )

    results = await asyncio.gather(
        store.pieces.transition(
            piece.id, m.PieceStage.finalizing, expected=m.PieceStage.review
        ),
        store.pieces.transition(
            piece.id, m.PieceStage.finalizing, expected=m.PieceStage.review
        ),
        return_exceptions=True,
    )

    assert sum(isinstance(result, m.Piece) for result in results) == 1
    conflicts = [result for result in results if isinstance(result, ValueError)]
    assert len(conflicts) == 1
    assert "expected review" in str(conflicts[0])
    assert (await store.pieces.get(piece.id)).stage == m.PieceStage.finalizing


async def test_piece_archive_works_regardless_of_stage(store: WorkStateStore) -> None:
    # Archiving is orthogonal to the stage machine — it must work from a stage with no outgoing
    # `transition` at all, e.g. the terminal `published` stage.
    piece = await store.pieces.insert(
        m.Piece(slug="s", voice="demo-mira", stage=m.PieceStage.released)
    )
    assert piece.archived_at is None

    archived = await store.pieces.archive(piece.id)
    assert archived.archived_at is not None
    # Otherwise changes nothing else about the piece.
    assert archived.stage == m.PieceStage.released
    assert archived.slug == "s"
    assert archived.voice == "demo-mira"


async def test_piece_unarchive_reverses_archive(store: WorkStateStore) -> None:
    piece = await store.pieces.insert(m.Piece(slug="s", voice="demo-mira"))
    archived = await store.pieces.archive(piece.id)
    assert archived.archived_at is not None

    restored = await store.pieces.unarchive(piece.id)
    assert restored.archived_at is None
    assert restored.stage == piece.stage


async def test_piece_archive_unknown_piece_raises_keyerror(store: WorkStateStore) -> None:
    with pytest.raises(KeyError):
        await store.pieces.archive("nonexistent")


async def test_piece_unarchive_unknown_piece_raises_keyerror(store: WorkStateStore) -> None:
    with pytest.raises(KeyError):
        await store.pieces.unarchive("nonexistent")


async def test_job_queries(store: WorkStateStore) -> None:
    await store.jobs.insert(m.Job(type=m.JobType.oracle, triggered_by="a@b"))
    await store.jobs.insert(m.Job(type=m.JobType.draft, piece_id="p1", status=m.JobStatus.running))
    oracles = await store.jobs.by_type(m.JobType.oracle)
    assert len(oracles) == 1
    running = await store.jobs.by_status(m.JobStatus.running)
    assert len(running) == 1 and running[0].piece_id == "p1"


async def test_job_error_submodel_roundtrip(store: WorkStateStore) -> None:
    job = await store.jobs.insert(
        m.Job(
            type=m.JobType.council,
            piece_id="p1",
            status=m.JobStatus.failed,
            error=m.JobError(code="429", message="rate limited", retryable=True),
        )
    )
    fetched = await store.jobs.get(job.id)
    assert fetched.error is not None
    assert fetched.error.retryable is True and fetched.error.code == "429"


async def test_review_round_latest(store: WorkStateStore) -> None:
    await store.review_rounds.insert(
        m.ReviewRound(piece_id="p1", round_number=1, minted_from_revision="rev-1")
    )
    await store.review_rounds.insert(
        m.ReviewRound(piece_id="p1", round_number=2, minted_from_revision="rev-2")
    )
    latest = await store.review_rounds.latest_for_piece("p1")
    assert latest is not None and latest.round_number == 2
    ordered = await store.review_rounds.by_piece("p1")
    assert [r.round_number for r in ordered] == [1, 2]


async def test_feedback_open_items(store: WorkStateStore) -> None:
    await store.feedback.insert(
        m.FeedbackItem(piece_id="p1", ask="fix typo", type=m.FeedbackType.editorial_fix)
    )
    await store.feedback.insert(
        m.FeedbackItem(
            piece_id="p1",
            ask="need a number",
            type=m.FeedbackType.info_gap,
            status=m.FeedbackStatus.routed,
        )
    )
    open_items = await store.feedback.open_items("p1")
    assert len(open_items) == 1 and open_items[0].ask == "fix typo"


async def test_council_repo_latest(store: WorkStateStore) -> None:
    scores = [
        m.EditorScore(editor="slop-allergist", score=8),
        m.EditorScore(editor="voice-guardian", score=9),
    ]
    await store.councils.insert(
        m.Council(
            piece_id="p1", revision="rev-1", round_number=1, editor_scores=scores, aggregate=8.6
        )
    )
    await store.councils.insert(
        m.Council(
            piece_id="p1", revision="rev-2", round_number=2, editor_scores=scores, aggregate=9.1
        )
    )
    latest = await store.councils.latest_for_piece("p1")
    assert latest is not None and latest.round_number == 2 and latest.meets_bar()


async def test_lesson_proposed_and_by_voice(store: WorkStateStore) -> None:
    await store.lessons.insert(
        m.Lesson(voice="demo-mira", observed_change="c", generalizable_rule="r")
    )
    await store.lessons.insert(
        m.Lesson(
            voice="demo-dana",
            observed_change="c",
            generalizable_rule="r",
            status=m.LessonStatus.accepted,
        )
    )
    proposed = await store.lessons.proposed()
    assert len(proposed) == 1 and proposed[0].voice == "demo-mira"
    dana = await store.lessons.by_voice("demo-dana")
    assert len(dana) == 1


async def test_interview_open_for_piece(store: WorkStateStore) -> None:
    await store.interviews.insert(
        m.Interview(piece_id="p1", interviewer_personas=["ferriss", "architect"])
    )
    await store.interviews.insert(m.Interview(piece_id="p1", status=m.InterviewStatus.complete))
    open_ivs = await store.interviews.open_for_piece("p1")
    assert len(open_ivs) == 1 and open_ivs[0].interviewer_personas == ["ferriss", "architect"]


async def test_interview_by_piece_orders_by_creation_for_stable_round_numbering(
    store: WorkStateStore,
) -> None:
    """A UI numbering interview sessions as "round 1", "round 2", ... needs `by_piece` to return
    them in creation order, not Mongo's unspecified natural order."""
    first = await store.interviews.insert(m.Interview(piece_id="p1", about="round one"))
    second = await store.interviews.insert(
        m.Interview(piece_id="p1", about="round two", is_gap_interview=True)
    )
    ivs = await store.interviews.by_piece("p1")
    assert [iv.id for iv in ivs] == [first.id, second.id]
