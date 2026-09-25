"""Deep workflow interface: typed commands in, operator projection out."""

from __future__ import annotations

import hashlib
import json

from app import repositories
from app.content_workflow.models import (
    AcceptFinalRevisionPayload,
    ActorRef,
    ArtifactReadiness,
    AuthorityAssignment,
    AuthorityInput,
    AuthorityKind,
    AuthorizeReleasePayload,
    AvailableCommand,
    CommandEnvelope,
    CommandKind,
    CommandReceipt,
    ContentProject,
    CouncilPolicy,
    DeclareInputSufficientPayload,
    DeskProjection,
    Disposition,
    ExperientialWaiver,
    HumanObligation,
    HumanObligationKind,
    HumanObligationState,
    ObligationResolution,
    ObligationSubject,
    PiecePhase,
    PieceRole,
    PieceWorkspaceItem,
    ProjectPhase,
    ProjectPiece,
    ProjectWorkspaceView,
    PublicationReleaseOut,
    QualityWaiver,
    RecordExperientialWaiverPayload,
    RecordQualityWaiverPayload,
    RecordTrivialEditWaiverPayload,
    Rejection,
    ReleaseGateView,
    ResearchGateView,
    ResearchPolicy,
    ResearchReport,
    Suspension,
    Visibility,
)
from app.content_workflow.store import WorkflowConflict, WorkflowState
from app.models.common import new_id, utcnow
from app.models.piece import PieceStage, is_released_stage
from app.models.publication import PublicationRelease, ReleaseActor, TrivialEditWaiver
from app.release.approval import approval_status


class ProjectNotFound(KeyError):
    pass


class ProjectNotActive(ValueError):
    def __init__(self, project_id: str, disposition: object) -> None:
        super().__init__(
            f"project {project_id!r} is {disposition!r}; only active projects accept research input"
        )
        self.project_id = project_id
        self.disposition = disposition


def _actor_has_authority(
    actor: ActorRef, project: ContentProject, kind: AuthorityKind
) -> bool:
    normalized_subject = (actor.subject_id or "").lower()
    normalized_email = (actor.email or "").lower()
    for assignment in project.authorities:
        if assignment.kind != kind:
            continue
        assignee = assignment.assignee
        if (assignee.subject_id or "").lower() == normalized_subject:
            return True
        if (assignee.email or "").lower() == normalized_email:
            return True
    return False


def _actor_matches_authority_input(actor: ActorRef, authority: AuthorityInput) -> bool:
    normalized_subject = (actor.subject_id or "").lower()
    normalized_email = (actor.email or "").lower()
    assignee = authority.assignee
    return (
        (assignee.subject_id or "").lower() == normalized_subject
        or (assignee.email or "").lower() == normalized_email
    )


