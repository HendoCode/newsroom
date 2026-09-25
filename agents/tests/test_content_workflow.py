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
from app.models.common import new_id, utcnow
from app.models.spike import Spike, SpikeOrigin, SpikeOriginKind
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


@pytest.mark.asyncio
async def test_commit_idea_creates_complete_vertical_tracer() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)

    receipt = await workflow.submit(_command(idea_id))

    assert receipt.outcome == "applied"
    project_id = str(receipt.result_refs["content_project_id"])
    project = state.projects[project_id]
    piece = next(iter(state.pieces.values()))
    obligation = next(iter(state.obligations.values()))
    assert state.ideas[idea_id].content_project_id == project_id
    assert state.ideas[idea_id].status == "in-use"
    assert state.ideas[idea_id].version == 1
    assert project.evidence_base_id == receipt.result_refs["evidence_base_id"]
    assert {item.kind for item in project.authorities} == {
        AuthorityKind.direction,
        AuthorityKind.input_sufficiency,
        AuthorityKind.voice,
        AuthorityKind.release,
    }
    assert piece.content_project_id == project_id
    assert piece.role == PieceRole.anchor
    assert obligation.content_project_id == project_id
    assert obligation.kind == HumanObligationKind.confirm_input_sufficiency


@pytest.mark.asyncio
async def test_invalid_idea_is_rejected_without_writes() -> None:
    state, _ = _state()
    workflow = ContentWorkflow(state)

    receipt = await workflow.submit(_command("missing"))

    assert receipt.outcome == "rejected"
    assert receipt.rejection and receipt.rejection.code == "idea-not-found"
    assert state.projects == {}
    assert state.pieces == {}
    assert state.obligations == {}


@pytest.mark.asyncio
async def test_duplicate_key_same_payload_returns_original_receipt() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    command = _command(idea_id)

    first = await workflow.submit(command)
    second = await workflow.submit(command)

    assert second == first
    assert len(state.projects) == 1
    assert len(state.pieces) == 1


@pytest.mark.asyncio
async def test_duplicate_key_different_payload_is_rejected() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    await workflow.submit(_command(idea_id))
    changed = _command(idea_id)
    changed.payload.project_title = "Different project"

    receipt = await workflow.submit(changed)

    assert receipt.outcome == "rejected"
    assert receipt.rejection and receipt.rejection.code == "idempotency-key-reused"
    assert len(state.projects) == 1


@pytest.mark.asyncio
async def test_version_conflict_is_typed_and_has_no_writes() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)

    receipt = await workflow.submit(_command(idea_id, version=7))

    assert receipt.outcome == "rejected"
    assert receipt.rejection and receipt.rejection.code == "version-conflict"
    assert receipt.rejection.current_version == 0
    assert state.projects == {}


@pytest.mark.asyncio
async def test_creation_is_atomic_when_transaction_fails() -> None:
    state, idea_id = _state()
    state.fail_before_commit = True
    workflow = ContentWorkflow(state)

    with pytest.raises(RuntimeError, match="injected transaction failure"):
        await workflow.submit(_command(idea_id))

    assert state.ideas[idea_id].status == "proposed"
    assert state.ideas[idea_id].version == 0
    assert state.projects == {}
    assert state.pieces == {}
    assert state.obligations == {}
    assert state.receipts == {}


@pytest.mark.asyncio
async def test_desk_returns_an_operators_real_open_obligations_and_active_projects() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    receipt = await workflow.submit(_command(idea_id))
    project_id = str(receipt.result_refs["content_project_id"])

    # Query the same Mongo-backed state adapter used in production, not a hand-built projection.
    mongo_state = MongoWorkflowState(AsyncMongoMockClient()["workflow_desk"])
    await mongo_state._projects.insert_one(
        mongo_encode(state.projects[project_id].model_dump(by_alias=True))
    )
    obligation = next(iter(state.obligations.values()))
    await mongo_state._obligations.insert_one(mongo_encode(obligation.model_dump(by_alias=True)))
    desk = await ContentWorkflow(mongo_state).desk(ACTOR.email)

    assert [obligation.id for obligation in desk.open_obligations] == receipt.created_obligation_ids
    assert [(project.id, project.title) for project in desk.active_work] == [
        (project_id, "Evidence that compounds")
    ]
    assert desk.released_projects == []
    assert (await ContentWorkflow(mongo_state).desk("other@example.com")).active_work == []


