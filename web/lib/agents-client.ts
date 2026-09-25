/**
 * Server-side REST client for the Python `agents/` service (docs/design.md §6).
 *
 * This module is imported ONLY from route handlers (the BFF) — never from client components —
 * so `AGENTS_URL` and any future provider keys stay server-side and are never bundled into the
 * browser. The `web/` service is UI + BFF only; it does not run orchestration (D5).
 */

import type { PersonaKind, PersonaListResponse } from "@/lib/brain/types";
import type { DeskView } from "@/lib/content-workflow/types";
import type { DashboardResponse, FailedJobRef } from "@/lib/dashboard/types";
import type {
  Interview,
  MetaCommandResult,
  OpenInterviewInput,
  PersonaAdvanceDirection,
  RespondResult,
  TranscriptTurn,
} from "@/lib/interviews/types";
import type { Narrative, NarrativeCreateInput } from "@/lib/narratives/types";
import type { OracleRunInput, OracleRunResult } from "@/lib/oracle/types";
import type { DerivativeArtifact } from "@/lib/pieces/derivatives";
import type { PieceDetail, RecentPiecesResponse } from "@/lib/pieces/types";
import type {
  MintReviewInput,
  MintReviewResult,
  ReviewPreviewResult,
  ReviewRoundListResponse,
} from "@/lib/review-round/types";
import type {
  MintSpikeFromNarrativeInput,
  PickSpikeInput,
  PickSpikeResponse,
  Spike,
  SpikeListResponse,
} from "@/lib/spikes/types";
import type {
  ClipInInput,
  ClipInResponse,
  RefreshRequestInput,
  RefreshResponse,
  Source,
  SourceCreateInput,
  SourceDeleteResponse,
  SourceListResponse,
  SourceUpdateInput,
} from "@/lib/sources/types";
import type {
  Lesson,
  LessonDecisionInput,
  ProposeLessonsInput,
  ProposeLessonsResult,
  VoiceCommit,
  VoiceFileContentResponse,
  VoiceFileHistoryResponse,
  VoiceFileKey,
  VoiceFileRollbackInput,
  VoiceFileUpdateInput,
  VoiceListResponse,
  VoicePack,
} from "@/lib/voice-kit/types";

// Internal service URL. In docker compose this is the compose service name (`agents`) on its
// fixed internal port; locally it defaults to localhost. NOT a NEXT_PUBLIC_ var → server-only.
const AGENTS_URL = process.env.AGENTS_URL ?? "http://localhost:8000";

/** A non-2xx response from the agents service, carrying its status so BFF routes can pass it
 * through (a 400/404/503 from agents is a client-visible outcome, not an opaque 502). */
export class AgentsRequestError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "AgentsRequestError";
  }
}

export interface AgentsHealth {
  status: string;
  service: string;
  version: string;
}

export interface AgentsStatus {
  service: string;
  environment: string;
  orchestration: string;
  pipeline_stages: string[];
  llm_configured: boolean;
}

/** Provenance for the on-disk brain clone (`HendoCode/content-machine-brain`) — "which brain am I
 * running." `connected: false` means every other field is null (brain_root isn't reachable). */
export interface BrainStatus {
  connected: boolean;
  root: string | null;
  remote_url: string | null;
  commit_sha: string | null;
  commit_date: string | null;
  commit_message: string | null;
}

/** FastAPI's default error body is `{"detail": "..."}`; unwrap it so callers see the plain
 * message rather than a JSON-encoded blob. Falls back to the raw text for non-JSON errors. */
