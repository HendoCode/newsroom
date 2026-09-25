"""Thin FastAPI adapters over ContentWorkflow submit/inspect (domain model §1.5/§1.6).

BFF callers and Operator Desk must not embed transition logic or sequence writes; all
orchestration stays server-side in ContentWorkflow.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from app.content_workflow import ContentWorkflow
from app.content_workflow.models import (
    ActorRef,
    CommandEnvelope,
    CommandReceipt,
    DeskProjection,
    ProjectWorkspaceView,
    ReportFact,
    ReportOpinion,
    ResearchGateView,
    ResearchReport,
)
from app.content_workflow.workflow import ProjectNotActive, ProjectNotFound
from app.models.common import new_id, utcnow

router = APIRouter(prefix="/api/content-workflow", tags=["content-workflow"])


def _require_workflow(request: Request) -> ContentWorkflow:
    wf = getattr(request.app.state, "content_workflow", None)
    if wf is None:
        raise HTTPException(
            status_code=503, detail="content workflow unavailable (workflow state not configured)"
        )
    return wf


@router.post("/submit", response_model=CommandReceipt, status_code=200)
async def submit_command(command: CommandEnvelope, request: Request) -> CommandReceipt:
    """Submit a typed command envelope (e.g. commit-idea). Idempotent on key+payload digest."""
    wf = _require_workflow(request)
    return await wf.submit(command)


@router.get("/{project_id}/inspect", response_model=ProjectWorkspaceView)
async def inspect_project(project_id: str, request: Request) -> ProjectWorkspaceView:
    """Project workspace projection for operator surfaces (phase, commands, obligations, pieces)."""
    wf = _require_workflow(request)
    return await wf.inspect(project_id)


@router.get("/desk", response_model=DeskProjection)
async def desk_projection(request: Request, assignee: str | None = None) -> DeskProjection:
    """Server-owned Desk projection for one operator's projects and obligations."""
    wf = getattr(request.app.state, "content_workflow", None)
    if wf is None:
        return DeskProjection()
    return await wf.desk(assignee)


class ResearchReportInput(BaseModel):
    """The operator-facing shape of a research report submission. ``submitted_by`` rides in the
    body because the agents service has no session identity of its own (attribution-only auth,
    docs/auth.md) — same convention as every other actor-carrying payload here."""

    subject: str = Field(min_length=1)
    facts: list[ReportFact] = Field(default_factory=list)
    opinions: list[ReportOpinion] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    submitted_by: ActorRef
    piece_id: str | None = None

    @model_validator(mode="after")
    def _require_sourced_facts(self) -> ResearchReportInput:
        if not self.facts:
            raise ValueError("a research report requires at least one sourced fact")
        return self


@router.get("/{project_id}/research-report", response_model=ResearchGateView)
async def get_research_gate(project_id: str, request: Request) -> ResearchGateView:
    """The project's research requirement: is a report required, is the gate satisfied, and by
    what (current report vs recorded experiential waiver)."""
    wf = _require_workflow(request)
    try:
        return await wf.research_gate(project_id)
    except ProjectNotFound as exc:
        raise HTTPException(status_code=404, detail=f"no content project {project_id!r}") from exc


@router.post(
    "/{project_id}/research-report", response_model=ResearchReport, status_code=201
)
async def submit_research_report(
    project_id: str, body: ResearchReportInput, request: Request
) -> ResearchReport:
    """Record the first-class research-report artifact (facts with sources, opinions kept apart,
    open questions carried forward). A new report supersedes the current one."""
    wf = _require_workflow(request)
    now = utcnow()
    report = ResearchReport(
        id=new_id(),
        content_project_id=project_id,
        piece_id=body.piece_id,
        subject=body.subject,
        facts=body.facts,
        opinions=body.opinions,
        open_questions=body.open_questions,
        submitted_by=body.submitted_by,
        created_at=now,
        updated_at=now,
    )
    try:
        return await wf.submit_research_report(project_id, report)
    except ProjectNotFound as exc:
        raise HTTPException(status_code=404, detail=f"no content project {project_id!r}") from exc
    except ProjectNotActive as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