@pytest.mark.asyncio
async def test_inspect_is_complete_operator_projection() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    receipt = await workflow.submit(_command(idea_id))

    view = await workflow.inspect(str(receipt.result_refs["content_project_id"]))

    assert view.derived_phase == ProjectPhase.building_evidence
    assert view.open_obligations[0].kind == HumanObligationKind.confirm_input_sufficiency
    assert view.piece_family[0].role == PieceRole.anchor
    assert view.piece_family[0].derived_phase == "input-building"
    assert [item.id for item in view.active_work] == [view.piece_family[0].id]
    assert view.consistency_warnings == []
    commands = {item.command_type: item for item in view.available_commands}
    assert commands[CommandKind.record_experiential_waiver].enabled is True
    assert commands[CommandKind.declare_input_sufficient].enabled is False
    assert commands[CommandKind.accept_final_revision].enabled is True
    assert commands[CommandKind.authorize_release].enabled is False


@pytest.mark.asyncio
async def test_commit_idea_creates_legacy_piece() -> None:
    """Verify that committing an idea creates a legacy Piece in the pieces collection."""
    mongo_client = AsyncMongoMockClient()
    mongo_state = MongoWorkflowState(mongo_client["test_db"])
    
    # Set up a spike in Mongo
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
    command = _command(idea_id)
    
    receipt = await workflow.submit(command)
    
    assert receipt.outcome == "applied"
    project_id = str(receipt.result_refs["content_project_id"])
    
    # Verify legacy Piece was created
    legacy_piece_doc = await mongo_client["test_db"]["pieces"].find_one({"content_project_id": project_id})
    assert legacy_piece_doc is not None
    assert legacy_piece_doc["role"] == "anchor"
    assert legacy_piece_doc["slug"] == command.payload.anchor_slug
    assert legacy_piece_doc["voice"] == command.payload.default_voice_id
    assert legacy_piece_doc["title"] == command.payload.anchor_title
    assert legacy_piece_doc["content_project_id"] == project_id


# --- research report + experiential waiver (research-v1 policy) -----------------------------


def _waiver_command(
    project_id: str, version: int, *, key: str = "waiver-1", actor: ActorRef = ACTOR
) -> CommandEnvelope:
    from app.content_workflow.models import RecordExperientialWaiverPayload

    return CommandEnvelope(
        command_type=CommandKind.record_experiential_waiver,
        aggregate=AggregateRef(kind="content-project", id=project_id),
        actor=actor,
        idempotency_key=key,
        expected_version=version,
        payload=RecordExperientialWaiverPayload(
            content_project_id=project_id,
            reason="I ran this exact migration for three customers last year.",
            experience_basis="Hands-on delivery experience with the subject matter.",
        ),
    )


async def _committed(workflow: ContentWorkflow, idea_id: str) -> tuple[str, int]:
    receipt = await workflow.submit(_command(idea_id))
    assert receipt.outcome == "applied"
    return str(receipt.result_refs["content_project_id"]), receipt.version_after or 1


@pytest.mark.asyncio
async def test_waiver_records_actor_and_reason_and_bumps_version() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    project_id, version = await _committed(workflow, idea_id)

    receipt = await workflow.submit(_waiver_command(project_id, version))

    assert receipt.outcome == "applied"
    assert receipt.command_type == CommandKind.record_experiential_waiver
    assert receipt.version_before == version
    assert receipt.version_after == version + 1
    assert receipt.result_refs["content_project_id"] == project_id
    waiver = state.waivers[0]
    assert waiver.content_project_id == project_id
    assert waiver.actor == ACTOR
    assert waiver.reason.startswith("I ran this exact migration")
    assert state.projects[project_id].version == version + 1


@pytest.mark.asyncio
async def test_waiver_is_idempotent_on_replay() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    project_id, version = await _committed(workflow, idea_id)
    command = _waiver_command(project_id, version)

    first = await workflow.submit(command)
    second = await workflow.submit(command)

    assert second == first
    assert len(state.waivers) == 1


@pytest.mark.asyncio
async def test_waiver_for_unknown_project_is_rejected() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    await _committed(workflow, idea_id)

    receipt = await workflow.submit(_waiver_command("missing-project", 1))

    assert receipt.outcome == "rejected"
    assert receipt.rejection and receipt.rejection.code == "project-not-found"
    assert state.waivers == []


@pytest.mark.asyncio
async def test_waiver_version_conflict_is_rejected() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    project_id, version = await _committed(workflow, idea_id)

    receipt = await workflow.submit(_waiver_command(project_id, version + 5))

    assert receipt.outcome == "rejected"
    assert receipt.rejection and receipt.rejection.code == "version-conflict"
    assert receipt.rejection.current_version == version
    assert state.waivers == []


