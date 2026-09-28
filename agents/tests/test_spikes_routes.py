"""HTTP-surface tests for the Spikes & Vault browser + pick hand-off (§1.6/§1.7, D15).

Drives ``GET/POST /api/spikes...`` over ASGI with an in-memory store attached to ``app.state``,
proving the store-vs-seed fallback (matching the dashboard's seed spikes), the pick -> create-piece
-> open-interview hand-off (including the intent carry-forward, the spike flip to `picked`, and the
atomic Interview open — cmw-piece-interviewing-without-interview), the 409 on re-picking an
already-picked spike, the 404 on an unknown spike, and the 503-when-unconfigured guard. No Mongo
server, no network.

``app.state`` is a mutable singleton shared by every test module that imports ``app.main.app`` (see
``test_interview.py``), so every test here that reaches past the engine-availability check attaches
its own real ``InterviewEngine`` explicitly rather than relying on whatever a previously-run test
left behind.
"""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.dashboard import seed_work_state
from app.interview import InterviewEngine
from app.main import app
from app.models.narrative import DistributionIntent, Narrative
from app.models.piece import PieceStage
from app.models.spike import Spike, SpikeOrigin, SpikeOriginKind, SpikeStatus
from app.orchestration.draft_step import DraftStep
from app.repositories import WorkStateStore


def _attach(store: WorkStateStore | None, engine: InterviewEngine | None = None) -> None:
    app.state.work_state = store
    app.state.interview_engine = engine


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_list_falls_back_to_seed_matching_dashboard() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["sp1"])
    _attach(store)

    async with _client() as client:
        resp = await client.get("/api/spikes")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "seed"
    assert len(body["items"]) == len(seed_work_state().spikes)
    headlines = {item["headline"] for item in body["items"]}
    assert "You're auditing the wrong line item" in headlines
    origin_kinds = {item["origin"]["kind"] for item in body["items"]}
    # A real value ("oracle-run"/"narrative"/"tangent"), never a leaked Python enum repr like
    # "SpikeOriginKind.oracle_run" (nested BaseModel fields don't inherit use_enum_values).
    assert origin_kinds <= {"oracle-run", "narrative", "tangent"}


async def test_list_reads_real_store_once_populated() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["sp2"])
    await store.spikes.insert(
        Spike(
            headline="Real spike",
            status=SpikeStatus.proposed,
            convergence_score=0.8,
            creator="owner@example.com",
            origin=SpikeOrigin(kind=SpikeOriginKind.oracle_run, ref="job-1"),
        )
    )
    _attach(store)

    async with _client() as client:
        resp = await client.get("/api/spikes")
    body = resp.json()
    assert body["source"] == "store"
    assert len(body["items"]) == 1
    assert body["items"][0]["headline"] == "Real spike"


async def test_get_one_falls_back_to_seed_by_deterministic_id() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["sp1b"])
    _attach(store)

    seed_spike = seed_work_state().spikes[0]
    async with _client() as client:
        # A LATER, independent seed call must resolve the SAME id (deterministic, headline-slug
        # derived) — the sharp-edge the piece seed already handles the same way.
        resp = await client.get(f"/api/spikes/{seed_spike.id}")
    assert resp.status_code == 200
    assert resp.json()["headline"] == seed_spike.headline


async def test_get_one_reads_real_store_and_404s_for_unknown() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["sp1c"])
    inserted = await store.spikes.insert(
        Spike(
            headline="Real spike",
            status=SpikeStatus.proposed,
            creator="owner@example.com",
            origin=SpikeOrigin(kind=SpikeOriginKind.oracle_run, ref="job-1"),
        )
    )
    _attach(store)

    async with _client() as client:
        found = await client.get(f"/api/spikes/{inserted.id}")
        missing = await client.get("/api/spikes/does-not-exist")
    assert found.status_code == 200
    assert found.json()["headline"] == "Real spike"
    assert missing.status_code == 404


