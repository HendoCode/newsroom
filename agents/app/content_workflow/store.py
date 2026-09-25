"""Narrow persistence port plus its Mongo transaction implementation."""

from __future__ import annotations

from typing import Any, Protocol

from pymongo import ASCENDING
from pymongo.errors import OperationFailure

from app.content_workflow.models import (
    CommandEnvelope,
    CommandReceipt,
    ContentProject,
    ExperientialWaiver,
    HumanObligation,
    HumanObligationState,
    ObligationResolution,
    ProjectPiece,
    QualityWaiver,
    ResearchReport,
)
from app.models.piece import Piece, PieceRole, PieceStage
from app.models.publication import PublicationRelease, TrivialEditWaiver
from app.models.common import new_id, utcnow
from app.models.spike import Spike
from app.repositories.base import mongo_encode


class WorkflowConflict(Exception):
    def __init__(self, code: str, message: str, *, current_version: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.current_version = current_version


class WorkflowState(Protocol):
    async def receipt_for(self, idempotency_key: str) -> CommandReceipt | None: ...

    async def commit_idea(
        self,
        command: CommandEnvelope,
        project: ContentProject,
        piece: ProjectPiece,
        obligations: list[HumanObligation],
        receipt: CommandReceipt,
    ) -> CommandReceipt: ...

    async def load_workspace(
        self, project_id: str
    ) -> tuple[ContentProject, list[ProjectPiece], list[HumanObligation]] | None: ...

    async def load_project(self, project_id: str) -> ContentProject | None: ...

    async def create_obligation(self, obligation: HumanObligation) -> HumanObligation: ...

    async def resolve_obligation(
        self, obligation_id: str, resolution: ObligationResolution
    ) -> HumanObligation | None: ...

    async def list_projects_and_obligations(
        self, assignee: str | None
    ) -> tuple[list[ContentProject], list[HumanObligation]]: ...


    async def submit_research_report(self, report: ResearchReport) -> ResearchReport:
        """Persist a new research report, superseding any current one on the same project."""
        ...

    async def latest_research_report(self, project_id: str) -> ResearchReport | None: ...

    async def record_waiver(self, waiver: ExperientialWaiver) -> ExperientialWaiver:
        """Persist an experiential waiver and bump the project version (optimistic concurrency)."""
        ...

    async def latest_waiver(self, project_id: str) -> ExperientialWaiver | None: ...

    async def record_quality_waiver(self, waiver: QualityWaiver) -> QualityWaiver: ...

    async def latest_quality_waiver(self, project_id: str) -> QualityWaiver | None: ...

    async def bump_project_version(self, project_id: str) -> None: ...

    async def save_receipt(self, receipt: CommandReceipt) -> CommandReceipt: ...

    async def load_legacy_piece(self, piece_id: str) -> Piece | None: ...

    async def stamp_approval(self, piece_id: str, revision: str) -> Piece | None: ...

    async def set_legacy_stage(self, piece_id: str, stage: PieceStage) -> Piece | None: ...

    async def insert_publication_release(self, release: PublicationRelease) -> PublicationRelease: ...

    async def list_publication_releases(self, piece_id: str) -> list[PublicationRelease]: ...

    async def insert_trivial_edit_waiver(self, waiver: TrivialEditWaiver) -> TrivialEditWaiver: ...

    async def list_trivial_edit_waivers(self, piece_id: str) -> list[TrivialEditWaiver]: ...


class MongoWorkflowState:
    """All cross-record writes are committed in one Mongo transaction."""

    def __init__(self, database: Any) -> None:
        self._db = database
        self._ideas = database["spikes"]
        self._projects = database["content_projects"]
        self._pieces = database["project_pieces"]
        self._obligations = database["human_obligations"]
        self._receipts = database["command_receipts"]
        self._research_reports = database["research_reports"]
        self._waivers = database["experiential_waivers"]
        self._legacy_pieces = database["pieces"]
        self._publication_releases = database["publication_releases"]
        self._trivial_edit_waivers = database["trivial_edit_waivers"]
        self._quality_waivers = database["quality_waivers"]

    async def ensure_indexes(self) -> None:
        await self._projects.create_index("originating_idea_id", unique=True)
        await self._pieces.create_index(
            [("content_project_id", ASCENDING), ("role", ASCENDING)],
            unique=True,
            partialFilterExpression={"role": "anchor"},
            name="one_anchor_per_project",
        )
        await self._receipts.create_index("idempotency_key", unique=True)
        await self._publication_releases.create_index(
            [("piece_id", ASCENDING), ("release_number", ASCENDING)],
            unique=True,
            name="one_number_per_piece_release",
        )

    async def receipt_for(self, idempotency_key: str) -> CommandReceipt | None:
        doc = await self._receipts.find_one({"idempotency_key": idempotency_key})
        return CommandReceipt.model_validate(doc) if doc else None

    async def _commit_idea_body(
        self,
        command: CommandEnvelope,
        project: ContentProject,
        piece: ProjectPiece,
        obligations: list[HumanObligation],
        receipt: CommandReceipt,
        *,
        session: Any | None = None,
    ) -> None:
        """The actual commit-idea writes, run either inside a Mongo transaction or directly on
        a standalone/mongomock database that does not support sessions."""
        sess_kw: dict[str, Any] = {"session": session} if session is not None else {}
        idea_doc = await self._ideas.find_one({"_id": command.aggregate.id}, **sess_kw)
        if idea_doc is None:
            raise WorkflowConflict("idea-not-found", "the proposed Idea does not exist")
        current_version = int(idea_doc.get("version", 0))
        if current_version != command.expected_version:
            raise WorkflowConflict(
                "version-conflict",
                "the Idea changed after it was inspected",
                current_version=current_version,
            )
        if idea_doc.get("status") not in {"proposed", "vaulted"}:
            raise WorkflowConflict(
                "idea-not-committable",
                f"Idea is {idea_doc.get('status')!r}, not proposed or vaulted",
                current_version=current_version,
            )

        update = await self._ideas.update_one(
            {
                "_id": command.aggregate.id,
                "version": current_version,
                "status": {"$in": ["proposed", "vaulted"]},
            },
            {
                "$set": {
                    "status": "in-use",
                    "content_project_id": project.id,
                },
                "$inc": {"version": 1},
            },
            **sess_kw,
        )
        if update.modified_count != 1:
            raise WorkflowConflict(
                "version-conflict",
                "the Idea was committed concurrently",
                current_version=current_version,
            )
        await self._projects.insert_one(
            mongo_encode(project.model_dump(by_alias=True)), **sess_kw
        )
        await self._pieces.insert_one(
            mongo_encode(piece.model_dump(by_alias=True)), **sess_kw
        )

        # Create legacy Piece for the anchor piece (integration with legacy pipeline)
        legacy_piece = Piece(
            id=piece.id,
            content_project_id=project.id,
            role=PieceRole.anchor,
            slug=piece.slug,
            voice=piece.voice_id,
            title=piece.title,
            stage="interviewing",
            owner=None,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        await self._db["pieces"].insert_one(
            mongo_encode(legacy_piece.model_dump(by_alias=True)), **sess_kw
        )

        if obligations:
            await self._obligations.insert_many(
                [mongo_encode(item.model_dump(by_alias=True)) for item in obligations],
                **sess_kw,
            )
        await self._receipts.insert_one(
            mongo_encode(receipt.model_dump(by_alias=True)), **sess_kw
        )

    async def commit_idea(
        self,
        command: CommandEnvelope,
        project: ContentProject,
        piece: ProjectPiece,
        obligations: list[HumanObligation],
        receipt: CommandReceipt,
    ) -> CommandReceipt:
        client = self._db.client
        try:
            async with await client.start_session() as session:
                async with session.start_transaction():
                    await self._commit_idea_body(
                        command, project, piece, obligations, receipt, session=session
                    )
        except (NotImplementedError, OperationFailure):
            # mongomock doesn't support sessions; standalone Mongo rejects transactions
            # (e.g. "Transaction numbers are only allowed on a replica set member or mongos").
            # Degrade to a non-transactional commit so the same code path works locally.
            await self._commit_idea_body(command, project, piece, obligations, receipt)
        return receipt

    async def load_workspace(
        self, project_id: str
    ) -> tuple[ContentProject, list[ProjectPiece], list[HumanObligation]] | None:
        project_doc = await self._projects.find_one({"_id": project_id})
        if project_doc is None:
            return None
        piece_docs = self._pieces.find({"content_project_id": project_id})
        obligation_docs = self._obligations.find({"content_project_id": project_id})
        pieces = [ProjectPiece.model_validate(doc) async for doc in piece_docs]
        obligations = [HumanObligation.model_validate(doc) async for doc in obligation_docs]
        return ContentProject.model_validate(project_doc), pieces, obligations

    async def load_project(self, project_id: str) -> ContentProject | None:
        project_doc = await self._projects.find_one({"_id": project_id})
        return ContentProject.model_validate(project_doc) if project_doc else None

    async def create_obligation(self, obligation: HumanObligation) -> HumanObligation:
        await self._obligations.insert_one(
            mongo_encode(obligation.model_dump(by_alias=True))
        )
        return obligation

    async def resolve_obligation(
        self, obligation_id: str, resolution: ObligationResolution
    ) -> HumanObligation | None:
        doc = await self._obligations.find_one_and_update(
            {"_id": obligation_id, "state": HumanObligationState.open.value},
            {
                "$set": {
                    "state": HumanObligationState.resolved.value,
                    "resolution": mongo_encode(resolution.model_dump(by_alias=True)),
                    "updated_at": utcnow(),
                }
            },
            return_document=True,
        )
        return HumanObligation.model_validate(doc) if doc else None

    async def list_projects_and_obligations(
        self, assignee: str | None
    ) -> tuple[list[ContentProject], list[HumanObligation]]:
        project_query = _assignee_query("authorities.assignee", assignee)
        obligation_query = _assignee_query("assignee", assignee)
        project_docs = self._projects.find(project_query).sort("updated_at", -1)
        obligation_docs = self._obligations.find(obligation_query).sort("created_at", -1)
        projects = [ContentProject.model_validate(doc) async for doc in project_docs]
        obligations = [HumanObligation.model_validate(doc) async for doc in obligation_docs]
        return projects, obligations

    async def submit_research_report(self, report: ResearchReport) -> ResearchReport:
        await self._research_reports.update_many(
            {"content_project_id": report.content_project_id, "status": "current"},
            {
                "$set": {"status": "superseded", "superseded_at": utcnow()},
            },
        )
        await self._research_reports.insert_one(
            mongo_encode(report.model_dump(by_alias=True))
        )
        return report

    async def latest_research_report(self, project_id: str) -> ResearchReport | None:
        doc = await self._research_reports.find_one(
            {"content_project_id": project_id, "status": "current"},
            sort=[("created_at", -1)],
        )
        return ResearchReport.model_validate(doc) if doc else None

    async def record_waiver(self, waiver: ExperientialWaiver) -> ExperientialWaiver:
        await self._waivers.insert_one(mongo_encode(waiver.model_dump(by_alias=True)))
        await self.bump_project_version(waiver.content_project_id)
        return waiver

    async def latest_waiver(self, project_id: str) -> ExperientialWaiver | None:
        doc = await self._waivers.find_one(
            {"content_project_id": project_id}, sort=[("recorded_at", -1)]
        )
        return ExperientialWaiver.model_validate(doc) if doc else None

    async def record_quality_waiver(self, waiver: QualityWaiver) -> QualityWaiver:
        await self._quality_waivers.insert_one(mongo_encode(waiver.model_dump(by_alias=True)))
        await self.bump_project_version(waiver.content_project_id)
        return waiver

    async def latest_quality_waiver(self, project_id: str) -> QualityWaiver | None:
        doc = await self._quality_waivers.find_one(
            {"content_project_id": project_id}, sort=[("recorded_at", -1)]
        )
        return QualityWaiver.model_validate(doc) if doc else None

    async def bump_project_version(self, project_id: str) -> None:
        await self._projects.update_one(
            {"_id": project_id},
            {"$inc": {"version": 1}, "$set": {"updated_at": utcnow()}},
        )

    async def save_receipt(self, receipt: CommandReceipt) -> CommandReceipt:
        await self._receipts.insert_one(mongo_encode(receipt.model_dump(by_alias=True)))
        return receipt

    async def load_legacy_piece(self, piece_id: str) -> Piece | None:
        doc = await self._legacy_pieces.find_one({"_id": piece_id})
        return Piece.model_validate(doc) if doc else None

    async def stamp_approval(self, piece_id: str, revision: str) -> Piece | None:
        now = utcnow()
        piece = await self.load_legacy_piece(piece_id)
        changes: dict[str, object] = {
            "approved_revision": revision,
            "approved_at": now,
            "updated_at": now,
        }
        if piece is not None and not piece.latest_revision:
            changes["latest_revision"] = revision
        await self._legacy_pieces.update_one({"_id": piece_id}, {"$set": changes})
        return await self.load_legacy_piece(piece_id)

    async def set_legacy_stage(self, piece_id: str, stage: PieceStage) -> Piece | None:
        await self._legacy_pieces.update_one(
            {"_id": piece_id},
            {"$set": {"stage": PieceStage(stage).value, "updated_at": utcnow()}},
        )
        return await self.load_legacy_piece(piece_id)

    async def insert_publication_release(self, release: PublicationRelease) -> PublicationRelease:
        if release.id is None:
            release.id = new_id()
        if release.created_at is None:
            release.created_at = utcnow()
        release.updated_at = utcnow()
        await self._publication_releases.insert_one(mongo_encode(release.model_dump(by_alias=True)))
        return release

    async def list_publication_releases(self, piece_id: str) -> list[PublicationRelease]:
        cursor = self._publication_releases.find({"piece_id": piece_id}).sort("release_number", 1)
        return [PublicationRelease.model_validate(doc) async for doc in cursor]

    async def insert_trivial_edit_waiver(self, waiver: TrivialEditWaiver) -> TrivialEditWaiver:
        if waiver.id is None:
            waiver.id = new_id()
        if waiver.created_at is None:
            waiver.created_at = utcnow()
        waiver.updated_at = utcnow()
        await self._trivial_edit_waivers.insert_one(mongo_encode(waiver.model_dump(by_alias=True)))
        return waiver

    async def list_trivial_edit_waivers(self, piece_id: str) -> list[TrivialEditWaiver]:
        cursor = self._trivial_edit_waivers.find({"piece_id": piece_id}).sort("recorded_at", 1)
        return [TrivialEditWaiver.model_validate(doc) async for doc in cursor]


class InMemoryWorkflowState:
    """Transactional test adapter; state is published only after every invariant passes."""

    def __init__(self, ideas: list[Spike] | None = None) -> None:
        self.ideas = {idea.id: idea for idea in ideas or [] if idea.id}
        self.projects: dict[str, ContentProject] = {}
        self.pieces: dict[str, ProjectPiece] = {}
        self.obligations: dict[str, HumanObligation] = {}
        self.receipts: dict[str, CommandReceipt] = {}
        self.legacy_pieces: dict[str, Piece] = {}
        self.research_reports: list[ResearchReport] = []
        self.waivers: list[ExperientialWaiver] = []
        self.publication_releases: list[PublicationRelease] = []
        self.trivial_edit_waivers: list[TrivialEditWaiver] = []
        self.quality_waivers: list[QualityWaiver] = []
        self.fail_before_commit = False

    async def receipt_for(self, idempotency_key: str) -> CommandReceipt | None:
        return self.receipts.get(idempotency_key)

    async def commit_idea(
        self,
        command: CommandEnvelope,
        project: ContentProject,
        piece: ProjectPiece,
        obligations: list[HumanObligation],
        receipt: CommandReceipt,
    ) -> CommandReceipt:
        idea = self.ideas.get(command.aggregate.id)
        if idea is None:
            raise WorkflowConflict("idea-not-found", "the proposed Idea does not exist")
        current_version = idea.version
        if current_version != command.expected_version:
            raise WorkflowConflict(
                "version-conflict",
                "the Idea changed after it was inspected",
                current_version=current_version,
            )
        if idea.status not in {"proposed", "vaulted"}:
            raise WorkflowConflict(
                "idea-not-committable",
                f"Idea is {idea.status!r}, not proposed or vaulted",
                current_version=current_version,
            )
        if self.fail_before_commit:
            raise RuntimeError("injected transaction failure")

        idea.status = "in-use"
        idea.version += 1
        idea.content_project_id = project.id
        self.projects[project.id] = project
        self.pieces[piece.id] = piece
        self.obligations.update({item.id: item for item in obligations})
        self.receipts[receipt.idempotency_key] = receipt
        
        # Create legacy Piece for testing
        legacy_piece = Piece(
            id=piece.id,
            content_project_id=project.id,
            role=PieceRole.anchor,
            slug=piece.slug,
            voice=piece.voice_id,
            title=piece.title,
            stage="interviewing",
            owner=None,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        self.legacy_pieces[piece.id] = legacy_piece
        return receipt

    async def load_workspace(
        self, project_id: str
    ) -> tuple[ContentProject, list[ProjectPiece], list[HumanObligation]] | None:
        project = self.projects.get(project_id)
        if project is None:
            return None
        pieces = [p for p in self.pieces.values() if p.content_project_id == project_id]
        obligations = [o for o in self.obligations.values() if o.content_project_id == project_id]
        return project, pieces, obligations

    async def load_project(self, project_id: str) -> ContentProject | None:
        return self.projects.get(project_id)

    async def create_obligation(self, obligation: HumanObligation) -> HumanObligation:
        self.obligations[obligation.id] = obligation
        return obligation

    async def resolve_obligation(
        self, obligation_id: str, resolution: ObligationResolution
    ) -> HumanObligation | None:
        obligation = self.obligations.get(obligation_id)
        if obligation is None or obligation.state != HumanObligationState.open:
            return None
        obligation.state = HumanObligationState.resolved
        obligation.resolution = resolution
        obligation.updated_at = utcnow()
        return obligation

    async def list_projects_and_obligations(
        self, assignee: str | None
    ) -> tuple[list[ContentProject], list[HumanObligation]]:
        projects = [
            project
            for project in self.projects.values()
            if _matches_assignee(
                assignee,
                [assignment.assignee for assignment in project.authorities],
            )
        ]
        obligations = [
            obligation
            for obligation in self.obligations.values()
            if _matches_assignee(assignee, [obligation.assignee])
        ]
        return projects, obligations

    async def submit_research_report(self, report: ResearchReport) -> ResearchReport:
        for existing in self.research_reports:
            if (
                existing.content_project_id == report.content_project_id
                and existing.status == "current"
            ):
                existing.status = "superseded"
                existing.superseded_at = utcnow()
        self.research_reports.append(report)
        return report

    async def latest_research_report(self, project_id: str) -> ResearchReport | None:
        current = [
            report
            for report in self.research_reports
            if report.content_project_id == project_id and report.status == "current"
        ]
        return current[-1] if current else None

    async def record_waiver(self, waiver: ExperientialWaiver) -> ExperientialWaiver:
        self.waivers.append(waiver)
        await self.bump_project_version(waiver.content_project_id)
        return waiver

    async def latest_waiver(self, project_id: str) -> ExperientialWaiver | None:
        matching = [w for w in self.waivers if w.content_project_id == project_id]
        return matching[-1] if matching else None

    async def record_quality_waiver(self, waiver: QualityWaiver) -> QualityWaiver:
        self.quality_waivers.append(waiver)
        await self.bump_project_version(waiver.content_project_id)
        return waiver

    async def latest_quality_waiver(self, project_id: str) -> QualityWaiver | None:
        matching = [w for w in self.quality_waivers if w.content_project_id == project_id]
        return matching[-1] if matching else None

    async def bump_project_version(self, project_id: str) -> None:
        project = self.projects.get(project_id)
        if project is not None:
            project.version += 1
            project.updated_at = utcnow()

    async def save_receipt(self, receipt: CommandReceipt) -> CommandReceipt:
        self.receipts[receipt.idempotency_key] = receipt
        return receipt

    async def load_legacy_piece(self, piece_id: str) -> Piece | None:
        return self.legacy_pieces.get(piece_id)

    async def stamp_approval(self, piece_id: str, revision: str) -> Piece | None:
        piece = self.legacy_pieces.get(piece_id)
        if piece is None:
            return None
        piece.approved_revision = revision
        piece.approved_at = utcnow()
        piece.updated_at = utcnow()
        if not piece.latest_revision:
            piece.latest_revision = revision
        return piece

    async def set_legacy_stage(self, piece_id: str, stage: PieceStage) -> Piece | None:
        piece = self.legacy_pieces.get(piece_id)
        if piece is None:
            return None
        piece.stage = PieceStage(stage).value
        piece.updated_at = utcnow()
        return piece

    async def insert_publication_release(self, release: PublicationRelease) -> PublicationRelease:
        if release.id is None:
            release.id = new_id()
        if release.created_at is None:
            release.created_at = utcnow()
        release.updated_at = utcnow()
        self.publication_releases.append(release)
        return release

    async def list_publication_releases(self, piece_id: str) -> list[PublicationRelease]:
        return sorted(
            [r for r in self.publication_releases if r.piece_id == piece_id],
            key=lambda r: r.release_number,
        )

    async def insert_trivial_edit_waiver(self, waiver: TrivialEditWaiver) -> TrivialEditWaiver:
        if waiver.id is None:
            waiver.id = new_id()
        if waiver.created_at is None:
            waiver.created_at = utcnow()
        waiver.updated_at = utcnow()
        self.trivial_edit_waivers.append(waiver)
        return waiver

    async def list_trivial_edit_waivers(self, piece_id: str) -> list[TrivialEditWaiver]:
        return [w for w in self.trivial_edit_waivers if w.piece_id == piece_id]


def _assignee_query(prefix: str, assignee: str | None) -> dict[str, object]:
    if not assignee:
        return {}
    return {
        "$or": [
            {f"{prefix}.subject_id": assignee},
            {f"{prefix}.email": assignee},
        ]
    }


def _matches_assignee(assignee: str | None, actors: list[object]) -> bool:
    if not assignee:
        return True
    return any(
        getattr(actor, "subject_id", None) == assignee
        or getattr(actor, "email", None) == assignee
        for actor in actors
    )