@pytest.mark.asyncio
async def test_research_report_supersedes_the_current_one() -> None:
    from app.content_workflow.models import ReportFact

    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    project_id, _ = await _committed(workflow, idea_id)

    first = await workflow.submit_research_report(
        project_id,
        _report(project_id, subject="first pass"),
    )
    second = await workflow.submit_research_report(
        project_id,
        _report(project_id, subject="second pass"),
    )

    current = await workflow.research_gate(project_id)
    assert current.report is not None
    assert current.report.subject == "second pass"
    assert current.report.id == second.id
    # The report is anchored to the project's anchor Piece when the caller names no piece.
    anchor = next(p for p in state.pieces.values() if p.role == PieceRole.anchor)
    assert second.piece_id == anchor.id
    # history is kept, marked superseded — never overwritten
    assert first.status == "superseded"
    assert len(state.research_reports) == 2


def _report(project_id: str, *, subject: str = "Token vs storage economics"):
    from app.content_workflow.models import ReportFact, ReportOpinion, ResearchReport

    return ResearchReport(
        id=new_id(),
        content_project_id=project_id,
        subject=subject,
        facts=[
            ReportFact(
                statement="Inference workloads grew 3x faster than training workloads in 2025.",
                source="Internal benchmark survey, Q4 2025",
            )
        ],
        opinions=[ReportOpinion(statement="This shift favors storage-tiering pitches.", holder=ACTOR.email)],
        open_questions=["Which customer segment feels the storage cost first?"],
        submitted_by=ACTOR,
        created_at=utcnow(),
        updated_at=utcnow(),
    )


@pytest.mark.asyncio
async def test_research_gate_required_by_default_and_satisfied_by_report_or_waiver() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    project_id, version = await _committed(workflow, idea_id)

    gate = await workflow.research_gate(project_id)
    assert gate.required is True
    assert gate.satisfied is False
    assert gate.satisfied_by is None

    await workflow.submit(_waiver_command(project_id, version))
    gate = await workflow.research_gate(project_id)
    assert gate.satisfied is True
    assert gate.satisfied_by == "experiential-waiver"
    assert gate.waiver is not None and gate.waiver.actor == ACTOR

    await workflow.submit_research_report(project_id, _report(project_id))
    gate = await workflow.research_gate(project_id)
    assert gate.satisfied is True
    assert gate.satisfied_by == "research-report"
    assert gate.report is not None


@pytest.mark.asyncio
async def test_research_report_for_unknown_project_raises() -> None:
    import pytest as _pytest

    from app.content_workflow.workflow import ProjectNotFound

    state, _ = _state()
    workflow = ContentWorkflow(state)
    with _pytest.raises(ProjectNotFound):
        await workflow.submit_research_report("missing", _report("missing"))


@pytest.mark.asyncio
async def test_report_without_a_sourced_fact_is_rejected() -> None:
    import pytest as _pytest

    from app.content_workflow.models import ResearchReport

    with _pytest.raises(ValueError, match="at least one sourced fact"):
        ResearchReport(
            content_project_id="p",
            subject="s",
            facts=[],
            submitted_by=ACTOR,
        )


@pytest.mark.asyncio
async def test_inspect_reflects_the_research_gate() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    project_id, version = await _committed(workflow, idea_id)

    view = await workflow.inspect(project_id)
    commands = {item.command_type: item for item in view.available_commands}
    assert commands[CommandKind.declare_input_sufficient].enabled is False
    assert view.research is not None
    assert view.research.required is True and view.research.satisfied is False
    assert view.artifact_readiness["research-report"] == "absent"
    assert view.piece_family[0].artifact_readiness["research-report"] == "absent"

    await workflow.submit_research_report(project_id, _report(project_id))
    view = await workflow.inspect(project_id)
    commands = {item.command_type: item for item in view.available_commands}
    assert commands[CommandKind.declare_input_sufficient].enabled is True
    assert view.research.satisfied is True
    assert view.research.satisfied_by == "research-report"
    assert view.artifact_readiness["research-report"] == "cleared"
    assert view.piece_family[0].artifact_readiness["research-report"] == "cleared"

    # A waiver-only project is satisfied too, and the projection says so honestly.
    state2, idea_id2 = _state()
    workflow2 = ContentWorkflow(state2)
    project_id2, version2 = await _committed(workflow2, idea_id2)
    await workflow2.submit(_waiver_command(project_id2, version2))
    view2 = await workflow2.inspect(project_id2)
    assert view2.research.satisfied_by == "experiential-waiver"
    assert view2.artifact_readiness["research-report"] == "approved"
    commands2 = {item.command_type: item for item in view2.available_commands}
    assert commands2[CommandKind.declare_input_sufficient].enabled is True


