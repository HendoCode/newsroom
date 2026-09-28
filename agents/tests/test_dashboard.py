"""Tests for the dashboard read-model (the shared work queue, Item 3).

Covers the seed (every predicate branch is reachable for the viewer), the join logic in
``build_queue`` against real repository-loaded work-state, and the ``/api/dashboard`` wire
contract. The attribution-only "needs my action" predicate itself is unit-tested in web/ (Vitest);
here we only assert the read-model carries the signals that predicate needs.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import models as m
from app.dashboard import build_queue, load_collections, seed_work_state
from app.main import app
from app.repositories import WorkStateStore

VIEWER = "me@example.com"


def _by_title(items, title):
    return next(i for i in items if i.title == title)


def test_seed_covers_every_predicate_signal() -> None:
    items = build_queue(seed_work_state(VIEWER))

    # review + owner=viewer, with the round & council aggregate joined in.
    token = _by_title(items, "The board on the wall")
    assert token.kind == "piece" and token.stage == "review"
    assert token.owner == VIEWER
    assert token.council_aggregate == 9.2
    assert token.review_round == 2
    assert token.open_gaps == 2

    # interviewing + an open interview assigned to the viewer.
    aws = _by_title(items, "Rehearse the rollback")
    assert aws.stage == "interviewing"
    assert VIEWER in aws.assigned_experts
    assert any(oi.expert == VIEWER for oi in aws.open_interviews)

    # interviewing + owner=viewer + a completed interview (decide "enough input").
    latency = _by_title(items, "Latency budget FAQ")
    assert latency.owner == VIEWER and latency.has_complete_interview is True

    # a failed draft job the viewer triggered — piece stayed at its last stable stage.
    pricing = _by_title(items, "Pricing, explained: what you actually pay for")
    assert pricing.stage == "interviewing"  # flagged, not rolled back (Item 4)
    assert pricing.failed_job is not None
    assert pricing.failed_job.code == "ceiling-exceeded"
    assert pricing.failed_job.triggered_by == VIEWER
    assert pricing.failed_job.retryable is False

    # finalized + owner=viewer + unreviewed proposed lessons.
    agentcore = _by_title(items, "AgentCore technical FAQ")
    assert agentcore.stage == "finalized" and agentcore.lessons_proposed == 5

    # picked-but-unassigned spike the viewer created (coordinator branch).
    spike = _by_title(items, "You're auditing the wrong line item")
    assert spike.kind == "spike" and spike.spike_status == "picked"
    assert spike.creator == VIEWER and spike.spike_assigned is False


def test_seed_titles_are_real_titles_not_slugs() -> None:
    """Placeholder pieces must not show their slug as the title (cmw-boss-facing-presentation,
    MEDIUM): every seeded piece carries a human title distinct from its slug/id — a
    slug-shaped title reads as unfinished data to a boss seeing the app for the first time."""
    items = build_queue(seed_work_state(VIEWER))
    for item in items:
        if item.kind != "piece":
            continue
        # Seed piece ids are deterministic `seed-<slug>` (see `seed_work_state`).
        slug = item.id.removeprefix("seed-")
        assert item.title, f"seeded piece {item.id} has no title"
        assert item.title != slug, f"seeded piece {item.id} shows its slug as the title"
        assert " " in item.title, (
            f"seeded piece {item.id} title looks like a raw slug: {item.title!r}"
        )


def test_seed_includes_teammate_work_for_all_in_flight() -> None:
    items = build_queue(seed_work_state(VIEWER))
    teammate = _by_title(items, "VPC egress guide")
    # Visible in the queue (All in flight) but NOT attributed to the viewer — the predicate must
    # exclude it while flat auth keeps it reachable.
    assert teammate.owner != VIEWER


async def test_build_queue_joins_over_real_store(store: WorkStateStore) -> None:
    piece = await store.pieces.insert(
        m.Piece(slug="s", voice="demo-mira", stage=m.PieceStage.review, owner="a@example.com", open_gaps=3)
    )
    piece = await store.pieces.mark_human_touch(piece.id)
    await store.councils.insert(
        m.Council(
            piece_id=piece.id,
            revision="rev-1",
            round_number=1,
            editor_scores=[
                m.EditorScore(editor="slop-allergist", score=8.0),
                m.EditorScore(editor="voice-guardian", score=8.5),
            ],
            aggregate=8.5,
        )
    )
    await store.interviews.insert(
        m.Interview(piece_id=piece.id, assigned_expert="b@example.com", status=m.InterviewStatus.open)
    )

    items = build_queue(await load_collections(store))
    assert len(items) == 1
    card = items[0]
    assert card.council_aggregate == 8.5
    assert card.open_gaps == 3
    assert [oi.expert for oi in card.open_interviews] == ["b@example.com"]
    # staleness triage (cmw-staleness-timestamps): both timestamps carried through to the card.
    assert piece.last_human_touch_at is not None
    assert card.updated_at == piece.updated_at
    assert card.last_human_touch_at == piece.last_human_touch_at


def test_dashboard_endpoint_seeds_and_attributes_to_viewer() -> None:
    with TestClient(app) as client:  # lifespan runs → no Mongo → seed path
        body = client.get("/api/dashboard", params={"viewer": VIEWER}).json()
    assert body["source"] == "seed"
    assert len(body["items"]) > 0
    owners = {i.get("owner") for i in body["items"] if i["kind"] == "piece"}
    assert VIEWER in owners  # the seed attributes your cards to you


async def test_build_queue_excludes_archived_pieces(store: WorkStateStore) -> None:
    visible = await store.pieces.insert(m.Piece(slug="visible", voice="demo-mira"))
    archived_stage = m.PieceStage.review
    to_archive = await store.pieces.insert(
        m.Piece(slug="archived", voice="demo-mira", stage=archived_stage, owner="a@example.com")
    )
    await store.pieces.archive(to_archive.id)

    items = build_queue(await load_collections(store))

    assert {i.id for i in items} == {visible.id}
    # Not merely absent from the queue — the underlying piece is untouched otherwise.
    reloaded = await store.pieces.get(to_archive.id)
    assert reloaded is not None
    assert reloaded.stage == archived_stage
    assert reloaded.owner == "a@example.com"


def test_dashboard_endpoint_never_leaks_secrets() -> None:
    with TestClient(app) as client:
        raw = client.get("/api/dashboard").text.lower()
    for forbidden in ("api_key", "apikey", "mongo_url", "secret", "password"):
        assert forbidden not in raw
