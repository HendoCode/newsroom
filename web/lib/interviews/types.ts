/**
 * Interview-engine domain types (cmw-ui-wireframes screen 3; domain model §1.12; D5-context-
 * assembly §5; D6; D16a/D16b).
 *
 * Mirror the agents `agents/app/interview/routes.py` wire contract 1:1 (snake_case), the same
 * no-mapping-layer convention `lib/pieces/types.ts` established for piece-detail.
 */

export type InterviewStatus = "open" | "complete";

export interface Interview {
  id: string;
  piece_id: string;
  status: InterviewStatus;
  interviewer_personas: string[];
  current_persona_index: number;
  current_question: string | null;
  assigned_expert: string | null;
  about: string | null;
  is_gap_interview: boolean;
}

/** The request body for `POST /api/pieces/{id}/interviews` — the kickoff flow's (screen 6 steps
 * 3-5) "assign expert + pre-selected personas" call. */
export interface OpenInterviewInput {
  interviewer_personas: string[];
  assigned_expert?: string | null;
  about?: string | null;
  is_gap_interview?: boolean;
}

/** One parsed turn of the sacred, piece-scoped transcript (D16b) — `GET .../transcript/turns`. */
export interface TranscriptTurn {
  id: string;
  persona: string;
  question: string;
  answer: string;
  research_derived: boolean;
}

/** The D6 bounded meta-command vocabulary (context-assembly report §5b). */
export type MetaCommand =
  | "add-interviewer"
  | "drop-interviewer"
  | "restart"
  | "stop-for-the-day"
  | "go-back"
  | "skip"
  | "switch-piece"
  | "other";

/** `POST .../advance-persona`'s bounded direction — the roster-navigation subset of
 * {@link MetaCommand} that is pure index arithmetic (no classifier call, no pending-question
 * gate), unlike every other meta-command, which only routes through `respondToInterview`. */
export type PersonaAdvanceDirection = "skip" | "go-back";

export interface AnsweredTurn {
  op: "answer";
  turn: TranscriptTurn;
  /** The "here's what I heard" confirmation view (D16b) — read-only, never re-written to the
   * transcript; a caller must never mistake this for the stored answer. */
  recap: string;
}

export interface ResearchResult {
  op: "research-this";
  answer: string;
  /** The pending question, unchanged ("borrowed time, then returned") — never `null` while a
   * question was pending when research was requested. */
  resume_question: string | null;
}

export interface MetaCommandResult {
  op: "meta-command";
  command: MetaCommand;
  /** Whether this engine enacted the command. `false` means recorded, not silently dropped (D6) —
   * e.g. an unknown persona name, or a cross-piece `switch-piece` outside this engine's remit. */
  handled: boolean;
  note: string | null;
}

export interface TangentResult {
  op: "tangent";
  /** The Vault Spike id the tangent was parked to — nothing is ever thrown away. */
  spike_id: string;
}

/** The D6 bounded op set every free-form composer submission classifies into — exactly the four
 * ops the wireframe surfaces as chips: answer / research-this / meta-command / tangent. */
export type RespondResult = AnsweredTurn | ResearchResult | MetaCommandResult | TangentResult;
