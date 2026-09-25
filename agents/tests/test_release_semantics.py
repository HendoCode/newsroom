"""Released stage + immutable Publication Releases + AuthorizeRelease + final-pass invalidation."""

from __future__ import annotations

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.content_workflow.models import (
    ActorRef,
    AggregateRef,
    AuthorityInput,
    AuthorityKind,
    AuthorizeReleasePayload,
    CommandEnvelope,
    CommandKind,
    CommitIdeaPayload,
    PiecePhase,
    ProjectPhase,
    PurposeBrief,
    AcceptFinalRevisionPayload,
    RecordTrivialEditWaiverPayload,
)
from app.content_workflow.store import InMemoryWorkflowState, MongoWorkflowState
from app.content_workflow.workflow import ContentWorkflow
from app.models.common import new_id, utcnow
from app.models.publication import ReleaseActor, TrivialEditWaiver
from app.models.spike import Spike, SpikeOrigin, SpikeOriginKind
from app.release.approval import approval_status
from app.repositories.base import mongo_encode

ACTOR = ActorRef(subject_id="captain@example.com", email="captain@example.com")


def _command(idea_id: str, *, key: str = "commit-1", version: int = 0) -> CommandEnvelope:
    return CommandEnvelope(
        command_type=CommandKind.commit_idea,
        aggregate=AggregateRef(kind="idea", id=idea_id),
        actor=ACTOR,
        idempotency_key=key,
        expected_version=version,
        payload=CommitIdeaPayload(
            project_title="Evidence that compounds",
            purpose_brief=PurposeBrief(
                proposition="Operational evidence should compound across a content family.",
                audience="Enterprise AI leaders",
                angle="Treat evidence as shared infrastructure, not draft decoration.",
                desired_outcome="Readers adopt an evidence-first production loop.",
                why_now="AI content volume is rising faster than trust.",
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
            anchor_title="Evidence that compounds",
            anchor_slug="evidence-that-compounds",
            anchor_destination="blog",
        ),
    )


def _state() -> tuple[InMemoryWorkflowState, str]:
    idea_id = new_id()
    idea = Spike(
        id=idea_id,
        headline="Evidence that compounds",
        creator="captain@example.com",
        origin=SpikeOrigin(kind=SpikeOriginKind.tangent),
    )
    return InMemoryWorkflowState([idea]), idea_id


async def _committed(workflow: ContentWorkflow, idea_id: str) -> tuple[str, str, int]:
    receipt = await workflow.submit(_command(idea_id))
    assert receipt.outcome == "applied"
    return (
        str(receipt.result_refs["content_project_id"]),
        str(receipt.result_refs["anchor_piece_id"]),
        receipt.version_after or 1,
    )


def _accept(project_id: str, piece_id: str, version: int, revision: str, *, key: str = "accept-1") -> CommandEnvelope:
    return CommandEnvelope(
        command_type=CommandKind.accept_final_revision,
        aggregate=AggregateRef(kind="content-project", id=project_id),
        actor=ACTOR,
        idempotency_key=key,
        expected_version=version,
        payload=AcceptFinalRevisionPayload(
            content_project_id=project_id,
            piece_id=piece_id,
            revision=revision,
        ),
    )


def _authorize(project_id: str, piece_id: str, version: int, *, key: str = "auth-1") -> CommandEnvelope:
    return CommandEnvelope(
        command_type=CommandKind.authorize_release,
        aggregate=AggregateRef(kind="content-project", id=project_id),
        actor=ACTOR,
        idempotency_key=key,
        expected_version=version,
        payload=AuthorizeReleasePayload(content_project_id=project_id, piece_id=piece_id),
    )


def _waiver(
    project_id: str,
    piece_id: str,
    version: int,
    *,
    frm: str,
    to: str,
    key: str = "tew-1",
) -> CommandEnvelope:
    return CommandEnvelope(
        command_type=CommandKind.record_trivial_edit_waiver,
        aggregate=AggregateRef(kind="content-project", id=project_id),
        actor=ACTOR,
        idempotency_key=key,
        expected_version=version,
        payload=RecordTrivialEditWaiverPayload(
            content_project_id=project_id,
            piece_id=piece_id,
            from_revision=frm,
            to_revision=to,
            reason="Fixed a typo in the heading.",
        ),
    )


def test_approval_status_valid_when_revisions_match() -> None:
    status = approval_status(
        approved_revision="abc", latest_revision="abc", waivers=[]
    )
    assert status.valid is True
    assert status.invalidated is False


def test_approval_status_invalidated_on_substantive_edit() -> None:
    status = approval_status(
        approved_revision="abc", latest_revision="def", waivers=[]
    )
    assert status.valid is False
    assert status.invalidated is True
    assert "council-reapproval-or-trivial-edit-waiver" in status.requirements


def test_approval_status_valid_with_matching_trivial_waiver() -> None:
    waiver = TrivialEditWaiver(
        piece_id="p",
        from_revision="abc",
        to_revision="def",
        actor=ReleaseActor(subject_id="captain@example.com"),
        reason="typo",
        recorded_at=utcnow(),
    )
    status = approval_status(
        approved_revision="abc", latest_revision="def", waivers=[waiver]
    )
    assert status.valid is True
    assert status.invalidated is False
    assert status.waiver is waiver


@pytest.mark.asyncio
async def test_authorize_release_mints_immutable_numbered_release_and_does_not_complete_workspace() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    project_id, piece_id, version = await _committed(workflow, idea_id)

    accept = await workflow.submit(_accept(project_id, piece_id, version, "rev-a"))
    assert accept.outcome == "applied"
    version = accept.version_after or version + 1

    first = await workflow.submit(_authorize(project_id, piece_id, version, key="auth-1"))
    assert first.outcome == "applied"
    assert first.result_refs["release_number"] == 1
    assert state.projects[project_id].disposition == "active"
    assert state.projects[project_id].disposition != "completed"

    view = await workflow.inspect(project_id)
    assert view.derived_phase == ProjectPhase.final_mile
    assert view.derived_phase != ProjectPhase.completed
    assert view.piece_family[0].derived_phase == PiecePhase.released
    assert view.release is not None
    assert view.release.releases[0].release_number == 1
    commands = {item.command_type: item for item in view.available_commands}
    # Repeatable: AuthorizeRelease stays enabled after the first release (same approved revision).
    assert commands[CommandKind.authorize_release].enabled is True

    version = first.version_after or version + 1
    second = await workflow.submit(_authorize(project_id, piece_id, version, key="auth-2"))
    assert second.outcome == "applied"
    assert second.result_refs["release_number"] == 2
    releases = await state.list_publication_releases(piece_id)
    assert [r.release_number for r in releases] == [1, 2]
    assert releases[0].revision == releases[1].revision == "rev-a"
    # First release is untouched.
    assert releases[0].id == first.result_refs["release_id"]


@pytest.mark.asyncio
async def test_authorize_release_refuses_without_accepted_candidate() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    project_id, piece_id, version = await _committed(workflow, idea_id)

    receipt = await workflow.submit(_authorize(project_id, piece_id, version))
    assert receipt.outcome == "rejected"
    assert receipt.rejection and receipt.rejection.code == "accepted-candidate-required"
    assert state.publication_releases == []


@pytest.mark.asyncio
async def test_substantive_edit_invalidates_approval_until_reaccept_or_waiver() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    project_id, piece_id, version = await _committed(workflow, idea_id)

    accept = await workflow.submit(_accept(project_id, piece_id, version, "rev-a"))
    version = accept.version_after or version + 1
    # Simulate a final-pass canonical edit after acceptance.
    piece = state.legacy_pieces[piece_id]
    piece.latest_revision = "rev-b"

    view = await workflow.inspect(project_id)
    assert view.release is not None
    assert view.release.invalidated is True
    commands = {item.command_type: item for item in view.available_commands}
    assert commands[CommandKind.authorize_release].enabled is False
    assert "council-reapproval-or-trivial-edit-waiver" in commands[CommandKind.authorize_release].requirements
    assert commands[CommandKind.record_trivial_edit_waiver].enabled is True
    assert commands[CommandKind.accept_final_revision].enabled is True

    refused = await workflow.submit(_authorize(project_id, piece_id, version, key="auth-no"))
    assert refused.outcome == "rejected"
    assert refused.rejection and refused.rejection.code == "approval-invalidated"

    # Trivial-edit waiver path: record it, then AuthorizeRelease succeeds.
    waiver = await workflow.submit(
        _waiver(project_id, piece_id, version, frm="rev-a", to="rev-b")
    )
    assert waiver.outcome == "applied"
    version = waiver.version_after or version + 1
    authorized = await workflow.submit(_authorize(project_id, piece_id, version, key="auth-yes"))
    assert authorized.outcome == "applied"
    assert authorized.result_refs["release_number"] == 1


@pytest.mark.asyncio
async def test_council_reapproval_is_accept_final_on_the_new_revision() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    project_id, piece_id, version = await _committed(workflow, idea_id)

    accept = await workflow.submit(_accept(project_id, piece_id, version, "rev-a", key="a1"))
    version = accept.version_after or version + 1
    state.legacy_pieces[piece_id].latest_revision = "rev-b"

    refused = await workflow.submit(_authorize(project_id, piece_id, version, key="no"))
    assert refused.outcome == "rejected"

    reaccept = await workflow.submit(
        _accept(project_id, piece_id, version, "rev-b", key="a2")
    )
    assert reaccept.outcome == "applied"
    version = reaccept.version_after or version + 1
    authorized = await workflow.submit(_authorize(project_id, piece_id, version, key="yes"))
    assert authorized.outcome == "applied"


@pytest.mark.asyncio
async def test_authorize_release_is_idempotent_on_replay() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    project_id, piece_id, version = await _committed(workflow, idea_id)
    accept = await workflow.submit(_accept(project_id, piece_id, version, "rev-a"))
    version = accept.version_after or version + 1
    command = _authorize(project_id, piece_id, version, key="same")
    first = await workflow.submit(command)
    second = await workflow.submit(command)
    assert second == first
    assert len(state.publication_releases) == 1


@pytest.mark.asyncio
async def test_mongo_adapter_round_trips_a_publication_release() -> None:
    mongo_state = MongoWorkflowState(AsyncMongoMockClient()["release_db"])
    idea_id = new_id()
    spike = Spike(
        id=idea_id,
        headline="Evidence that compounds",
        creator="captain@example.com",
        origin=SpikeOrigin(kind=SpikeOriginKind.tangent),
        status="proposed",
        version=0,
    )
    await mongo_state._ideas.insert_one(mongo_encode(spike.model_dump(by_alias=True)))
    workflow = ContentWorkflow(mongo_state)
    receipt = await workflow.submit(_command(idea_id))
    assert receipt.outcome == "applied"
    project_id = str(receipt.result_refs["content_project_id"])
    piece_id = str(receipt.result_refs["anchor_piece_id"])
    version = receipt.version_after or 1
    accept = await workflow.submit(_accept(project_id, piece_id, version, "rev-a"))
    version = accept.version_after or version + 1
    authorized = await workflow.submit(_authorize(project_id, piece_id, version))
    assert authorized.outcome == "applied"
    releases = await mongo_state.list_publication_releases(piece_id)
    assert len(releases) == 1
    assert releases[0].release_number == 1
    piece = await mongo_state.load_legacy_piece(piece_id)
    assert piece is not None
    assert piece.stage == "released"
    project = await mongo_state.load_project(project_id)
    assert project is not None
    assert project.disposition == "active"