async def test_pick_creates_piece_and_flips_spike(content_store, git_brain) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["sp3"])
    spike = await store.spikes.insert(
        Spike(
            headline="You're auditing the wrong line item",
            status=SpikeStatus.proposed,
            convergence_score=0.64,
            creator="demo-mira@example.com",
            origin=SpikeOrigin(kind=SpikeOriginKind.oracle_run, ref="job-1"),
            intent=DistributionIntent(audience="technical leaders", angle="reframe the bill"),
        )
    )
    _attach(store, InterviewEngine(store, content_store, git_brain, None))

    async with _client() as client:
        resp = await client.post(
            f"/api/spikes/{spike.id}/pick",
            json={
                "voice": "demo-mira",
                "owner": "coordinator@example.com",
                "interviewer_personas": ["tactician"],
                "assigned_expert": "expert@example.com",
            },
        )
    assert resp.status_code == 201
    body = resp.json()
    piece_id = body["piece_id"]
    assert body["slug"] == "you-re-auditing-the-wrong-line-item"
    assert body["spike"]["status"] == "picked"
    assert body["spike"]["piece_id"] == piece_id
    # The spike's own attribution never changes — the picker becomes the piece's owner, not the
    # spike's creator (D15: ownership is attribution, not a lock).
    assert body["spike"]["creator"] == "demo-mira@example.com"

    piece = await store.pieces.get(piece_id)
    assert piece is not None
    assert piece.stage == PieceStage.interviewing
    assert piece.voice == "demo-mira"
    assert piece.owner == "coordinator@example.com"
    assert piece.origin_spike_id == spike.id
    assert piece.intent is not None
    assert piece.intent.angle == "reframe the bill"

    # The core regression this ticket asks for: a piece must never sit in `interviewing` with no
    # Interview to conduct — pick now opens one atomically, in the same call.
    interviews = await store.interviews.by_piece(piece_id)
    assert len(interviews) == 1
    assert interviews[0].id == body["interview_id"]
    assert interviews[0].interviewer_personas == ["tactician"]
    assert interviews[0].assigned_expert == "expert@example.com"
    assert interviews[0].about == spike.headline


async def test_pick_honors_explicit_slug_and_target(content_store, git_brain) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["sp4"])
    spike = await store.spikes.insert(
        Spike(
            headline="Some headline",
            status=SpikeStatus.vaulted,
            creator="demo-mira@example.com",
            origin=SpikeOrigin(kind=SpikeOriginKind.tangent),
        )
    )
    _attach(store, InterviewEngine(store, content_store, git_brain, None))

    async with _client() as client:
        resp = await client.post(
            f"/api/spikes/{spike.id}/pick",
            json={
                "voice": "demo-dana",
                "slug": "custom-slug",
                "target": "LinkedIn post",
                "interviewer_personas": ["tactician"],
            },
        )
    assert resp.status_code == 201
    piece = await store.pieces.get(resp.json()["piece_id"])
    assert piece is not None
    assert piece.slug == "custom-slug"
    assert piece.target == "LinkedIn post"


async def test_pick_rejects_already_picked_spike(content_store, git_brain) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["sp5"])
    spike = await store.spikes.insert(
        Spike(
            headline="Already in flight",
            status=SpikeStatus.in_flight,
            creator="demo-mira@example.com",
            origin=SpikeOrigin(kind=SpikeOriginKind.oracle_run, ref="job-1"),
            piece_id="some-piece",
        )
    )
    _attach(store, InterviewEngine(store, content_store, git_brain, None))

    async with _client() as client:
        resp = await client.post(f"/api/spikes/{spike.id}/pick", json={"voice": "demo-mira"})
    assert resp.status_code == 409


async def test_pick_404_for_unknown_spike(content_store, git_brain) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["sp6"])
    _attach(store, InterviewEngine(store, content_store, git_brain, None))

    async with _client() as client:
        resp = await client.post("/api/spikes/does-not-exist/pick", json={"voice": "demo-mira"})
    assert resp.status_code == 404


