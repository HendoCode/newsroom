"""Public contracts and persisted facts for the Evidence-to-Publication Loop."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.models.common import MongoModel
from app.models.derivative import DerivativeLineage


class Disposition(str, Enum):
    active = "active"
    completed = "completed"
    abandoned = "abandoned"


class Suspension(str, Enum):
    running = "running"
    paused = "paused"


class Visibility(str, Enum):
    visible = "visible"
    archived = "archived"


class PieceRole(str, Enum):
    anchor = "anchor"
    derivative = "derivative"


class AuthorityKind(str, Enum):
    direction = "direction"
    input_sufficiency = "input-sufficiency"
    contribution = "contribution"
    claim = "claim"
    clearance = "clearance"
    voice = "voice"
    release = "release"


class HumanObligationKind(str, Enum):
    choose_direction = "choose-direction"
    answer_question = "answer-question"
    approve_contribution = "approve-contribution"
    confirm_input_sufficiency = "confirm-input-sufficiency"
    resolve_gap = "resolve-gap"
    correct_claim = "correct-claim"
    grant_clearance = "grant-clearance"
    close_review = "close-review"
    revise_final = "revise-final"
    accept_final_revision = "accept-final-revision"
    authorize_release = "authorize-release"
    decide_lesson = "decide-lesson"
    decide_abandonment = "decide-abandonment"
    attention_required = "attention-required"


class HumanObligationState(str, Enum):
    open = "open"
    resolved = "resolved"
    declined = "declined"
    superseded = "superseded"


class ArtifactReadiness(str, Enum):
    absent = "absent"
    assembling = "assembling"
    reviewable = "reviewable"
    blocked = "blocked"
    cleared = "cleared"
    approved = "approved"
    released = "released"
    superseded = "superseded"


class ProjectPhase(str, Enum):
    shaping = "shaping"
    building_evidence = "building-evidence"
    producing = "producing"
    final_mile = "final-mile"
    completed = "completed"
    abandoned = "abandoned"


class PiecePhase(str, Enum):
    planned = "planned"
    input_building = "input-building"
    drafting = "drafting"
    quality_closure = "quality-closure"
    human_revision = "human-revision"
    release_ready = "release-ready"
    released = "released"
    abandoned = "abandoned"


class CommandKind(str, Enum):
    commit_idea = "commit-idea"
    declare_input_sufficient = "declare-input-sufficient"
    record_experiential_waiver = "record-experiential-waiver"
    commission_derivative = "commission-derivative"
    accept_final_revision = "accept-final-revision"
    authorize_release = "authorize-release"
    record_trivial_edit_waiver = "record-trivial-edit-waiver"
    record_quality_waiver = "record-quality-waiver"


class ActorRef(BaseModel):
    subject_id: str = Field(default="", min_length=0)
    display_name: str | None = None
    email: str | None = None

    @model_validator(mode="after")
    def _ensure_subject_id(self) -> ActorRef:
        if not self.subject_id:
            if self.email:
                self.subject_id = self.email
            else:
                raise ValueError("subject_id or email is required")
        return self


class AggregateRef(BaseModel):
    # "idea" for commit-idea (the command that consumes an Idea); "content-project" for
    # project-scoped commands recorded after the project exists (record-experiential-waiver).
    kind: Literal["idea", "content-project"]
    id: str = Field(min_length=1)


class PurposeBrief(BaseModel):
    proposition: str = Field(min_length=1)
    audience: str = Field(default="General", min_length=1)
    angle: str = Field(default="Default", min_length=1)
    desired_outcome: str = Field(default="Core proposition adopted", min_length=1)
    why_now: str = Field(default="Relevant operational context", min_length=1)
    constraints: list[str] = Field(default_factory=list)


class AuthorityAssignment(BaseModel):
    kind: AuthorityKind
    assignee: ActorRef
    scope: str = "project"
    assigned_by: ActorRef
    assigned_at: datetime


class AuthorityInput(BaseModel):
    kind: AuthorityKind
    assignee: ActorRef
    scope: str = "project"


class CouncilPolicy(BaseModel):
    mode: Literal["bounded-autonomy"] = "bounded-autonomy"
    quality_bar: float = 9.0
    iteration_ceiling: int = Field(default=3, ge=1)
    cost_ceiling_usd: float = Field(default=25.0, gt=0)
    plateau_policy: str = "stop-when-score-does-not-improve"
    gaps_require_human: bool = True
    clearances_require_human: bool = True


class ResearchPolicy(BaseModel):
    report_required_by_default: Literal[True] = True
    experiential_waiver_allowed: Literal[True] = True
    policy_version: str = "research-v1"


class ReportFact(BaseModel):
    """One sourced fact: the statement plus where it came from. A research report without at
    least one sourced fact is not a *sourced* research report (research-v1 policy)."""

    statement: str = Field(min_length=1)
    source: str = Field(min_length=1)


class ReportOpinion(BaseModel):
    """One opinion/judgment call, kept strictly apart from facts (facts-vs-opinion split)."""

    statement: str = Field(min_length=1)
    holder: str | None = None


class ResearchReport(MongoModel):
    """The first-class research-report artifact (research-v1): required by default after idea
    selection and before interviews. Facts carry sources; opinions are labeled as such; open
    questions are carried forward into the interview, never silently dropped."""

    content_project_id: str
    piece_id: str | None = None
    subject: str = Field(min_length=1)
    facts: list[ReportFact] = Field(default_factory=list)
    opinions: list[ReportOpinion] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    submitted_by: ActorRef
    status: Literal["current", "superseded"] = "current"
    superseded_at: datetime | None = None

    @model_validator(mode="after")
    def _require_sourced_facts(self) -> ResearchReport:
        if not self.facts:
            raise ValueError("a research report requires at least one sourced fact")
        return self


class ExperientialWaiver(MongoModel):
    """A recorded experiential waiver: an operator with subject-matter experience skips the
    research report. The record itself (actor + reason) is the audit trail — a waiver is never
    silent (research-v1 policy)."""

    content_project_id: str
    actor: ActorRef
    reason: str = Field(min_length=1)
    experience_basis: str | None = None
    recorded_at: datetime


class ResearchGateView(BaseModel):
    """The research requirement for one project, projected for operator surfaces: is a report
    required, is the gate already satisfied (and by what), plus the satisfying artifact."""

    required: bool
    satisfied: bool
    satisfied_by: Literal["research-report", "experiential-waiver"] | None = None
    report: ResearchReport | None = None
    waiver: ExperientialWaiver | None = None


class PublicationReleaseOut(BaseModel):
    id: str | None = None
    piece_id: str
    release_number: int
    revision: str
    authorized_by_subject_id: str
    authorized_at: datetime
    html_url: str | None = None
    pdf_url: str | None = None
    doc_url: str | None = None


class ReleaseGateView(BaseModel):
    """The AuthorizeRelease gate for one piece, projected for operator surfaces.

    Authority-model (queued) will add an actor-vs-assignment check on top of ``authorize_enabled``;
    this view already carries ``authority_required`` via ``inspect().available_commands``.
    """

    piece_id: str
    accepted_revision: str | None = None
    current_revision: str | None = None
    approval_valid: bool = False
    invalidated: bool = False
    waiver_reason: str | None = None
    releases: list[PublicationReleaseOut] = Field(default_factory=list)
    authorize_enabled: bool = False
    reason: str = ""


class QualityWaiver(MongoModel):
    """A recorded council-policy override: actor, reason, policy version, and the explicit
    override values that replace the project's defaults for one run. At least one override
    value must be set."""

    content_project_id: str
    actor: ActorRef
    reason: str = Field(min_length=1)
    policy_version: str = Field(default="council-v1")
    quality_bar: float | None = None
    iteration_ceiling: int | None = Field(default=None, ge=1)
    cost_ceiling_usd: float | None = Field(default=None, gt=0)
    recorded_at: datetime

    @model_validator(mode="after")
    def _require_at_least_one_override(self) -> QualityWaiver:
        if (
            self.quality_bar is None
            and self.iteration_ceiling is None
            and self.cost_ceiling_usd is None
        ):
            raise ValueError("a quality waiver must override at least one of quality_bar, iteration_ceiling, or cost_ceiling_usd")
        return self


class RecordExperientialWaiverPayload(BaseModel):
    type: Literal["record-experiential-waiver"] = "record-experiential-waiver"
    content_project_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    experience_basis: str | None = None


class DeclareInputSufficientPayload(BaseModel):
    type: Literal["declare-input-sufficient"] = "declare-input-sufficient"
    content_project_id: str = Field(min_length=1)
    reason: str | None = None


class RecordQualityWaiverPayload(BaseModel):
    type: Literal["record-quality-waiver"] = "record-quality-waiver"
    content_project_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    policy_version: str = Field(default="council-v1")
    quality_bar: float | None = None
    iteration_ceiling: int | None = Field(default=None, ge=1)
    cost_ceiling_usd: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _require_at_least_one_override(self) -> RecordQualityWaiverPayload:
        if (
            self.quality_bar is None
            and self.iteration_ceiling is None
            and self.cost_ceiling_usd is None
        ):
            raise ValueError("a quality waiver must override at least one of quality_bar, iteration_ceiling, or cost_ceiling_usd")
        return self


class AcceptFinalRevisionPayload(BaseModel):
    """Human accepts the current canonical revision as the release candidate.

    Also the council-reapproval path after a substantive final-pass edit invalidated the prior
    approval: accepting again stamps a new ``approved_revision``.
    """

    type: Literal["accept-final-revision"] = "accept-final-revision"
    content_project_id: str = Field(min_length=1)
    piece_id: str = Field(min_length=1)
    revision: str = Field(min_length=1)


class AuthorizeReleasePayload(BaseModel):
    """Explicit human AuthorizeRelease. The machine never publishes; this command is the only
    workflow writer of a Publication Release. Authority-model (queued) will gate WHO may submit
    it; this ticket only records ``actor`` and creates the immutable numbered release.
    """

    type: Literal["authorize-release"] = "authorize-release"
    content_project_id: str = Field(min_length=1)
    piece_id: str = Field(min_length=1)


class RecordTrivialEditWaiverPayload(BaseModel):
    """Recorded path for a trivial final-pass canonical edit: keeps the prior approval valid
    across ``from_revision`` → ``to_revision``. Actor + reason ARE the audit trail.
    """

    type: Literal["record-trivial-edit-waiver"] = "record-trivial-edit-waiver"
    content_project_id: str = Field(min_length=1)
    piece_id: str = Field(min_length=1)
    from_revision: str = Field(min_length=1)
    to_revision: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class CommitIdeaPayload(BaseModel):
    type: Literal["commit-idea"] = "commit-idea"
    project_title: str = Field(default="", min_length=0)
    purpose_brief: PurposeBrief | None = None
    default_voice_id: str = Field(default="demo-dana", min_length=1)
    authorities: list[AuthorityInput] = Field(default_factory=list)
    anchor_title: str = Field(default="", min_length=0)
    anchor_slug: str = Field(default="", min_length=0)
    anchor_destination: str = Field(default="blog", min_length=1)
    council_policy: CouncilPolicy = Field(default_factory=CouncilPolicy)

    @model_validator(mode="before")
    @classmethod
    def _coerce_shorthand_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "type" not in d:
            d["type"] = "commit-idea"

        # project_title fallback from title
        if not d.get("project_title") and d.get("title"):
            d["project_title"] = d["title"]

        # default_voice_id fallback from voice_id
        if not d.get("default_voice_id") and d.get("voice_id"):
            d["default_voice_id"] = d["voice_id"]

        # anchor_title fallback from project_title / title
        if not d.get("anchor_title"):
            if d.get("project_title"):
                d["anchor_title"] = d["project_title"]
            elif d.get("title"):
                d["anchor_title"] = d["title"]

        # anchor_slug fallback from anchor_title / project_title / title / slug
        if not d.get("anchor_slug"):
            candidate = d.get("slug") or d.get("anchor_title") or d.get("project_title") or d.get("title") or "idea"
            slug = re.sub(r"[^a-z0-9]+", "-", str(candidate).lower()).strip("-")
            d["anchor_slug"] = slug or "idea"

        # purpose_brief fallback from narrative or flat fields
        if "purpose_brief" not in d or d["purpose_brief"] is None:
            prop = (
                d.get("proposition")
                or d.get("narrative")
                or d.get("project_title")
                or d.get("title")
                or "Idea proposition"
            )
            d["purpose_brief"] = {
                "proposition": prop,
                "audience": d.get("audience") or "General",
                "angle": d.get("angle") or "Default",
                "desired_outcome": d.get("desired_outcome") or "Core proposition adopted",
                "why_now": d.get("why_now") or "Relevant operational context",
                "constraints": d.get("constraints") or [],
            }
        elif isinstance(d["purpose_brief"], str):
            d["purpose_brief"] = {
                "proposition": d["purpose_brief"],
                "audience": d.get("audience") or "General",
                "angle": d.get("angle") or "Default",
                "desired_outcome": d.get("desired_outcome") or "Core proposition adopted",
                "why_now": d.get("why_now") or "Relevant operational context",
                "constraints": d.get("constraints") or [],
            }

        # authorities fallback from owners or single actor
        if not d.get("authorities"):
            owners = d.get("owners") or []
            assignee_ref: dict[str, Any]
            if owners and isinstance(owners[0], str):
                assignee_ref = {"subject_id": owners[0], "email": owners[0]}
            elif owners and isinstance(owners[0], dict):
                assignee_ref = owners[0]
            else:
                assignee_ref = {"subject_id": "operator", "email": "operator@example.com"}

            d["authorities"] = [
                {"kind": "direction", "assignee": assignee_ref, "scope": "project"},
                {"kind": "input-sufficiency", "assignee": assignee_ref, "scope": "project"},
                {"kind": "voice", "assignee": assignee_ref, "scope": "project"},
                {"kind": "release", "assignee": assignee_ref, "scope": "project"},
            ]

        return d

    @model_validator(mode="after")
    def _validate_fields(self) -> CommitIdeaPayload:
        if not self.project_title:
            raise ValueError("project_title is required")
        if not self.anchor_title:
            self.anchor_title = self.project_title
        if not self.anchor_slug:
            slug = re.sub(r"[^a-z0-9]+", "-", self.anchor_title.lower()).strip("-")
            self.anchor_slug = slug or "idea"
        elif not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", self.anchor_slug):
            raise ValueError(f"anchor_slug must match ^[a-z0-9]+(?:-[a-z0-9]+)*$: {self.anchor_slug!r}")
        if self.purpose_brief is None:
            raise ValueError("purpose_brief is required")

        assigned = {assignment.kind for assignment in self.authorities}
        required = {
            AuthorityKind.direction,
            AuthorityKind.input_sufficiency,
            AuthorityKind.voice,
            AuthorityKind.release,
        }
        missing = sorted(kind.value for kind in required - assigned)
        if missing:
            raise ValueError(f"missing required authorities: {', '.join(missing)}")
        return self


CommandPayload = Annotated[
    CommitIdeaPayload
    | RecordExperientialWaiverPayload
    | DeclareInputSufficientPayload
    | AcceptFinalRevisionPayload
    | AuthorizeReleasePayload
    | RecordTrivialEditWaiverPayload
    | RecordQualityWaiverPayload,
    Field(discriminator="type"),
]


class CommandEnvelope(BaseModel):
    schema_version: Literal[1] = 1
    command_type: CommandKind
    aggregate: AggregateRef | None = None
    actor: ActorRef | None = None
    idempotency_key: str = Field(default="", min_length=0)
    expected_version: int = Field(default=0, ge=0)
    payload: CommandPayload

    @model_validator(mode="before")
    @classmethod
    def _coerce_envelope_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "command_type" in d and isinstance(d["command_type"], str):
            if isinstance(d.get("payload"), dict) and "type" not in d["payload"]:
                d["payload"]["type"] = d["command_type"]

        if not d.get("aggregate"):
            idea_id = (
                (d.get("payload") and isinstance(d["payload"], dict) and d["payload"].get("idea_id"))
                or "idea-1"
            )
            d["aggregate"] = {"kind": "idea", "id": str(idea_id)}
        elif isinstance(d["aggregate"], str):
            d["aggregate"] = {"kind": "idea", "id": d["aggregate"]}

        if not d.get("actor"):
            actor_email = (
                d.get("payload")
                and isinstance(d["payload"], dict)
                and d["payload"].get("owners")
                and isinstance(d["payload"]["owners"], list)
                and d["payload"]["owners"][0]
            ) or "operator@example.com"
            d["actor"] = {"subject_id": str(actor_email), "email": str(actor_email)}

        if not d.get("idempotency_key"):
            import uuid

            d["idempotency_key"] = f"cmd-{uuid.uuid4().hex[:12]}"

        return d

    @model_validator(mode="after")
    def _payload_matches_command(self) -> CommandEnvelope:
        if self.command_type.value != self.payload.type:
            raise ValueError("command_type does not match payload type")
        if self.aggregate is None:
            raise ValueError("aggregate is required")
        if self.actor is None:
            raise ValueError("actor is required")
        if not self.idempotency_key:
            raise ValueError("idempotency_key is required")
        return self


class Rejection(BaseModel):
    code: str
    message: str
    current_version: int | None = None
    requirements: list[str] = Field(default_factory=list)


class CommandReceipt(MongoModel):
    command_type: CommandKind
    aggregate: AggregateRef
    actor: ActorRef
    idempotency_key: str
    payload_digest: str
    outcome: Literal["applied", "rejected"]
    version_before: int | None = None
    version_after: int | None = None
    applied_at: datetime | None = None
    rejected_at: datetime | None = None
    rejection: Rejection | None = None
    result_refs: dict[str, object] = Field(default_factory=dict)
    created_task_ids: list[str] = Field(default_factory=list)
    created_obligation_ids: list[str] = Field(default_factory=list)


class ContentProject(MongoModel):
    version: int = 1
    title: str
    originating_idea_id: str
    purpose_brief: PurposeBrief
    authorities: list[AuthorityAssignment]
    default_voice_id: str
    evidence_base_id: str
    disposition: Disposition = Disposition.active
    suspension: Suspension = Suspension.running
    visibility: Visibility = Visibility.visible
    epoch: int = 1
    council_policy: CouncilPolicy = Field(default_factory=CouncilPolicy)
    research_policy: ResearchPolicy = Field(default_factory=ResearchPolicy)


class ProjectPiece(MongoModel):
    version: int = 1
    content_project_id: str
    role: PieceRole
    title: str
    slug: str
    voice_id: str
    destination: str
    source_anchor_revision_id: str | None = None
    # Child of the anchor by default; promoted to a top-level Piece only when the derivative
    # needs its own owner/review/publish state (cmw-lesson-lineage-impl). Ignored on anchors.
    lineage: DerivativeLineage = DerivativeLineage.child
    promoted_piece_id: str | None = None
    disposition: Disposition = Disposition.active
    suspension: Suspension = Suspension.running
    visibility: Visibility = Visibility.visible
    epoch: int = 1

    @model_validator(mode="after")
    def _derivative_has_anchor_source(self) -> ProjectPiece:
        if self.role == PieceRole.derivative and not self.source_anchor_revision_id:
            raise ValueError("a derivative Piece requires its source Anchor Revision")
        if self.role == PieceRole.anchor and self.source_anchor_revision_id:
            raise ValueError("an Anchor Piece cannot have a source Anchor Revision")
        return self


class ObligationSubject(BaseModel):
    kind: Literal["content-project", "piece", "evidence-base", "revision", "release"]
    id: str


class ObligationResolution(BaseModel):
    actor: ActorRef
    decision: str
    rationale: str | None = None
    resolved_at: datetime


class HumanObligation(MongoModel):
    content_project_id: str
    kind: HumanObligationKind
    assignee: ActorRef
    authority: AuthorityKind
    subject: ObligationSubject
    state: HumanObligationState = HumanObligationState.open
    resolution: ObligationResolution | None = None


class AvailableCommand(BaseModel):
    command_type: CommandKind
    subject: ObligationSubject
    enabled: bool
    reason: str
    requirements: list[str] = Field(default_factory=list)
    authority_required: AuthorityKind | None = None
    assigned_actor: ActorRef | None = None
    expected_version: int
    irreversible: bool = False


class PieceWorkspaceItem(BaseModel):
    id: str
    version: int
    role: PieceRole
    title: str
    destination: str
    voice_id: str
    disposition: Disposition
    suspension: Suspension
    visibility: Visibility
    derived_phase: PiecePhase
    phase_reason: str
    source_anchor_revision_id: str | None = None
    lineage: DerivativeLineage = DerivativeLineage.child
    promoted_piece_id: str | None = None
    artifact_readiness: dict[str, ArtifactReadiness]
    active_work: list[object] = Field(default_factory=list)


class ConsistencyWarning(BaseModel):
    code: str
    severity: Literal["warning", "error"]
    explanation: str


class DeskProjection(BaseModel):
    """The signed-in operator's current obligations and projects."""

    open_obligations: list[HumanObligation] = Field(default_factory=list)
    active_work: list[ContentProject] = Field(default_factory=list)
    released_projects: list[ContentProject] = Field(default_factory=list)


class ProjectWorkspaceView(BaseModel):
    schema_version: Literal[1] = 1
    generated_at: datetime
    project: ContentProject
    derived_phase: ProjectPhase
    phase_reason: str
    available_commands: list[AvailableCommand]
    open_obligations: list[HumanObligation]
    piece_family: list[PieceWorkspaceItem]
    artifact_readiness: dict[str, ArtifactReadiness]
    research: ResearchGateView | None = None
    release: ReleaseGateView | None = None
    quality_waiver: QualityWaiver | None = None
    active_work: list[object] = Field(default_factory=list)
    consistency_warnings: list[ConsistencyWarning] = Field(default_factory=list)
