"""The pre-interview research gate (research-v1): a piece owned by a ContentProject cannot open
its extraction interview until the project's research requirement is satisfied — a current
research report OR a recorded experiential waiver. Gap interviews and legacy (non-project)
pieces are exempt. Degrades open, never closed, whenever the workflow isn't configured.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.content_workflow import ContentWorkflow
from app.content_workflow.models import (
    ActorRef,
    AggregateRef,
    AuthorityInput,
    AuthorityKind,
    CommandEnvelope,
    CommandKind,
    CommitIdeaPayload,
    PurposeBrief,
    RecordExperientialWaiverPayload,
    ReportFact,
    ResearchReport,
)
from app.content_workflow.store import InMemoryWorkflowState
from app.interview import InterviewEngine
from app.models import Piece, PieceStage
from app.models.common import new_id, utcnow
from app.models.spike import Spike, SpikeOrigin, SpikeOriginKind

ACTOR = ActorRef(subject_id="captain@example.com", email="captain@example.com")


def _engine_app(store, content_store, git_brain):
    from app.main import app

    app.state.interview_engine = InterviewEngine(store, content_store, git_brain, None)
    return app


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _commit_idea(idea_id: str) -> CommandEnvelope:
    return CommandEnvelope(
        command_type=CommandKind.commit_idea,
        aggregate=AggregateRef(kind="idea", id=idea_id),
        actor=ACTOR,
        idempotency_key=f"commit-{idea_id}",
        expected_version=0,
        payload=CommitIdeaPayload(
            project_title="Gate project",
            purpose_brief=PurposeBrief(proposition="p"),
            default_voice_id="demo-dana",
            authorities=[
                AuthorityInput(kind=kind, assignee=ACTOR)
                for kind in (
                    AuthorityKind.direction,
                    AuthorityKind.input_sufficiency,
                    AuthorityKind.voice,
                    AuthorityKind.release,
                )
            ],
            anchor_title="Gate project",
            anchor_slug="gate-project",
            anchor_destination="blog",
        ),
    )


async def _project_workflow() -> tuple[ContentWorkflow, str, int]:
    """A real committed project through the same code path production uses."""
    idea_id = new_id()
    idea = Spike(
        id=idea_id,
        headline="Gate project",
        creator="captain@example.com",
        origin=SpikeOrigin(kind=SpikeOriginKind.tangent),
    )
    workflow = ContentWorkflow(InMemoryWorkflowState([idea]))
    receipt = await workflow.submit(_commit_idea(idea_id))
    assert receipt.outcome == "applied"
    return workflow, str(receipt.result_refs["content_project_id"]), receipt.version_after or 1


async def _waive(workflow: ContentWorkflow, project_id: str, version: int) -> None:
    receipt = await workflow.submit(
        CommandEnvelope(
            command_type=CommandKind.record_experiential_waiver,
            aggregate=AggregateRef(kind="content-project", id=project_id),
            actor=ACTOR,
            idempotency_key=f"waiver-{project_id}",
            expected_version=version,
            payload=RecordExperientialWaiverPayload(
                content_project_id=project_id,
                reason="I have delivered this exact migration myself.",
            ),
        )
    )
    assert receipt.outcome == "applied"


async def _report(store_workflow: ContentWorkflow, project_id: str) -> None:
    await store_workflow.submit_research_report(
        project_id,
        ResearchReport(
            id=new_id(),
            content_project_id=project_id,
            subject="Gate subject",
            facts=[ReportFact(statement="A sourced fact.", source="Internal survey 2025")],
            submitted_by=ACTOR,
            created_at=utcnow(),
            updated_at=utcnow(),
        ),
    )


async def _project_piece(store, project_id: str, *, slug: str) -> Piece:
    piece = Piece(
        slug=slug,
        voice="demo-mira",
        stage=PieceStage.interviewing,
        content_project_id=project_id,
    )
    return await store.pieces.insert(piece)


async def _open(client, piece_id: str, *, is_gap_interview: bool = False):
    return await client.post(
        f"/api/pieces/{piece_id}/interviews",
        json={"interviewer_personas": ["tactician"], "is_gap_interview": is_gap_interview},
    )


@pytest.mark.asyncio
async def test_project_piece_blocked_until_research_or_waiver(store, content_store, git_brain):
    app = _engine_app(store, content_store, git_brain)
    workflow, project_id, version = await _project_workflow()
    piece = await _project_piece(store, project_id, slug="gate-piece")
    app.state.content_workflow = workflow
    try:
        async with _client(app) as client:
            blocked = await _open(client, piece.id)
            assert blocked.status_code == 409
            assert "research report" in blocked.json()["detail"]

            await _waive(workflow, project_id, version)
            opened = await _open(client, piece.id)
            assert opened.status_code == 200, opened.text
    finally:
        app.state.content_workflow = None


@pytest.mark.asyncio
async def test_a_current_report_also_opens_the_gate(store, content_store, git_brain):
    app = _engine_app(store, content_store, git_brain)
    workflow, project_id, _ = await _project_workflow()
    piece = await _project_piece(store, project_id, slug="gate-piece-report")
    app.state.content_workflow = workflow
    try:
        async with _client(app) as client:
            assert (await _open(client, piece.id)).status_code == 409
            await _report(workflow, project_id)
            opened = await _open(client, piece.id)
            assert opened.status_code == 200, opened.text
    finally:
        app.state.content_workflow = None


@pytest.mark.asyncio
async def test_legacy_piece_is_unaffected_by_the_gate(store, content_store, git_brain):
    app = _engine_app(store, content_store, git_brain)
    workflow, _, _ = await _project_workflow()
    piece = Piece(slug="legacy-piece", voice="demo-mira", stage=PieceStage.interviewing)
    piece = await store.pieces.insert(piece)
    app.state.content_workflow = workflow
    try:
        async with _client(app) as client:
            opened = await _open(client, piece.id)
            assert opened.status_code == 200, opened.text
    finally:
        app.state.content_workflow = None


@pytest.mark.asyncio
async def test_gate_degrades_open_without_a_configured_workflow(store, content_store, git_brain):
    app = _engine_app(store, content_store, git_brain)
    piece = Piece(
        slug="orphan-project-piece",
        voice="demo-mira",
        stage=PieceStage.interviewing,
        content_project_id="project-that-does-not-resolve",
    )
    piece = await store.pieces.insert(piece)
    app.state.content_workflow = None
    async with _client(app) as client:
        opened = await _open(client, piece.id)
        assert opened.status_code == 200, opened.text


@pytest.mark.asyncio
async def test_gap_interviews_are_exempt_from_the_gate(store, content_store, git_brain):
    """A gap interview opens mid-pipeline, after the gate has necessarily already been passed —
    re-checking it there would only wedge review rounds on seeded/degraded data."""
    app = _engine_app(store, content_store, git_brain)
    workflow, project_id, _ = await _project_workflow()
    piece = await _project_piece(store, project_id, slug="gate-piece-gap")
    app.state.content_workflow = workflow
    try:
        async with _client(app) as client:
            opened = await _open(client, piece.id, is_gap_interview=True)
            assert opened.status_code == 200, opened.text
            assert opened.json()["is_gap_interview"] is True
    finally:
        app.state.content_workflow = None
