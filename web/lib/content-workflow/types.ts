export interface ActorRef {
  subject_id?: string;
  email?: string;
  name?: string;
  display_name?: string;
}

export interface AggregateRef {
  /** "idea" for commit-idea; "content-project" for project-scoped commands recorded after the
   * project exists (record-experiential-waiver). Mirrors the backend `AggregateRef.kind`. */
  kind: "idea" | "content-project";
  id: string;
}

export interface AuthorityInput {
  kind: string;
  assignee: ActorRef;
  scope?: string;
}

export interface CouncilPolicy {
  mode?: "bounded-autonomy";
  quality_bar?: number;
  iteration_ceiling?: number;
  cost_ceiling_usd?: number;
  plateau_policy?: string;
  gaps_require_human?: true;
  clearances_require_human?: true;
}

export interface CommitIdeaPayload {
  type?: "commit-idea";
  project_title: string;
  purpose_brief: PurposeBrief;
  default_voice_id: string;
  authorities: AuthorityInput[];
  anchor_title: string;
  anchor_slug: string;
  anchor_destination: string;
  council_policy?: CouncilPolicy;
}

export interface RecordExperientialWaiverPayload {
  type?: "record-experiential-waiver";
  content_project_id: string;
  reason: string;
  experience_basis?: string;
}

export interface DeclareInputSufficientPayload {
  type?: "declare-input-sufficient";
  content_project_id: string;
  reason?: string | null;
}

export interface RecordQualityWaiverPayload {
  type?: "record-quality-waiver";
  content_project_id: string;
  reason: string;
  policy_version?: string;
  quality_bar?: number | null;
  iteration_ceiling?: number | null;
  cost_ceiling_usd?: number | null;
}

export interface AcceptFinalRevisionPayload {
  type?: "accept-final-revision";
  content_project_id: string;
  piece_id: string;
  revision: string;
}

export interface AuthorizeReleasePayload {
  type?: "authorize-release";
  content_project_id: string;
  piece_id: string;
}

export interface RecordTrivialEditWaiverPayload {
  type?: "record-trivial-edit-waiver";
  content_project_id: string;
  piece_id: string;
  from_revision: string;
  to_revision: string;
  reason: string;
}

export interface CommandEnvelope {
  schema_version?: 1;
  command_type: CommandKind;
  aggregate: AggregateRef;
  actor: ActorRef;
  idempotency_key: string;
  expected_version: number;
  payload:
    | CommitIdeaPayload
    | RecordExperientialWaiverPayload
    | DeclareInputSufficientPayload
    | AcceptFinalRevisionPayload
    | AuthorizeReleasePayload
    | RecordTrivialEditWaiverPayload
    | RecordQualityWaiverPayload;
}

export interface CommandReceipt {
  id?: string;
  command_type: CommandKind;
  aggregate: AggregateRef;
  actor: ActorRef;
  idempotency_key: string;
  payload_digest: string;
  outcome: "applied" | "rejected";
  version_before?: number | null;
  version_after?: number | null;
  applied_at?: string | null;
  rejected_at?: string | null;
  rejection?: {
    code: string;
    message: string;
    current_version?: number | null;
    requirements?: string[];
  } | null;
  result_refs?: Record<string, unknown>;
  created_task_ids?: string[];
  created_obligation_ids?: string[];
}

/**
 * Mirrors `agents/app/content_workflow/models.py`'s `HumanObligationKind` 1:1 — the backend enum
 * is ground truth; every literal here is the exact wire VALUE the backend serializes (hyphenated,
 * per that enum's `str, Enum` values), not the Python member name.
 *
 * This union was hand-written in PR #120 against a guessed contract never checked against the
 * real backend enum (built in PR #117) — see `cmw-fix-workflow-contract-drift`'s launch brief for
 * the full diagnosis. Fixed here to the real 14-member backend set for every value with an
 * unambiguous backend counterpart: `answer_interview` / `close_review_round` / `resolve_lesson`
 * were guessed names for what are really `answer-question` / `close-review` / `decide-lesson`
 * below (same intent, different name — not just a hyphen/underscore mismatch), and
 * `confirm_input_sufficiency` / `accept_final_revision` / `authorize_release` needed only their
 * literal string reformatted to the real hyphenated wire value.
 *
 * `"recover_failure"` and `"pick_idea"` are LEFT AS-IS below (not renamed, not removed) — they
 * have no backend `HumanObligationKind` counterpart at all (confirmed: no member of the real
 * 14-value backend enum matches either by name or by intent) and are pure frontend inventions.
 * Per this ticket's launch brief, a value with no real backend counterpart is a genuine product
 * decision (build the backend kind for real, or drop the frontend concept), not a pure bug fix —
 * flagged via this ticket's `needs-decision` status line and left untouched pending Hendo's call.
 * Neither is currently compared/branched on anywhere. User-facing copy goes through
 * `lib/content-workflow/labels.ts` (`obligationKindLabel`) so a raw kind never greets a teammate.
 */