async function errorMessage(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const parsed: unknown = JSON.parse(text);
    if (parsed && typeof parsed === "object" && "detail" in parsed) {
      const detail = (parsed as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
    }
  } catch {
    // not JSON — fall through to the raw text
  }
  return text;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${AGENTS_URL}${path}`, {
    // Always hit the live service; health/status must never be cached.
    cache: "no-store",
    headers: { accept: "application/json" },
  });
  if (!res.ok) {
    throw new AgentsRequestError(res.status, await errorMessage(res));
  }
  return (await res.json()) as T;
}

async function sendJson<T>(path: string, method: "POST" | "PUT" | "PATCH" | "DELETE", body?: unknown): Promise<T> {
  const res = await fetch(`${AGENTS_URL}${path}`, {
    method,
    cache: "no-store",
    headers: { accept: "application/json", "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    throw new AgentsRequestError(res.status, await errorMessage(res));
  }
  return (await res.json()) as T;
}

export function fetchAgentsHealth(): Promise<AgentsHealth> {
  return getJson<AgentsHealth>("/health");
}

export function fetchAgentsStatus(): Promise<AgentsStatus> {
  return getJson<AgentsStatus>("/api/status");
}

export function fetchBrainStatus(): Promise<BrainStatus> {
  return getJson<BrainStatus>("/api/brain/status");
}

/**
 * The shared work queue for the dashboard (Item 3). `viewer` is the signed-in user's email; the
 * agents service uses it only to attribute SEED entities to that user (never a permission filter —
 * authorization is flat), and ignores it entirely once real Mongo work-state exists.
 */
export function fetchDashboard(viewer?: string | null): Promise<DashboardResponse> {
  const qs = viewer ? `?viewer=${encodeURIComponent(viewer)}` : "";
  return getJson<DashboardResponse>(`/api/dashboard${qs}`);
}

/** The signed-in operator's Content Workflow projects and unresolved obligations. */
export function fetchContentWorkflowDesk(assignee?: string | null): Promise<DeskView> {
  const qs = assignee ? `?assignee=${encodeURIComponent(assignee)}` : "";
  return getJson<DeskView>(`/api/content-workflow/desk${qs}`);
}

// --- Source registry (Item 6 / D8): manage what the Oracle reads ------------------------------

export function fetchSources(): Promise<SourceListResponse> {
  return getJson<SourceListResponse>("/api/sources");
}

export function createSource(input: SourceCreateInput): Promise<Source> {
  return sendJson<Source>("/api/sources", "POST", input);
}

export function updateSource(id: string, input: SourceUpdateInput): Promise<Source> {
  return sendJson<Source>(`/api/sources/${encodeURIComponent(id)}`, "PATCH", input);
}

export function retireSource(id: string): Promise<SourceDeleteResponse> {
  return sendJson<SourceDeleteResponse>(`/api/sources/${encodeURIComponent(id)}`, "DELETE");
}

// --- Source connectors (D8): on-demand refresh + credential-free clip-in ----------------------

export function refreshSources(input: RefreshRequestInput): Promise<RefreshResponse> {
  return sendJson<RefreshResponse>("/api/connectors/refresh", "POST", input);
}

export function clipIn(input: ClipInInput): Promise<ClipInResponse> {
  return sendJson<ClipInResponse>("/api/connectors/clip", "POST", input);
}

/**
 * One piece across its whole lifecycle (Item 2/piece-detail screen). `viewer` only shapes the
 * SEED's owner attribution (never a permission filter, §1.17) — the same convention as
 * `fetchDashboard`, so a piece card's link target resolves against a fresh seed call too.
 */
export function fetchPieceDetail(pieceId: string, viewer?: string | null): Promise<PieceDetail> {
  const qs = viewer ? `?viewer=${encodeURIComponent(viewer)}` : "";
  return getJson<PieceDetail>(`/api/pieces/${encodeURIComponent(pieceId)}${qs}`);
}

/** The desk's ~6 most recently active pieces (live work-state; honest empty state when Mongo is
 * unconfigured — never a seed fallback, see `agents/app/pieces.py`'s `/recent` route). */
export function fetchRecentPieces(limit = 6): Promise<RecentPiecesResponse> {
  return getJson<RecentPiecesResponse>(`/api/pieces/recent?limit=${limit}`);
}

/** The three human triggers (D16a/D4/use-case-J) plus the interactive gates the piece-detail
 * screen's stage-contextual action can fire — the exact set `agents/app/orchestration/routes.py`
 * exposes at `POST /api/pieces/{id}/{trigger}`. */
export type PieceTrigger =
  | "enough-input"
  | "reviews-done"
  | "finalize"
  | "capture-lessons"
  | "finish-lessons"
  | "route-to-interview"
  | "pause"
  | "resume"
  | "publish";

export interface PieceStateResult {
  id: string;
  slug: string;
  stage: string;
  failures: FailedJobRef[];
}

/**
 * Fire a stage-contextual trigger (the orchestration state machine, D5). Flat auth: `actor` is
 * attribution only (who gets credited on the Job/Piece), never a permission check — any signed-in
 * employee may fire any legal trigger (§1.17). The agents service maps illegal state/config as
 * 404/409/501/503; those surface here as `AgentsRequestError` so the BFF/UI can show the real
 * reason.
 */
export function triggerPiece(
  pieceId: string,
  trigger: PieceTrigger,
  actor?: string | null,
): Promise<PieceStateResult> {
  const qs = actor ? `?actor=${encodeURIComponent(actor)}` : "";
  return sendJson<PieceStateResult>(
    `/api/pieces/${encodeURIComponent(pieceId)}/${trigger}${qs}`,
    "POST",
  );
}

// --- Review round (screen 04 / D4/D11; open-decisions Item 7): mint + the assisted preview -----

/** Mint an internal/external review Doc from the piece's current revision (D4/D11). */
export function mintReviewRound(pieceId: string, input: MintReviewInput): Promise<MintReviewResult> {
  return sendJson<MintReviewResult>(
    `/api/pieces/${encodeURIComponent(pieceId)}/review/mint`,
    "POST",
    input,
  );
}

/** The assisted "reviews done" ingest preview for the piece's currently open review round — a
 * human sanity-checks the agent's reading of the comments before "reviews done" actually fires. */
export function fetchReviewPreview(pieceId: string): Promise<ReviewPreviewResult> {
  return getJson<ReviewPreviewResult>(`/api/pieces/${encodeURIComponent(pieceId)}/review/preview`);
}

/** List every review round for a piece, ascending — the round is the primary REST resource
 * (cmw-review-round-ux-impl), the Doc is a child link inside each round. */
export function fetchReviewRounds(pieceId: string): Promise<ReviewRoundListResponse> {
  return getJson<ReviewRoundListResponse>(
    `/api/pieces/${encodeURIComponent(pieceId)}/review/rounds`,
  );
}

// --- Voice kit (screen 11 / D12): view/edit/rollback Git-backed voice packs -------------------

export function fetchVoices(): Promise<VoiceListResponse> {
  return getJson<VoiceListResponse>("/api/voices");
}

export function fetchVoicePack(slug: string): Promise<VoicePack> {
  return getJson<VoicePack>(`/api/voices/${encodeURIComponent(slug)}`);
}

export function fetchVoiceFileHistory(slug: string, fileKey: VoiceFileKey): Promise<VoiceFileHistoryResponse> {
  return getJson<VoiceFileHistoryResponse>(
    `/api/voices/${encodeURIComponent(slug)}/files/${fileKey}/history`,
  );
}

export function fetchVoiceFileAt(
  slug: string,
  fileKey: VoiceFileKey,
  sha: string,
): Promise<VoiceFileContentResponse> {
  return getJson<VoiceFileContentResponse>(
    `/api/voices/${encodeURIComponent(slug)}/files/${fileKey}/at/${encodeURIComponent(sha)}`,
  );
}

/** Edit + commit one voice-pack file (D12: a human edit; the machine never self-commits). */
export function updateVoiceFile(
  slug: string,
  fileKey: VoiceFileKey,
  input: VoiceFileUpdateInput,
): Promise<VoiceCommit> {
  return sendJson<VoiceCommit>(
    `/api/voices/${encodeURIComponent(slug)}/files/${fileKey}`,
    "PUT",
    input,
  );
}

/** Roll a voice-pack file back to an earlier Git revision — a new, attributable forward commit. */
export function rollbackVoiceFile(
  slug: string,
  fileKey: VoiceFileKey,
  input: VoiceFileRollbackInput,
): Promise<VoiceCommit> {
  return sendJson<VoiceCommit>(
    `/api/voices/${encodeURIComponent(slug)}/files/${fileKey}/rollback`,
    "POST",
    input,
  );
}

// --- Lessons loop (D12; domain model §1.18): the proposed-lessons accept/edit/reject gate ------

/** Diff the machine's final draft against `published_content` and propose deduped per-voice
 * lessons (Opus tier) — the step that actually generates the first batch a human then
 * accepts/edits/rejects. Only legal while the piece is in the `lessons` stage. */
export function proposeLessons(
  pieceId: string,
  input: ProposeLessonsInput,
): Promise<ProposeLessonsResult> {
  return sendJson<ProposeLessonsResult>(
    `/api/lessons/${encodeURIComponent(pieceId)}/propose`,
    "POST",
    input,
  );
}

/** Pending proposals awaiting the D12 gate, optionally narrowed to one voice. */
export function fetchPendingLessons(voice?: string | null): Promise<Lesson[]> {
  const qs = voice ? `?voice=${encodeURIComponent(voice)}` : "";
  return getJson<Lesson[]>(`/api/lessons/pending${qs}`);
}

/** The D12 accept gate: commits the (optionally edited) rule to Git, flips Mongo to accepted. */
export function acceptLesson(lessonId: string, input: LessonDecisionInput): Promise<Lesson> {
  return sendJson<Lesson>(`/api/lessons/${encodeURIComponent(lessonId)}/accept`, "POST", input);
}

/** The D12 reject gate: marks the proposal rejected. Never touches Git. */
export function rejectLesson(lessonId: string, input: LessonDecisionInput): Promise<Lesson> {
  return sendJson<Lesson>(`/api/lessons/${encodeURIComponent(lessonId)}/reject`, "POST", input);
}

export interface LessonBatchResult {
  decided: Lesson[];
  errors: { id: string; error: string }[];
}

export function decideLessonsBatch(
  action: "accept" | "reject",
  lessonIds: string[],
  input: { actor?: string | null; rule_texts?: Record<string, string> } = {},
): Promise<LessonBatchResult> {
  return sendJson<LessonBatchResult>(`/api/lessons/batch`, "POST", {
    action,
    lesson_ids: lessonIds,
    ...input,
  });
}

export interface LessonPreview {
  lesson_id: string;
  path: string;
  before: string;
  after: string;
  rule_text: string;
}

export function fetchLessonPreview(
  lessonId: string,
  ruleText?: string | null,
): Promise<LessonPreview> {
  const qs = ruleText ? `?rule_text=${encodeURIComponent(ruleText)}` : "";
  return getJson<LessonPreview>(`/api/lessons/${encodeURIComponent(lessonId)}/preview${qs}`);
}

// --- Interview engine (D5-context-assembly §5): serial personas, D6 classification, transcript --

/** The full ~10-persona interviewer roster (§1.2) — for the persona menu's done/active/off state. */
export function fetchInterviewerPersonas(): Promise<string[]> {
  return getJson<string[]>("/api/personas/interviewers");
}

export function fetchInterview(interviewId: string): Promise<Interview> {
  return getJson<Interview>(`/api/interviews/${encodeURIComponent(interviewId)}`);
}

/** Generate (Opus) and persist the active persona's next question — one question per turn. */
export function requestNextQuestion(interviewId: string): Promise<Interview> {
  return sendJson<Interview>(
    `/api/interviews/${encodeURIComponent(interviewId)}/next-question`,
    "POST",
  );
}

/** Classify (Sonnet, D6) and route the interviewee's free-form input into the bounded op set. */
export function respondToInterview(interviewId: string, text: string): Promise<RespondResult> {
  return sendJson<RespondResult>(`/api/interviews/${encodeURIComponent(interviewId)}/respond`, "POST", {
    text,
  });
}

/** Move the active persona forward/back through the roster — pure index arithmetic, with no
 * classifier call and no pending-question gate (unlike {@link respondToInterview}). */
export function advancePersona(
  interviewId: string,
  direction: PersonaAdvanceDirection,
): Promise<MetaCommandResult> {
  return sendJson<MetaCommandResult>(
    `/api/interviews/${encodeURIComponent(interviewId)}/advance-persona`,
    "POST",
    { direction },
  );
}

/** Flip the interview to complete — a signal, never the draft trigger (D16a). */
export function markInterviewComplete(interviewId: string): Promise<Interview> {
  return sendJson<Interview>(
    `/api/interviews/${encodeURIComponent(interviewId)}/mark-complete`,
    "POST",
  );
}

/** Open a new Interview session on a piece (initial, or a council-spawned gap interview) — the
 * kickoff flow's (screen 6 steps 3-5) "assign expert + pre-selected personas" call. */
export function openInterview(pieceId: string, input: OpenInterviewInput): Promise<Interview> {
  return sendJson<Interview>(`/api/pieces/${encodeURIComponent(pieceId)}/interviews`, "POST", input);
}

/** The sacred, piece-scoped transcript (D16b), pre-parsed into turns. */
export function fetchTranscriptTurns(pieceId: string): Promise<TranscriptTurn[]> {
  return getJson<TranscriptTurn[]>(`/api/pieces/${encodeURIComponent(pieceId)}/transcript/turns`);
}

/** The interviewee's own edit of a previously stored answer (D16b) — splices in place. Requires
 * the id of the interview surface the edit is being made from: the agents side refuses the write
 * once *that* interview is complete (read-only, even though the transcript itself is piece-scoped
 * and shared across a piece's interviews). */
export function editTranscriptAnswer(
  pieceId: string,
  turnId: string,
  interviewId: string,
  text: string,
): Promise<TranscriptTurn> {
  return sendJson<TranscriptTurn>(
    `/api/pieces/${encodeURIComponent(pieceId)}/transcript/turns/${encodeURIComponent(turnId)}`,
    "POST",
    { text, interview_id: interviewId },
  );
}

/** Regenerate the "here's what I heard" recap over a (possibly just-edited) stored turn. */
export function recapTranscriptTurn(pieceId: string, turnId: string): Promise<{ recap: string }> {
  return sendJson<{ recap: string }>(
    `/api/pieces/${encodeURIComponent(pieceId)}/transcript/turns/${encodeURIComponent(turnId)}/recap`,
    "POST",
  );
}

// --- Read-only Git-brain persona listing (kickoff persona picker; screen 6 step 4) --------------
//
// Distinct from `fetchInterviewerPersonas` above: that one is hard-coded to the interviewer kind
// for the interview surface's persona menu; this one is generic over kind (interviewer | editor)
// for the spike-kickoff and narrative-run screens' selects.

export function fetchPersonas(kind: PersonaKind = "interviewer"): Promise<PersonaListResponse> {
  return getJson<PersonaListResponse>(`/api/personas?kind=${encodeURIComponent(kind)}`);
}

// --- Spikes & Vault (§1.6/§1.7, D15) — the browser + the pick hand-off -------------------------

export function fetchSpikes(): Promise<SpikeListResponse> {
  return getJson<SpikeListResponse>("/api/spikes");
}

export function fetchSpike(spikeId: string): Promise<Spike> {
  return getJson<Spike>(`/api/spikes/${encodeURIComponent(spikeId)}`);
}

/** Kickoff steps 1-2 (screen 6): pick the spike and create its Piece in one call. */
export function pickSpike(spikeId: string, input: PickSpikeInput): Promise<PickSpikeResponse> {
  return sendJson<PickSpikeResponse>(
    `/api/spikes/${encodeURIComponent(spikeId)}/pick`,
    "POST",
    input,
  );
}

/** The "new piece from my own idea" fast path (cmw-narrative-first-entry-point): mint a Spike
 * straight from a Narrative, no Oracle ranking run, no ranked-spikes review table. */
export function mintSpikeFromNarrative(
  input: MintSpikeFromNarrativeInput,
): Promise<Spike> {
  return sendJson<Spike>("/api/spikes/from-narrative", "POST", input);
}

// --- Narrative (§1.5) — Oracle Entry B's seed ---------------------------------------------------

export function createNarrative(input: NarrativeCreateInput): Promise<Narrative> {
  return sendJson<Narrative>("/api/narratives", "POST", input);
}

/** Read a Narrative back — the ONLY way to see a spoken narrative's full `seed_text` again once
 * the Radar page it was typed on has moved on (cmw-first-run-ux-batch item 6). `agents/` already
 * exposes `GET /api/narratives/{id}`; this was the missing web/ half. */
export function fetchNarrative(narrativeId: string): Promise<Narrative> {
  return getJson<Narrative>(`/api/narratives/${encodeURIComponent(narrativeId)}`);
}

// --- Oracle (§1.8) — the on-demand run entrypoint -----------------------------------------------

export function runOracle(input: OracleRunInput): Promise<OracleRunResult> {
  return sendJson<OracleRunResult>("/api/oracle/run", "POST", input);
}

// --- Finalize (screen 10 / D13): the "finalize" trigger, with selectable output formats --------

/**
 * The "finalize" human trigger (use case J; D13), with an optional selectable subset of output
 * formats (`html`/`pdf`/`doc`) — the one trigger whose body carries more than plain attribution.
 * `formats` omitted/`null` takes the finalize step's own default (all three formats).
 */
export function finalizePiece(
  pieceId: string,
  formats: string[] | null | undefined,
  actor?: string | null,
): Promise<PieceStateResult> {
  const qs = actor ? `?actor=${encodeURIComponent(actor)}` : "";
  return sendJson<PieceStateResult>(
    `/api/pieces/${encodeURIComponent(pieceId)}/finalize${qs}`,
    "POST",
    { formats: formats ?? null },
  );
}

// --- Archive (triage at scale) — a dashboard-visibility flag, orthogonal to the stage machine --
//
// Deliberately NOT `PieceTrigger`/`triggerPiece`: archiving isn't a state-machine edge (it works
// regardless of the piece's current stage, including the terminal `published` stage), so it gets
// its own dedicated endpoint, mirroring `finalizePiece`'s shape rather than the generic trigger.

export interface PieceTitleUpdateResult {
  id: string;
  slug: string;
  title: string | null;
  updated_at: string | null;
}

export interface PieceArchiveResult {
  id: string;
  slug: string;
  archived_at: string | null;
}

/** Hide a piece from the dashboard queue. Reversible (see {@link unarchivePiece}) and otherwise
 * changes nothing about the piece — no job/permission/asset side effects. */
export function archivePiece(pieceId: string): Promise<PieceArchiveResult> {
  return sendJson<PieceArchiveResult>(`/api/pieces/${encodeURIComponent(pieceId)}/archive`, "POST");
}

/** Restore a piece to the dashboard queue. */
export function unarchivePiece(pieceId: string): Promise<PieceArchiveResult> {
  return sendJson<PieceArchiveResult>(
    `/api/pieces/${encodeURIComponent(pieceId)}/unarchive`,
    "POST",
  );
}

/** Update a piece's title (dashboard rename). */
export function updatePieceTitle(
  pieceId: string,
  title: string | null,
): Promise<PieceTitleUpdateResult> {
  return sendJson<PieceTitleUpdateResult>(
    `/api/pieces/${encodeURIComponent(pieceId)}/title`,
    "POST",
    { title },
  );
}

export function fetchDerivatives(pieceId: string): Promise<DerivativeArtifact[]> {
  return getJson<DerivativeArtifact[]>(`/api/pieces/${encodeURIComponent(pieceId)}/derivatives`);
}

export function createDerivative(
  pieceId: string,
  input: { destination: string; title?: string | null },
): Promise<DerivativeArtifact> {
  return sendJson<DerivativeArtifact>(
    `/api/pieces/${encodeURIComponent(pieceId)}/derivatives`,
    "POST",
    input,
  );
}

export function promoteDerivative(
  pieceId: string,
  artifactId: string,
  input: { owner?: string | null; actor?: string | null } = {},
): Promise<DerivativeArtifact> {
  return sendJson<DerivativeArtifact>(
    `/api/pieces/${encodeURIComponent(pieceId)}/derivatives/${encodeURIComponent(artifactId)}/promote`,
    "POST",
    input,
  );
}

export { AGENTS_URL };