class ContentWorkflow:
    def __init__(self, state: WorkflowState) -> None:
        self._state = state

    @property
    def state(self) -> WorkflowState:
        return self._state

    async def submit(self, command: CommandEnvelope) -> CommandReceipt:
        digest = _command_digest(command)
        prior = await self._state.receipt_for(command.idempotency_key)
        if prior is not None:
            if prior.payload_digest == digest:
                return prior
            return _rejected_receipt(
                command,
                digest,
                code="idempotency-key-reused",
                message="idempotency key was already used for a different command payload",
            )

        if command.command_type != CommandKind.commit_idea:
            if command.command_type == CommandKind.record_experiential_waiver:
                return await self._record_experiential_waiver(command, digest)
            if command.command_type == CommandKind.declare_input_sufficient:
                return await self._declare_input_sufficient(command, digest)
            if command.command_type == CommandKind.accept_final_revision:
                return await self._accept_final_revision(command, digest)
            if command.command_type == CommandKind.authorize_release:
                return await self._authorize_release(command, digest)
            if command.command_type == CommandKind.record_trivial_edit_waiver:
                return await self._record_trivial_edit_waiver(command, digest)
            if command.command_type == CommandKind.record_quality_waiver:
                return await self._record_quality_waiver(command, digest)
            if command.command_type == CommandKind.commission_derivative:
                return _rejected_receipt(
                    command,
                    digest,
                    code="not-implemented",
                    message="commissioning derivatives is not implemented yet",
                )
            return _rejected_receipt(
                command,
                digest,
                code="unsupported-command",
                message=f"{command.command_type.value} is not implemented yet",
            )

        now = utcnow()
        project_id = new_id()
        piece_id = new_id()
        evidence_base_id = new_id()
        assignments = [
            AuthorityAssignment(
                kind=item.kind,
                assignee=item.assignee,
                scope=item.scope,
                assigned_by=command.actor,
                assigned_at=now,
            )
            for item in command.payload.authorities
        ]
        direction_authority = next(
            (item for item in command.payload.authorities if item.kind == AuthorityKind.direction),
            None,
        )
        if direction_authority is None or not _actor_matches_authority_input(
            command.actor, direction_authority
        ):
            return _rejected_receipt(
                command,
                digest,
                code="authority-required",
                message="committing an idea requires the actor to be assigned the direction authority",
            )
        project = ContentProject(
            id=project_id,
            title=command.payload.project_title,
            originating_idea_id=command.aggregate.id,
            purpose_brief=command.payload.purpose_brief,
            authorities=assignments,
            default_voice_id=command.payload.default_voice_id,
            evidence_base_id=evidence_base_id,
            council_policy=command.payload.council_policy,
            research_policy=ResearchPolicy(),
            created_at=now,
            updated_at=now,
        )
        piece = ProjectPiece(
            id=piece_id,
            content_project_id=project_id,
            role=PieceRole.anchor,
            title=command.payload.anchor_title,
            slug=command.payload.anchor_slug,
            voice_id=command.payload.default_voice_id,
            destination=command.payload.anchor_destination,
            created_at=now,
            updated_at=now,
        )
        input_authority = next(
            assignment
            for assignment in assignments
            if assignment.kind == AuthorityKind.input_sufficiency
        )
        obligation = HumanObligation(
            id=new_id(),
            content_project_id=project_id,
            kind=HumanObligationKind.confirm_input_sufficiency,
            assignee=input_authority.assignee,
            authority=AuthorityKind.input_sufficiency,
            subject=ObligationSubject(kind="evidence-base", id=evidence_base_id),
            created_at=now,
            updated_at=now,
        )
        receipt = CommandReceipt(
            id=new_id(),
            command_type=command.command_type,
            aggregate=command.aggregate,
            actor=command.actor,
            idempotency_key=command.idempotency_key,
            payload_digest=digest,
            outcome="applied",
            version_before=command.expected_version,
            version_after=command.expected_version + 1,
            applied_at=now,
            result_refs={
                "idea_id": command.aggregate.id,
                "content_project_id": project_id,
                "anchor_piece_id": piece_id,
                "evidence_base_id": evidence_base_id,
                "authority_kinds": [item.kind.value for item in assignments],
            },
            created_obligation_ids=[obligation.id],
            created_at=now,
            updated_at=now,
        )
        try:
            return await self._state.commit_idea(command, project, piece, [obligation], receipt)
        except WorkflowConflict as exc:
            return _rejected_receipt(
                command,
                digest,
                code=exc.code,
                message=str(exc),
                current_version=exc.current_version,
            )

    async def _record_experiential_waiver(
        self, command: CommandEnvelope, digest: str
    ) -> CommandReceipt:
        """The recorded waiver path (research-v1): an operator with subject-matter experience
        skips the research report. Never silent — the waiver record carries actor + reason."""
        assert isinstance(command.payload, RecordExperientialWaiverPayload)
        payload = command.payload
        now = utcnow()

        project = await self._state.load_project(payload.content_project_id)
        if project is None:
            return _rejected_receipt(
                command,
                digest,
                code="project-not-found",
                message=f"no content project with id {payload.content_project_id!r}",
            )
        if project.version != command.expected_version:
            return _rejected_receipt(
                command,
                digest,
                code="version-conflict",
                message="the project changed after it was inspected",
                current_version=project.version,
            )
        if project.disposition != Disposition.active:
            return _rejected_receipt(
                command,
                digest,
                code="project-not-active",
                message=f"project is {project.disposition!r}; a waiver only applies to active work",
                current_version=project.version,
            )
        if not project.research_policy.experiential_waiver_allowed:
            return _rejected_receipt(
                command,
                digest,
                code="waiver-not-allowed",
                message="this project's research policy does not allow experiential waivers",
                current_version=project.version,
            )
        if not _actor_has_authority(command.actor, project, AuthorityKind.direction):
            return _rejected_receipt(
                command,
                digest,
                code="authority-required",
                message=f"{command.command_type.value} requires direction authority",
                current_version=project.version,
            )

        waiver = ExperientialWaiver(
            id=new_id(),
            content_project_id=project.id,
            actor=command.actor,
            reason=payload.reason,
            experience_basis=payload.experience_basis,
            recorded_at=now,
            created_at=now,
            updated_at=now,
        )
        receipt = CommandReceipt(
            id=new_id(),
            command_type=command.command_type,
            aggregate=command.aggregate,
            actor=command.actor,
            idempotency_key=command.idempotency_key,
            payload_digest=digest,
            outcome="applied",
            version_before=project.version,
            version_after=project.version + 1,
            applied_at=now,
            result_refs={
                "content_project_id": project.id,
                "waiver_id": waiver.id,
            },
            created_at=now,
            updated_at=now,
        )
        try:
            await self._state.record_waiver(waiver)
        except WorkflowConflict as exc:
            return _rejected_receipt(
                command,
                digest,
                code=exc.code,
                message=str(exc),
                current_version=exc.current_version,
            )
        await self._state.save_receipt(receipt)
        return receipt

    async def _declare_input_sufficient(
        self, command: CommandEnvelope, digest: str
    ) -> CommandReceipt:
        """Resolve the confirm-input-sufficiency obligation once the research gate is clear."""
        assert isinstance(command.payload, DeclareInputSufficientPayload)
        payload = command.payload
        rejected = await self._require_active_project(command, digest, payload.content_project_id)
        if rejected is not None:
            return rejected
        project = await self._state.load_project(payload.content_project_id)
        assert project is not None
        if not _actor_has_authority(command.actor, project, AuthorityKind.input_sufficiency):
            return _rejected_receipt(
                command,
                digest,
                code="authority-required",
                message=f"{command.command_type.value} requires input-sufficiency authority",
                current_version=project.version,
            )
        workspace = await self._state.load_workspace(project.id)
        assert workspace is not None
        _, _, obligations = workspace
        obligation = next(
            (
                item
                for item in obligations
                if item.kind == HumanObligationKind.confirm_input_sufficiency
                and item.state == HumanObligationState.open
            ),
            None,
        )
        if obligation is None:
            return _rejected_receipt(
                command,
                digest,
                code="obligation-not-found",
                message="no open input-sufficiency obligation to resolve",
                current_version=project.version,
            )
        now = utcnow()
        resolution = ObligationResolution(
            actor=command.actor,
            decision="input-sufficient",
            rationale=payload.reason,
            resolved_at=now,
        )
        resolved = await self._state.resolve_obligation(obligation.id, resolution)
        if resolved is None:
            return _rejected_receipt(
                command,
                digest,
                code="obligation-not-found",
                message="the input-sufficiency obligation was already resolved",
                current_version=project.version,
            )
        receipt = CommandReceipt(
            id=new_id(),
            command_type=command.command_type,
            aggregate=command.aggregate,
            actor=command.actor,
            idempotency_key=command.idempotency_key,
            payload_digest=digest,
            outcome="applied",
            version_before=project.version,
            version_after=project.version + 1,
            applied_at=now,
            result_refs={
                "content_project_id": project.id,
                "obligation_id": obligation.id,
            },
            created_at=now,
            updated_at=now,
        )
        await self._state.bump_project_version(project.id)
        await self._state.save_receipt(receipt)
        return receipt

    async def _record_quality_waiver(
        self, command: CommandEnvelope, digest: str
    ) -> CommandReceipt:
        """Record a council-policy override (quality bar, iteration ceiling, cost ceiling)."""
        assert isinstance(command.payload, RecordQualityWaiverPayload)
        payload = command.payload
        rejected = await self._require_active_project(command, digest, payload.content_project_id)
        if rejected is not None:
            return rejected
        project = await self._state.load_project(payload.content_project_id)
        assert project is not None
        if not _actor_has_authority(command.actor, project, AuthorityKind.direction):
            return _rejected_receipt(
                command,
                digest,
                code="authority-required",
                message=f"{command.command_type.value} requires direction authority",
                current_version=project.version,
            )
        now = utcnow()
        waiver = QualityWaiver(
            id=new_id(),
            content_project_id=project.id,
            actor=command.actor,
            reason=payload.reason,
            policy_version=payload.policy_version,
            quality_bar=payload.quality_bar,
            iteration_ceiling=payload.iteration_ceiling,
            cost_ceiling_usd=payload.cost_ceiling_usd,
            recorded_at=now,
            created_at=now,
            updated_at=now,
        )
        try:
            await self._state.record_quality_waiver(waiver)
        except WorkflowConflict as exc:
            return _rejected_receipt(
                command,
                digest,
                code=exc.code,
                message=str(exc),
                current_version=exc.current_version,
            )
        receipt = CommandReceipt(
            id=new_id(),
            command_type=command.command_type,
            aggregate=command.aggregate,
            actor=command.actor,
            idempotency_key=command.idempotency_key,
            payload_digest=digest,
            outcome="applied",
            version_before=project.version,
            version_after=project.version + 1,
            applied_at=now,
            result_refs={
                "content_project_id": project.id,
                "waiver_id": waiver.id,
            },
            created_at=now,
            updated_at=now,
        )
        await self._state.save_receipt(receipt)
        return receipt

    async def _accept_final_revision(
        self, command: CommandEnvelope, digest: str
    ) -> CommandReceipt:
        """Stamp the named revision as the accepted candidate (and as council re-approval after
        a substantive final-pass edit invalidated the prior approval)."""
        assert isinstance(command.payload, AcceptFinalRevisionPayload)
        payload = command.payload
        rejected = await self._require_active_project(command, digest, payload.content_project_id)
        if rejected is not None:
            return rejected
        project = await self._state.load_project(payload.content_project_id)
        assert project is not None
        if not _actor_has_authority(command.actor, project, AuthorityKind.release):
            return _rejected_receipt(
                command,
                digest,
                code="authority-required",
                message=f"{command.command_type.value} requires release authority",
                current_version=project.version,
            )
        piece = await self._state.load_legacy_piece(payload.piece_id)
        if piece is None or piece.content_project_id != project.id:
            return _rejected_receipt(
                command,
                digest,
                code="piece-not-found",
                message=f"no piece {payload.piece_id!r} on this project",
                current_version=project.version,
            )
        now = utcnow()
        await self._state.stamp_approval(payload.piece_id, payload.revision)
        receipt = CommandReceipt(
            id=new_id(),
            command_type=command.command_type,
            aggregate=command.aggregate,
            actor=command.actor,
            idempotency_key=command.idempotency_key,
            payload_digest=digest,
            outcome="applied",
            version_before=project.version,
            version_after=project.version + 1,
            applied_at=now,
            result_refs={
                "content_project_id": project.id,
                "piece_id": payload.piece_id,
                "accepted_revision": payload.revision,
            },
            created_at=now,
            updated_at=now,
        )
        await self._state.bump_project_version(project.id)
        await self._state.save_receipt(receipt)
        return receipt

    async def _authorize_release(
        self, command: CommandEnvelope, digest: str
    ) -> CommandReceipt:
        """Explicit human AuthorizeRelease: mint an immutable numbered Publication Release.

        The machine never calls this. The workspace stays active (disposition unchanged).
        Authority-model (queued) will gate the actor; this records them and creates the release.
        """
        assert isinstance(command.payload, AuthorizeReleasePayload)
        payload = command.payload
        rejected = await self._require_active_project(command, digest, payload.content_project_id)
        if rejected is not None:
            return rejected
        project = await self._state.load_project(payload.content_project_id)
        assert project is not None
        if not _actor_has_authority(command.actor, project, AuthorityKind.release):
            return _rejected_receipt(
                command,
                digest,
                code="authority-required",
                message=f"{command.command_type.value} requires release authority",
                current_version=project.version,
            )
        piece = await self._state.load_legacy_piece(payload.piece_id)
        if piece is None or piece.content_project_id != project.id:
            return _rejected_receipt(
                command,
                digest,
                code="piece-not-found",
                message=f"no piece {payload.piece_id!r} on this project",
                current_version=project.version,
            )
        waivers = await self._state.list_trivial_edit_waivers(payload.piece_id)
        status = approval_status(
            approved_revision=piece.approved_revision,
            latest_revision=piece.latest_revision,
            waivers=waivers,
        )
        if not status.valid:
            return _rejected_receipt(
                command,
                digest,
                code="approval-invalidated" if status.invalidated else "accepted-candidate-required",
                message=status.reason,
                current_version=project.version,
            )
        assert piece.latest_revision is not None
        existing = await self._state.list_publication_releases(payload.piece_id)
        release_number = (existing[-1].release_number + 1) if existing else 1
        now = utcnow()
        release = PublicationRelease(
            id=new_id(),
            piece_id=payload.piece_id,
            content_project_id=project.id,
            release_number=release_number,
            revision=piece.latest_revision,
            authorized_by=ReleaseActor(
                subject_id=command.actor.subject_id,
                email=command.actor.email,
                display_name=command.actor.display_name,
            ),
            authorized_at=now,
            created_at=now,
            updated_at=now,
        )
        await self._state.insert_publication_release(release)
        # First authorization enters the terminal Released stage; subsequent ones stay there.
        # Never flips project.disposition — the workspace is not terminal after release.
        if not is_released_stage(piece.stage):
            await self._state.set_legacy_stage(payload.piece_id, PieceStage.released)
        receipt = CommandReceipt(
            id=new_id(),
            command_type=command.command_type,
            aggregate=command.aggregate,
            actor=command.actor,
            idempotency_key=command.idempotency_key,
            payload_digest=digest,
            outcome="applied",
            version_before=project.version,
            version_after=project.version + 1,
            applied_at=now,
            result_refs={
                "content_project_id": project.id,
                "piece_id": payload.piece_id,
                "release_id": release.id,
                "release_number": release_number,
                "revision": piece.latest_revision,
            },
            created_at=now,
            updated_at=now,
        )
        await self._state.bump_project_version(project.id)
        await self._state.save_receipt(receipt)
        return receipt

    async def _record_trivial_edit_waiver(
        self, command: CommandEnvelope, digest: str
    ) -> CommandReceipt:
        """Recorded path for a trivial final-pass edit: keeps the prior approval valid."""
        assert isinstance(command.payload, RecordTrivialEditWaiverPayload)
        payload = command.payload
        rejected = await self._require_active_project(command, digest, payload.content_project_id)
        if rejected is not None:
            return rejected
        project = await self._state.load_project(payload.content_project_id)
        assert project is not None
        if not _actor_has_authority(command.actor, project, AuthorityKind.release):
            return _rejected_receipt(
                command,
                digest,
                code="authority-required",
                message=f"{command.command_type.value} requires release authority",
                current_version=project.version,
            )
        piece = await self._state.load_legacy_piece(payload.piece_id)
        if piece is None or piece.content_project_id != project.id:
            return _rejected_receipt(
                command,
                digest,
                code="piece-not-found",
                message=f"no piece {payload.piece_id!r} on this project",
                current_version=project.version,
            )
        now = utcnow()
        waiver = TrivialEditWaiver(
            id=new_id(),
            piece_id=payload.piece_id,
            content_project_id=project.id,
            from_revision=payload.from_revision,
            to_revision=payload.to_revision,
            actor=ReleaseActor(
                subject_id=command.actor.subject_id,
                email=command.actor.email,
                display_name=command.actor.display_name,
            ),
            reason=payload.reason,
            recorded_at=now,
            created_at=now,
            updated_at=now,
        )
        await self._state.insert_trivial_edit_waiver(waiver)
        receipt = CommandReceipt(
            id=new_id(),
            command_type=command.command_type,
            aggregate=command.aggregate,
            actor=command.actor,
            idempotency_key=command.idempotency_key,
            payload_digest=digest,
            outcome="applied",
            version_before=project.version,
            version_after=project.version + 1,
            applied_at=now,
            result_refs={
                "content_project_id": project.id,
                "piece_id": payload.piece_id,
                "waiver_id": waiver.id,
            },
            created_at=now,
            updated_at=now,
        )
        await self._state.bump_project_version(project.id)
        await self._state.save_receipt(receipt)
        return receipt

    async def _require_active_project(
        self, command: CommandEnvelope, digest: str, project_id: str
    ) -> CommandReceipt | None:
        project = await self._state.load_project(project_id)
        if project is None:
            return _rejected_receipt(
                command,
                digest,
                code="project-not-found",
                message=f"no content project with id {project_id!r}",
            )
        if project.version != command.expected_version:
            return _rejected_receipt(
                command,
                digest,
                code="version-conflict",
                message="the project changed after it was inspected",
                current_version=project.version,
            )
        if project.disposition != Disposition.active:
            return _rejected_receipt(
                command,
                digest,
                code="project-not-active",
                message=f"project is {project.disposition!r}; only active projects accept this command",
                current_version=project.version,
            )
        return None

    async def submit_research_report(
        self,
        project_id: str,
        report: ResearchReport,
    ) -> ResearchReport:
        """Record the first-class research-report artifact for a project (research-v1).

        A new report supersedes the current one; history is kept, never overwritten. When the
        caller doesn't name a piece, the report is anchored on the project's anchor Piece —
        it is a report ON the piece, not floating metadata.
        """
        project = await self._state.load_project(project_id)
        if project is None:
            raise ProjectNotFound(project_id)
        if project.disposition != Disposition.active:
            raise ProjectNotActive(project_id, project.disposition)
        report.content_project_id = project_id
        if report.piece_id is None:
            loaded = await self._state.load_workspace(project_id)
            if loaded is not None:
                anchor = next(
                    (piece for piece in loaded[1] if piece.role == PieceRole.anchor), None
                )
                if anchor is not None:
                    report.piece_id = anchor.id
        return await self._state.submit_research_report(report)

    async def research_gate(self, project_id: str) -> ResearchGateView:
        """The project's research requirement, projected: required by default, satisfied by a
        current report OR a recorded experiential waiver."""
        project = await self._state.load_project(project_id)
        if project is None:
            raise ProjectNotFound(project_id)
        return await self._research_gate(project)

    async def _research_gate(self, project: ContentProject) -> ResearchGateView:
        assert project.id is not None
        report = await self._state.latest_research_report(project.id)
        waiver = await self._state.latest_waiver(project.id)
        satisfied = report is not None or waiver is not None
        return ResearchGateView(
            required=project.research_policy.report_required_by_default,
            satisfied=satisfied,
            satisfied_by=(
                "research-report"
                if report is not None
                else "experiential-waiver" if waiver is not None else None
            ),
            report=report,
            waiver=waiver,
        )

    async def _release_gate(self, piece_id: str | None) -> ReleaseGateView | None:
        if not piece_id:
            return None
        piece = await self._state.load_legacy_piece(piece_id)
        releases = await self._state.list_publication_releases(piece_id)
        waivers = await self._state.list_trivial_edit_waivers(piece_id)
        approved = piece.approved_revision if piece else None
        current = piece.latest_revision if piece else None
        status = approval_status(
            approved_revision=approved,
            latest_revision=current,
            waivers=waivers,
        )
        return ReleaseGateView(
            piece_id=piece_id,
            accepted_revision=status.approved_revision,
            current_revision=status.current_revision,
            approval_valid=status.valid,
            invalidated=status.invalidated,
            waiver_reason=status.waiver.reason if status.waiver else None,
            releases=[
                PublicationReleaseOut(
                    id=item.id,
                    piece_id=item.piece_id,
                    release_number=item.release_number,
                    revision=item.revision,
                    authorized_by_subject_id=item.authorized_by.subject_id,
                    authorized_at=item.authorized_at,
                    html_url=item.html_url,
                    pdf_url=item.pdf_url,
                    doc_url=item.doc.url if item.doc else None,
                )
                for item in releases
            ],
            authorize_enabled=status.valid,
            reason=status.reason,
        )

    async def desk(self, assignee: str | None) -> DeskProjection:
        """Return the projects and unresolved obligations relevant to one operator."""
        projects, obligations = await self._state.list_projects_and_obligations(assignee)
        return DeskProjection(
            open_obligations=[
                obligation
                for obligation in obligations
                if obligation.state == HumanObligationState.open
            ],
            active_work=[
                project
                for project in projects
                if project.disposition == Disposition.active
                and project.suspension == Suspension.running
                and project.visibility == Visibility.visible
            ],
            released_projects=[
                project
                for project in projects
                if project.disposition == Disposition.completed
                and project.visibility == Visibility.visible
            ],
        )

    async def inspect(self, project_id: str) -> ProjectWorkspaceView:
        loaded = await self._state.load_workspace(project_id)
        if loaded is None:
            raise ProjectNotFound(project_id)
        project, pieces, obligations = loaded
        open_obligations = [item for item in obligations if item.state == HumanObligationState.open]
        phase, reason = _project_phase(project, pieces, open_obligations)
        authority_by_kind = {item.kind: item.assignee for item in project.authorities}
        project_subject = ObligationSubject(kind="content-project", id=project_id)
        anchor = next((piece for piece in pieces if piece.role == PieceRole.anchor), None)
        anchor_subject = ObligationSubject(
            kind="piece", id=anchor.id if anchor and anchor.id else project_id
        )
        gate = await self._research_gate(project)
        quality_waiver = await self._state.latest_quality_waiver(project.id)
        research_readiness = (
            ArtifactReadiness.cleared
            if gate.satisfied_by == "research-report"
            else ArtifactReadiness.approved
            if gate.satisfied_by == "experiential-waiver"
            else ArtifactReadiness.absent
        )
        release_gate = await self._release_gate(anchor.id if anchor and anchor.id else None)
        accept_enabled = bool(release_gate) and not release_gate.approval_valid
        authorize_enabled = bool(release_gate and release_gate.authorize_enabled)
        waiver_enabled = bool(release_gate and release_gate.invalidated)
        available_commands = [
            AvailableCommand(
                command_type=CommandKind.declare_input_sufficient,
                subject=project_subject,
                enabled=gate.satisfied,
                reason=(
                    "Research gate satisfied \u2014 input sufficiency can now be declared."
                    if gate.satisfied
                    else "A Research Report or an approved experiential waiver is required first."
                ),
                requirements=["research-report-or-experiential-waiver"],
                authority_required=AuthorityKind.input_sufficiency,
                assigned_actor=authority_by_kind.get(AuthorityKind.input_sufficiency),
                expected_version=project.version,
            ),
            AvailableCommand(
                command_type=CommandKind.record_experiential_waiver,
                subject=project_subject,
                enabled=True,
                reason="Available only when the planned work is purely experiential or opinion-led.",
                authority_required=AuthorityKind.direction,
                assigned_actor=authority_by_kind.get(AuthorityKind.direction),
                expected_version=project.version,
            ),
            AvailableCommand(
                command_type=CommandKind.commission_derivative,
                subject=anchor_subject,
                enabled=False,
                reason="A Derivative Piece can be commissioned after an eligible Anchor Revision exists.",
                requirements=["approved-anchor-revision"],
                authority_required=AuthorityKind.direction,
                assigned_actor=authority_by_kind.get(AuthorityKind.direction),
                expected_version=project.version,
            ),
            AvailableCommand(
                command_type=CommandKind.accept_final_revision,
                subject=anchor_subject,
                enabled=accept_enabled,
                reason=(
                    release_gate.reason
                    if release_gate and accept_enabled
                    else "No quality-cleared Anchor Revision is available for acceptance."
                ),
                requirements=["quality-cleared-current-revision"],
                authority_required=AuthorityKind.release,
                assigned_actor=authority_by_kind.get(AuthorityKind.release),
                expected_version=project.version,
            ),
            AvailableCommand(
                command_type=CommandKind.record_trivial_edit_waiver,
                subject=anchor_subject,
                enabled=waiver_enabled,
                reason=(
                    "Canonical content changed since approval — record a trivial-edit waiver to keep it."
                    if waiver_enabled
                    else "A trivial-edit waiver is only needed when canonical content changed after approval."
                ),
                requirements=["invalidated-approval"],
                authority_required=AuthorityKind.release,
                assigned_actor=authority_by_kind.get(AuthorityKind.release),
                expected_version=project.version,
            ),
            AvailableCommand(
                command_type=CommandKind.record_quality_waiver,
                subject=project_subject,
                enabled=True,
                reason="Override the project's council quality bar, iteration ceiling, or cost ceiling.",
                authority_required=AuthorityKind.direction,
                assigned_actor=authority_by_kind.get(AuthorityKind.direction),
                expected_version=project.version,
            ),
            AvailableCommand(
                command_type=CommandKind.authorize_release,
                subject=anchor_subject,
                enabled=authorize_enabled,
                reason=(
                    release_gate.reason
                    if release_gate
                    else "Release authorization is separate and requires an Accepted Candidate."
                ),
                requirements=(
                    []
                    if authorize_enabled
                    else (
                        ["council-reapproval-or-trivial-edit-waiver"]
                        if release_gate and release_gate.invalidated
                        else ["accepted-candidate"]
                    )
                ),
                authority_required=AuthorityKind.release,
                assigned_actor=authority_by_kind.get(AuthorityKind.release),
                expected_version=project.version,
                irreversible=True,
            ),
        ]
        family = []
        any_released = False
        for piece in sorted(pieces, key=lambda item: item.role != PieceRole.anchor):
            is_anchor = anchor is not None and piece.id == anchor.id
            gate_for_piece = release_gate if is_anchor else None
            piece_phase, piece_reason, candidate_ready, release_ready = _piece_phase(gate_for_piece)
            if piece_phase == PiecePhase.released:
                any_released = True
            family.append(
                PieceWorkspaceItem(
                    id=piece.id or "",
                    version=piece.version,
                    role=piece.role,
                    title=piece.title,
                    destination=piece.destination,
                    voice_id=piece.voice_id,
                    disposition=piece.disposition,
                    suspension=piece.suspension,
                    visibility=piece.visibility,
                    derived_phase=piece_phase,
                    phase_reason=piece_reason,
                    source_anchor_revision_id=piece.source_anchor_revision_id,
                    lineage=piece.lineage,
                    promoted_piece_id=piece.promoted_piece_id,
                    artifact_readiness={
                        "research-report": research_readiness,
                        "evidence-snapshot": ArtifactReadiness.absent,
                        "revision": ArtifactReadiness.absent,
                        "accepted-candidate": candidate_ready,
                        "publication-release": release_ready,
                    },
                )
            )
        if any_released and project.disposition == Disposition.active:
            phase, reason = (
                ProjectPhase.final_mile,
                "A Publication Release exists; the workspace stays open for further releases and follow-ons.",
            )
        return ProjectWorkspaceView(
            generated_at=utcnow(),
            project=project,
            derived_phase=phase,
            phase_reason=reason,
            available_commands=available_commands,
            open_obligations=open_obligations,
            piece_family=family,
            artifact_readiness={
                "purpose-brief": ArtifactReadiness.approved,
                "research-report": research_readiness,
                "evidence-snapshot": ArtifactReadiness.absent,
            },
            research=gate,
            release=release_gate,
            quality_waiver=quality_waiver,
            active_work=[
                piece
                for piece in family
                if piece.disposition == Disposition.active
                and piece.suspension == Suspension.running
                and piece.visibility == Visibility.visible
            ],
            consistency_warnings=[],
        )