# --- authority model (cmw-authority-model-impl) -------------------------------------------

OTHER_ACTOR = ActorRef(subject_id="other@example.com", email="other@example.com")


def _command_with_direction_assignee(
    idea_id: str,
    direction_assignee: ActorRef,
    actor: ActorRef,
    *,
    key: str = "commit-auth",
    version: int = 0,
) -> CommandEnvelope:
    """Commit-idea payload with a specific direction authority, issued by ``actor``."""
    return CommandEnvelope(
        command_type=CommandKind.commit_idea,
        aggregate=AggregateRef(kind="idea", id=idea_id),
        actor=actor,
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
                AuthorityInput(kind=AuthorityKind.direction, assignee=direction_assignee),
                AuthorityInput(kind=AuthorityKind.input_sufficiency, assignee=actor),
                AuthorityInput(kind=AuthorityKind.voice, assignee=actor),
                AuthorityInput(kind=AuthorityKind.release, assignee=actor),
            ],
            anchor_title="Evidence that compounds",
            anchor_slug="evidence-that-compounds",
            anchor_destination="blog",
        ),
    )


def _declare_input_sufficient_command(
    project_id: str, version: int, actor: ActorRef, *, key: str = "declare-1"
) -> CommandEnvelope:
    from app.content_workflow.models import DeclareInputSufficientPayload

    return CommandEnvelope(
        command_type=CommandKind.declare_input_sufficient,
        aggregate=AggregateRef(kind="content-project", id=project_id),
        actor=actor,
        idempotency_key=key,
        expected_version=version,
        payload=DeclareInputSufficientPayload(
            content_project_id=project_id,
            reason="Research gate is satisfied.",
        ),
    )


def _quality_waiver_command(
    project_id: str, version: int, actor: ActorRef, *, key: str = "quality-1"
) -> CommandEnvelope:
    from app.content_workflow.models import RecordQualityWaiverPayload

    return CommandEnvelope(
        command_type=CommandKind.record_quality_waiver,
        aggregate=AggregateRef(kind="content-project", id=project_id),
        actor=actor,
        idempotency_key=key,
        expected_version=version,
        payload=RecordQualityWaiverPayload(
            content_project_id=project_id,
            reason="Customer needs a tighter loop.",
            quality_bar=6.5,
            iteration_ceiling=2,
        ),
    )


def _accept_command(
    project_id: str,
    piece_id: str,
    version: int,
    actor: ActorRef,
    *,
    key: str = "accept-1",
) -> CommandEnvelope:
    from app.content_workflow.models import AcceptFinalRevisionPayload

    return CommandEnvelope(
        command_type=CommandKind.accept_final_revision,
        aggregate=AggregateRef(kind="content-project", id=project_id),
        actor=actor,
        idempotency_key=key,
        expected_version=version,
        payload=AcceptFinalRevisionPayload(
            type="accept-final-revision",
            content_project_id=project_id,
            piece_id=piece_id,
            revision="rev-1",
        ),
    )


def _authorize_command(
    project_id: str, piece_id: str, version: int, actor: ActorRef
) -> CommandEnvelope:
    from app.content_workflow.models import AuthorizeReleasePayload

    return CommandEnvelope(
        command_type=CommandKind.authorize_release,
        aggregate=AggregateRef(kind="content-project", id=project_id),
        actor=actor,
        idempotency_key="authz-1",
        expected_version=version,
        payload=AuthorizeReleasePayload(
            type="authorize-release",
            content_project_id=project_id,
            piece_id=piece_id,
        ),
    )


def _trivial_waiver_command(
    project_id: str, piece_id: str, version: int, actor: ActorRef
) -> CommandEnvelope:
    from app.content_workflow.models import RecordTrivialEditWaiverPayload

    return CommandEnvelope(
        command_type=CommandKind.record_trivial_edit_waiver,
        aggregate=AggregateRef(kind="content-project", id=project_id),
        actor=actor,
        idempotency_key="trivial-1",
        expected_version=version,
        payload=RecordTrivialEditWaiverPayload(
            type="record-trivial-edit-waiver",
            content_project_id=project_id,
            piece_id=piece_id,
            from_revision="rev-1",
            to_revision="rev-2",
            reason="Typo fix.",
        ),
    )


@pytest.mark.asyncio
async def test_commit_idea_rejects_actor_who_is_not_direction_authority() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    command = _command_with_direction_assignee(idea_id, ACTOR, OTHER_ACTOR)

    receipt = await workflow.submit(command)

    assert receipt.outcome == "rejected"
    assert receipt.rejection and receipt.rejection.code == "authority-required"
    assert state.ideas[idea_id].status == "proposed"
    assert state.projects == {}