export type HumanObligationKind =
  | "choose-direction"
  | "answer-question"
  | "approve-contribution"
  | "confirm-input-sufficiency"
  | "resolve-gap"
  | "correct-claim"
  | "grant-clearance"
  | "close-review"
  | "revise-final"
  | "accept-final-revision"
  | "authorize-release"
  | "decide-lesson"
  | "decide-abandonment"
  | "attention-required"
  | "recover_failure"
  | "pick_idea";

export type HumanObligationState = "open" | "resolved" | "declined" | "superseded";

export type ObligationSubjectKind =
  | "content-project"
  | "piece"
  | "evidence-base"
  | "revision"
  | "release";

export interface ObligationSubject {
  kind: ObligationSubjectKind;
  id: string;
}

export interface ObligationResolution {
  actor: ActorRef;
  decision: string;
  rationale?: string;
  resolved_at: string;
}

export interface HumanObligation {
  id: string;
  content_project_id: string;
  kind: HumanObligationKind;
  assignee: ActorRef;
  authority: string;
  subject: ObligationSubject;
  state: HumanObligationState;
  resolution?: ObligationResolution;
}

/**
 * Mirrors `agents/app/content_workflow/models.py`'s `CommandKind` 1:1 — same discipline as
 * `HumanObligationKind` above: every literal is the real backend wire VALUE (hyphenated), not a
 * guessed name/format. Reconciled in `cmw-fix-workflow-contract-drift` (PR #136):
 * `"commit_idea"` -> `"commit-idea"` (pure format fix — same intent, wrong separator);
 * `"declare_sufficiency"` -> `"declare-input-sufficient"` and `"accept_final"` ->
 * `"accept-final-revision"` (pure renames — different name, unambiguous same intent);
 * `"authorize_release"` already matched the backend NAME and now also matches its real
 * hyphenated VALUE.
 *
 * The remaining orphans were reconciled in `cmw-reconcile-command-gaps` so this union is a
 * 1:1 mirror of the backend enum (seven members after `cmw-release-semantics-impl` added
 * `record-trivial-edit-waiver`):
 *   - `"record-experiential-waiver"` and `"commission-derivative"` are real backend commands
 *     (both are genuinely sent over the wire in `inspect()`'s `available_commands`) that had no
 *     frontend literal — added here so a typed `ProjectWorkspaceView.available_commands` payload
 *     cannot carry a `command_type` this union denies. Neither has an executing UI flow yet, but
 *     neither does any other non-`commit-idea` command (the backend itself rejects those in
 *     `submit()` with "not implemented yet"). Type-contract presence is the established
 *     convention from PR #136.
 *   - `"accept_lesson"` / `"reject_lesson"` were frontend-only inventions with no backend
 *     `CommandKind` counterpart (lessons are decided via the separate `decide-lesson`
 *     `HumanObligationKind` above, never a submitted command) and dead code — never constructed,
 *     compared, or rendered anywhere in `web/`. Removed here rather than implemented.
 *
 * A compile-time canary in `types.test.ts` locks this union to the backend enum values — run
 * `npm run typecheck` in `web/` to enforce it (vitest itself does not type-check).
 */
export type CommandKind =
  | "commit-idea"
  | "declare-input-sufficient"
  | "record-experiential-waiver"
  | "commission-derivative"
  | "accept-final-revision"
  | "authorize-release"
  | "record-trivial-edit-waiver"
  | "record-quality-waiver";

export interface AvailableCommand {
  command_type: CommandKind;
  subject: ObligationSubject;
  enabled: boolean;
  reason: string;
  requirements: string[];
  authority_required?: string;
  assigned_actor?: ActorRef;
  expected_version: number;
  irreversible: boolean;
}

export type PieceRole = "anchor" | "derivative";
export type DerivativeLineage = "child" | "promoted";
export type Disposition = "active" | "completed" | "abandoned";
export type Suspension = "running" | "paused";
export type Visibility = "visible" | "archived";