async def test_pick_422_requires_at_least_one_persona(content_store, git_brain) -> None:
    store = WorkStateStore(AsyncMongoMockClient()["sp6b"])
    spike = await store.spikes.insert(
        Spike(
            headline="Some headline",
            status=SpikeStatus.proposed,
            creator="demo-mira@example.com",
            origin=SpikeOrigin(kind=SpikeOriginKind.oracle_run, ref="job-1"),
        )
    )
    _attach(store, InterviewEngine(store, content_store, git_brain, None))

    async with _client() as client:
        resp = await client.post(
            f"/api/spikes/{spike.id}/pick",
            json={"voice": "demo-mira", "interviewer_personas": []},
        )
    assert resp.status_code == 422
    # All-or-nothing: no piece was left behind, and the spike is still pickable.
    assert await store.pieces.find({}) == []
    unchanged = await store.spikes.get(spike.id)
    assert unchanged is not None
    assert unchanged.status == SpikeStatus.proposed


async def test_pick_422_unknown_persona_leaves_no_piece_behind(content_store, git_brain) -> None:
    """The exact invariant this ticket enforces: pick is all-or-nothing. An unknown persona name
    must never leave a piece sitting in `interviewing` with no Interview to conduct."""
    store = WorkStateStore(AsyncMongoMockClient()["sp6c"])
    spike = await store.spikes.insert(
        Spike(
            headline="Some headline",
            status=SpikeStatus.proposed,
            creator="demo-mira@example.com",
            origin=SpikeOrigin(kind=SpikeOriginKind.oracle_run, ref="job-1"),
        )
    )
    _attach(store, InterviewEngine(store, content_store, git_brain, None))

    async with _client() as client:
        resp = await client.post(
            f"/api/spikes/{spike.id}/pick",
            json={"voice": "demo-mira", "interviewer_personas": ["nonexistent"]},
        )
    assert resp.status_code == 422
    assert await store.pieces.find({}) == []
    assert await store.interviews.find({}) == []
    unchanged = await store.spikes.get(spike.id)
    assert unchanged is not None
    assert unchanged.status == SpikeStatus.proposed
    assert unchanged.piece_id is None


async def test_pick_503_when_unconfigured() -> None:
    _attach(None)
    async with _client() as client:
        resp = await client.post("/api/spikes/x/pick", json={"voice": "demo-mira"})
    assert resp.status_code == 503
    # GET never 503s — it always has the seed fallback.
    async with _client() as client:
        listed = await client.get("/api/spikes")
    assert listed.status_code == 200
    assert listed.json()["source"] == "seed"


# --- mint-from-narrative (Option B fast path, cmw-narrative-first-entry-point): a "new piece ----
# --- from my own idea" entry that skips the Oracle ranking run and the ranked-spikes review -----
# --- table, but must still mint a real narrative-origin Spike (see MintSpikeFromNarrativeRequest's
# --- docstring for why: DraftStep._purpose_block has no purpose block at all without one). -------