@pytest.mark.asyncio
async def test_record_experiential_waiver_rejects_actor_without_direction_authority() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    project_id, version = await _committed(workflow, idea_id)
    command = _waiver_command(project_id, version, actor=OTHER_ACTOR)

    receipt = await workflow.submit(command)

    assert receipt.outcome == "rejected"
    assert receipt.rejection and receipt.rejection.code == "authority-required"
    assert state.waivers == []


@pytest.mark.asyncio
async def test_declare_input_sufficient_resolves_obligation_when_authorized() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    project_id, version = await _committed(workflow, idea_id)
    await workflow.submit_research_report(project_id, _report(project_id))

    receipt = await workflow.submit(_declare_input_sufficient_command(project_id, version, ACTOR))

    assert receipt.outcome == "applied"
    assert receipt.result_refs["content_project_id"] == project_id
    obligation = next(iter(state.obligations.values()))
    assert obligation.state == "resolved"
    assert obligation.resolution is not None
    view = await workflow.inspect(project_id)
    assert view.open_obligations == []
    assert view.derived_phase == ProjectPhase.producing


@pytest.mark.asyncio
async def test_declare_input_sufficient_rejects_actor_without_input_sufficiency_authority() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    project_id, version = await _committed(workflow, idea_id)
    await workflow.submit_research_report(project_id, _report(project_id))
    command = _declare_input_sufficient_command(project_id, version, OTHER_ACTOR)

    receipt = await workflow.submit(command)

    assert receipt.outcome == "rejected"
    assert receipt.rejection and receipt.rejection.code == "authority-required"
    obligation = next(iter(state.obligations.values()))
    assert obligation.state == "open"


@pytest.mark.asyncio
async def test_release_commands_reject_actor_without_release_authority() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    receipt = await workflow.submit(_command(idea_id))
    project_id = str(receipt.result_refs["content_project_id"])
    piece_id = str(receipt.result_refs["anchor_piece_id"])
    version = receipt.version_after or 1
    # Accept the revision first so authorize_release passes its non-authority checks.
    accept_receipt = await workflow.submit(
        _accept_command(project_id, piece_id, version, ACTOR, key="accept-ok")
    )
    version = accept_receipt.version_after or version + 1

    for idx, command in enumerate(
        (
            _accept_command(project_id, piece_id, version, OTHER_ACTOR, key="accept-bad"),
            _authorize_command(project_id, piece_id, version, OTHER_ACTOR),
            _trivial_waiver_command(project_id, piece_id, version, OTHER_ACTOR),
        )
    ):
        receipt = await workflow.submit(command)
        assert receipt.outcome == "rejected", command.command_type
        assert receipt.rejection and receipt.rejection.code == "authority-required", command.command_type


@pytest.mark.asyncio
async def test_record_quality_waiver_records_override_and_surfaces_in_inspect() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    project_id, version = await _committed(workflow, idea_id)

    receipt = await workflow.submit(_quality_waiver_command(project_id, version, ACTOR))

    assert receipt.outcome == "applied"
    waiver = state.quality_waivers[0]
    assert waiver.content_project_id == project_id
    assert waiver.quality_bar == 6.5
    assert waiver.iteration_ceiling == 2
    assert waiver.actor == ACTOR
    view = await workflow.inspect(project_id)
    assert view.quality_waiver is not None
    assert view.quality_waiver.quality_bar == 6.5
    assert view.quality_waiver.iteration_ceiling == 2


@pytest.mark.asyncio
async def test_record_quality_waiver_rejects_actor_without_direction_authority() -> None:
    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    project_id, version = await _committed(workflow, idea_id)
    command = _quality_waiver_command(project_id, version, OTHER_ACTOR)

    receipt = await workflow.submit(command)

    assert receipt.outcome == "rejected"
    assert receipt.rejection and receipt.rejection.code == "authority-required"
    assert state.quality_waivers == []


@pytest.mark.asyncio
async def test_record_quality_waiver_rejects_empty_override() -> None:
    import pytest as _pytest
    from pydantic import ValidationError

    from app.content_workflow.models import RecordQualityWaiverPayload

    state, idea_id = _state()
    workflow = ContentWorkflow(state)
    project_id, version = await _committed(workflow, idea_id)

    with _pytest.raises(ValidationError, match="must override at least one"):
        RecordQualityWaiverPayload(
            content_project_id=project_id,
            reason="No override values.",
        )