def _command_digest(command: CommandEnvelope) -> str:
    canonical = json.dumps(
        command.model_dump(mode="json", exclude={"idempotency_key"}),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _rejected_receipt(
    command: CommandEnvelope,
    digest: str,
    *,
    code: str,
    message: str,
    current_version: int | None = None,
) -> CommandReceipt:
    now = utcnow()
    return CommandReceipt(
        id=new_id(),
        command_type=command.command_type,
        aggregate=command.aggregate,
        actor=command.actor,
        idempotency_key=command.idempotency_key,
        payload_digest=digest,
        outcome="rejected",
        version_before=current_version,
        rejected_at=now,
        rejection=Rejection(
            code=code,
            message=message,
            current_version=current_version,
        ),
        created_at=now,
        updated_at=now,
    )


def _project_phase(
    project: ContentProject,
    pieces: list[ProjectPiece],
    obligations: list[HumanObligation],
) -> tuple[ProjectPhase, str]:
    if project.disposition == Disposition.abandoned:
        return ProjectPhase.abandoned, "The project was explicitly abandoned."
    if project.disposition == Disposition.completed:
        return ProjectPhase.completed, "All intended Pieces were released or abandoned."
    if any(item.kind == HumanObligationKind.confirm_input_sufficiency for item in obligations):
        return ProjectPhase.building_evidence, "Input sufficiency remains a human obligation."
    if not pieces:
        return ProjectPhase.shaping, "No Piece has been commissioned."
    return ProjectPhase.producing, "The project has commissioned Pieces in production."


def _piece_phase(
    gate: ReleaseGateView | None,
) -> tuple[PiecePhase, str, ArtifactReadiness, ArtifactReadiness]:
    """(phase, reason, accepted-candidate readiness, publication-release readiness)."""
    if gate is None:
        return (
            PiecePhase.input_building,
            "The Piece has no declared sufficient Evidence Snapshot.",
            ArtifactReadiness.absent,
            ArtifactReadiness.absent,
        )
    release_ready = (
        ArtifactReadiness.released if gate.releases else ArtifactReadiness.absent
    )
    if gate.releases:
        candidate = (
            ArtifactReadiness.approved
            if gate.approval_valid
            else ArtifactReadiness.blocked
            if gate.invalidated
            else ArtifactReadiness.absent
        )
        return (
            PiecePhase.released,
            "An immutable Publication Release exists; further releases are numbered and append-only.",
            candidate,
            release_ready,
        )
    if gate.invalidated:
        return (
            PiecePhase.human_revision,
            gate.reason,
            ArtifactReadiness.blocked,
            release_ready,
        )
    if gate.approval_valid:
        return (
            PiecePhase.release_ready,
            "An accepted candidate is ready for AuthorizeRelease.",
            ArtifactReadiness.approved,
            release_ready,
        )
    return (
        PiecePhase.input_building,
        "The Piece has no declared sufficient Evidence Snapshot.",
        ArtifactReadiness.absent,
        release_ready,
    )