async def test_mint_from_narrative_creates_unranked_narrative_origin_spike() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["sp7"])
    narrative = await store.narratives.insert(
        Narrative(
            author="hendo@example.com",
            seed_text="Customers insulate themselves from data-centre risk across geographies.",
            intent=DistributionIntent(audience="infra leaders", angle="multi-vendor resilience"),
        )
    )
    _attach(store)

    async with _client() as client:
        resp = await client.post(
            "/api/spikes/from-narrative",
            json={"narrative_id": narrative.id, "headline": "Why single-vendor infra is a risk"},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["headline"] == "Why single-vendor infra is a risk"
    assert body["status"] == "proposed"
    assert body["creator"] == "hendo@example.com"
    assert body["origin"] == {"kind": "narrative", "ref": narrative.id}
    # Nothing ranked this — no Oracle run means no score/rationale, and that must be honest,
    # never a fabricated or defaulted value.
    assert body["convergence_score"] is None
    assert body["rank_rationale"] is None
    assert body["convergence_note"] is None
    assert body["intent"] == {"audience": "infra leaders", "angle": "multi-vendor resilience"}

    stored_spike = await store.spikes.get(body["id"])
    assert stored_spike is not None
    assert stored_spike.origin.kind == SpikeOriginKind.narrative


async def test_mint_from_narrative_honors_explicit_creator() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["sp8"])
    narrative = await store.narratives.insert(
        Narrative(author="hendo@example.com", seed_text="Some narrative.")
    )
    _attach(store)

    async with _client() as client:
        resp = await client.post(
            "/api/spikes/from-narrative",
            json={
                "narrative_id": narrative.id,
                "headline": "A headline",
                "creator": "coordinator@example.com",
            },
        )
    assert resp.status_code == 201
    assert resp.json()["creator"] == "coordinator@example.com"


async def test_mint_from_narrative_404_for_unknown_narrative() -> None:
    store = WorkStateStore(AsyncMongoMockClient()["sp9"])
    _attach(store)

    async with _client() as client:
        resp = await client.post(
            "/api/spikes/from-narrative",
            json={"narrative_id": "does-not-exist", "headline": "A headline"},
        )
    assert resp.status_code == 404


async def test_mint_from_narrative_503_when_unconfigured() -> None:
    _attach(None)
    async with _client() as client:
        resp = await client.post(
            "/api/spikes/from-narrative",
            json={"narrative_id": "x", "headline": "A headline"},
        )
    assert resp.status_code == 503


async def test_narrative_fast_path_end_to_end_purpose_block_carries_narrative_text(
    content_store, git_brain
) -> None:
    """The regression this ticket's hard requirement asks for: the fast path (mint spike -> pick
    spike, skipping the Oracle ranking and ranked-spikes table) must produce a piece whose
    DraftStep purpose block is present and carries the author's own narrative text — the exact
    signal `_purpose_block` needs to avoid PR #74's wrong-subject-draft failure mode."""
    store = WorkStateStore(AsyncMongoMockClient()["sp10"])
    _attach(store, InterviewEngine(store, content_store, git_brain, None))

    async with _client() as client:
        narrative_resp = await client.post(
            "/api/narratives",
            json={
                "author": "hendo@example.com",
                "seed_text": "Customers insulate themselves from data-centre risk across geographies and vendors.",
                "audience": "infra decision-makers",
                "angle": "deliberate multi-vendor resilience",
            },
        )
        assert narrative_resp.status_code == 201
        narrative_id = narrative_resp.json()["id"]

        spike_resp = await client.post(
            "/api/spikes/from-narrative",
            json={
                "narrative_id": narrative_id,
                "headline": "How infra teams insulate themselves from data-centre risk",
            },
        )
        assert spike_resp.status_code == 201
        spike_id = spike_resp.json()["id"]

        pick_resp = await client.post(
            f"/api/spikes/{spike_id}/pick",
            json={"voice": "demo-mira", "interviewer_personas": ["tactician"]},
        )
        assert pick_resp.status_code == 201
        piece_id = pick_resp.json()["piece_id"]

    piece = await store.pieces.get(piece_id)
    assert piece is not None
    assert piece.origin_spike_id == spike_id

    block = await DraftStep._purpose_block(store, piece)

    assert block is not None
    assert "infra decision-makers" in block
    assert "deliberate multi-vendor resilience" in block
    assert "How infra teams insulate themselves from data-centre risk" in block
    assert (
        "Customers insulate themselves from data-centre risk across geographies and vendors"
        in block
    )
    # Nothing ranked this idea — the block must stay coherent with no "why this was picked" or
    # convergence commentary rather than emitting a half-built line for absent data.
    assert "Why this idea was picked" not in block
    assert "Convergence note" not in block