export interface ArtifactReadiness {
  status: string;
  detail?: string;
}

export interface PieceWorkspaceItem {
  id: string;
  version: number;
  role: PieceRole;
  title: string;
  destination: string;
  voice_id: string;
  disposition: Disposition;
  suspension: Suspension;
  visibility: Visibility;
  derived_phase: string;
  phase_reason: string;
  source_anchor_revision_id?: string;
  lineage?: DerivativeLineage;
  promoted_piece_id?: string | null;
  artifact_readiness: Record<string, ArtifactReadiness>;
  active_work: unknown[];
}

export interface ConsistencyWarning {
  code: string;
  severity: "warning" | "error";
  explanation: string;
}

export interface PurposeBrief {
  proposition: string;
  audience: string;
  angle: string;
  desired_outcome: string;
  why_now: string;
  constraints: string[];
}

export interface AuthorityAssignment {
  kind: string;
  assignee: ActorRef;
  scope: string;
  assigned_by: ActorRef;
  assigned_at: string;
}

export interface ContentProject {
  id: string;
  version: number;
  title: string;
  originating_idea_id: string;
  purpose_brief: PurposeBrief;
  authorities: AuthorityAssignment[];
  default_voice_id: string;
  evidence_base_id: string;
  disposition: Disposition;
  suspension: Suspension;
  visibility: Visibility;
  epoch: number;
  research_policy?: ResearchPolicy;
}

export interface ResearchPolicy {
  report_required_by_default: boolean;
  experiential_waiver_allowed: boolean;
  policy_version?: string;
}

/** One sourced fact: statement + where it came from (research-v1). */
export interface ReportFact {
  statement: string;
  source: string;
}

/** One opinion/judgment call, kept strictly apart from facts. */
export interface ReportOpinion {
  statement: string;
  holder?: string | null;
}

/** The first-class research-report artifact (research-v1). */
export interface ResearchReport {
  id?: string;
  content_project_id: string;
  piece_id?: string | null;
  subject: string;
  facts: ReportFact[];
  opinions: ReportOpinion[];
  open_questions: string[];
  submitted_by: ActorRef;
  status?: "current" | "superseded";
  created_at?: string;
}

/** A recorded experiential waiver: actor + reason ARE the audit trail, never silent. */
export interface ExperientialWaiver {
  id?: string;
  content_project_id: string;
  actor: ActorRef;
  reason: string;
  experience_basis?: string | null;
  recorded_at: string;
}

export interface QualityWaiver {
  id?: string;
  content_project_id: string;
  actor: ActorRef;
  reason: string;
  policy_version: string;
  quality_bar?: number | null;
  iteration_ceiling?: number | null;
  cost_ceiling_usd?: number | null;
  recorded_at: string;
}

/** The project's research requirement, projected for operator surfaces. */
export interface ResearchGateView {
  required: boolean;
  satisfied: boolean;
  satisfied_by: "research-report" | "experiential-waiver" | null;
  report: ResearchReport | null;
  waiver: ExperientialWaiver | null;
}

export interface PublicationReleaseView {
  id?: string | null;
  piece_id: string;
  release_number: number;
  revision: string;
  authorized_by_subject_id: string;
  authorized_at: string;
  html_url?: string | null;
  pdf_url?: string | null;
  doc_url?: string | null;
}

/** The AuthorizeRelease gate for one piece (cmw-release-semantics-impl). */
export interface ReleaseGateView {
  piece_id: string;
  accepted_revision?: string | null;
  current_revision?: string | null;
  approval_valid: boolean;
  invalidated: boolean;
  waiver_reason?: string | null;
  releases: PublicationReleaseView[];
  authorize_enabled: boolean;
  reason: string;
}

export interface ProjectWorkspaceView {
  schema_version: 1;
  generated_at: string;
  project: ContentProject;
  derived_phase: string;
  phase_reason: string;
  available_commands: AvailableCommand[];
  open_obligations: HumanObligation[];
  piece_family: PieceWorkspaceItem[];
  artifact_readiness: Record<string, ArtifactReadiness>;
  research?: ResearchGateView | null;
  release?: ReleaseGateView | null;
  quality_waiver?: QualityWaiver | null;
  active_work: unknown[];
  consistency_warnings: ConsistencyWarning[];
}

export interface DeskView {
  open_obligations: HumanObligation[];
  active_work: ContentProject[];
  released_projects: ContentProject[];
}
