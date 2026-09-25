"""Test that ContentWorkflow creates legacy Pieces linked to ContentProjects."""

from __future__ import annotations

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.content_workflow.models import (
    ActorRef,
    AggregateRef,
    AuthorityInput,
    AuthorityKind,
    CommandEnvelope,
    CommandKind,
    CommitIdeaPayload,
    HumanObligationKind,
    PieceRole,
    ProjectPhase,
    PurposeBrief,
)
from app.content_workflow.store import InMemoryWorkflowState, MongoWorkflowState
from app.content_workflow.workflow import ContentWorkflow
from app.repositories.base import mongo_encode, new_id
from app.models.piece import Piece
from app.models.spike import Spike, SpikeOrigin, SpikeOriginKind

ACTOR = ActorRef(subject_id="test@example.com", email="test@example.com")


def _command(idea_id: str, *, key: str = "test-commit", version: int = 0) -> CommandEnvelope:
    return CommandEnvelope(
        command_type=CommandKind.commit_idea,
        aggregate=AggregateRef(kind="idea", id=idea_id),
        actor=ACTOR,
        idempotency_key=key,
        expected_version=version,
        payload=CommitIdeaPayload(
            project_title="Test Project",
            purpose_brief=PurposeBrief(
                proposition="Test proposition",
                audience="Test Audience",
                angle="Test Angle",
                desired_outcome="Test Outcome",
                why_now="Test Why Now",
            ),
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
            anchor_title="Test Anchor Piece",
            anchor_slug="test-anchor",
            anchor_destination="blog",
        ),
    )


@pytest.mark.asyncio
async def test_in_memory_workflow_creates_legacy_piece() -> None:
    """InMemoryWorkflowState should create a legacy Piece for testing."""
    spike = Spike(
        id=new_id(),
        headline="Test Idea",
        creator="test@example.com",
        origin=SpikeOrigin(kind=SpikeOriginKind.tangent),
        status="proposed",
        version=0,
    )
    state = InMemoryWorkflowState([spike])
    workflow = ContentWorkflow(state)
    
    receipt = await workflow.submit(_command(spike.id))
    
    assert receipt.outcome == "applied"
    assert len(state.legacy_pieces) == 1
    
    legacy_piece = next(iter(state.legacy_pieces.values()))
    assert legacy_piece.role == PieceRole.anchor
    assert legacy_piece.content_project_id is not None
    assert legacy_piece.slug == "test-anchor"
    assert legacy_piece.voice == "demo-dana"


@pytest.mark.asyncio
async def test_mongo_workflow_creates_legacy_piece() -> None:
    """MongoWorkflowState should create a legacy Piece in MongoDB."""
    # Setup
    db = AsyncMongoMockClient()["test_db"]
    mongo_state = MongoWorkflowState(db)
    
    spike = Spike(
        id=new_id(),
        headline="Test Idea",
        creator="test@example.com",
        origin=SpikeOrigin(kind=SpikeOriginKind.tangent),
        status="proposed",
        version=0,
    )
    await db["spikes"].insert_one(mongo_encode(spike.model_dump(by_alias=True)))
    
    workflow = ContentWorkflow(mongo_state)
    receipt = await workflow.submit(_command(spike.id))
    
    assert receipt.outcome == "applied"
    project_id = str(receipt.result_refs["content_project_id"])
    piece_id = str(receipt.result_refs["anchor_piece_id"])
    
    # Verify legacy Piece was created in MongoDB
    legacy_doc = await db["pieces"].find_one({"_id": piece_id})
    assert legacy_doc is not None
    
    legacy_piece = Piece.model_validate(legacy_doc)
    assert legacy_piece.content_project_id == project_id
    assert legacy_piece.role == PieceRole.anchor
    assert legacy_piece.slug == "test-anchor"


@pytest.mark.asyncio
async def test_legacy_piece_links_to_project() -> None:
    """Legacy Piece correctly links to its ContentProject."""
    db = AsyncMongoMockClient()["test_db"]
    mongo_state = MongoWorkflowState(db)
    
    spike = Spike(id=new_id(), headline="Test", creator="test@example.com", origin=SpikeOrigin(kind=SpikeOriginKind.tangent), status="proposed", version=0)
    await db["spikes"].insert_one(mongo_encode(spike.model_dump(by_alias=True)))
    
    workflow = ContentWorkflow(mongo_state)
    receipt = await workflow.submit(_command(spike.id))
    
    project_id = str(receipt.result_refs["content_project_id"])
    piece_id = str(receipt.result_refs["anchor_piece_id"])
    
    # Verify both ProjectPiece and legacy Piece exist and match
    project_piece = await db["project_pieces"].find_one({"_id": piece_id})
    legacy_piece = await db["pieces"].find_one({"_id": piece_id})
    
    assert project_piece is not None
    assert legacy_piece is not None
    
    # They should have the same ID and title
    assert project_piece["_id"] == legacy_piece["_id"]
    assert project_piece["title"] == legacy_piece["title"]
    assert legacy_piece["content_project_id"] == project_id
