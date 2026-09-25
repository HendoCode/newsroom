/**
 * Dashboard domain types — the shared work-queue model (docs/design.md §3; cmw-open-decisions
 * report §Item-3; cmw-ui-wireframes screen 1).
 *
 * These mirror the agents `/api/dashboard` wire contract 1:1 (snake_case, matching the existing
 * `AgentsStatus` contract in `lib/agents-client.ts`) so there is no mapping layer. The queue is a
 * single shared list of pieces + spikes; tabs are saved FILTERS over it (`lib/dashboard/filters`),
 * never permission scopes, and "needs my action" (`lib/dashboard/needs-my-action`) is an
 * attribution-only convenience predicate — NEVER a gate (§1.17, flat authorization).
 */

/**
 * The per-piece state machine (domain model §1.9), now 10 states: `released` is the terminal
 * ship state (HITL AuthorizeRelease from `finalized`). `published` is accepted as a legacy wire
 * alias for the same state (backend coerces it on read). See `agents/app/models/piece.py`.
 */
export type PieceStage =
  | "interviewing"
  | "drafting"
  | "council"
  | "review"
  | "incorporating"
  | "finalizing"
  | "finalized"
  | "lessons"
  | "paused"
  | "released"
  | "published";

/** Spike pool status (domain model §1.6). */
export type SpikeStatus = "proposed" | "picked" | "in-flight" | "vaulted";

/** A failed/stuck batch job surfaced against a piece (Item 4: failures flag, never roll back). */
export interface FailedJobRef {
  type: string;
  code: string;
  message: string;
  /** Attribution: powers the "you triggered this" predicate branch. Never a gate. */
  triggered_by: string | null;
  retryable: boolean;
  cost: number;
}

/** An open interview session on a piece, with the expert it is assigned to (attribution). */
export interface OpenInterviewRef {
  interview_id: string;
  expert: string | null;
}

/** One card in the shared queue: either a Piece across its lifecycle or a pooled Spike. */
export interface QueueItem {
  kind: "piece" | "spike";
  id: string;
  title: string;
  voice: string | null;

  stage: PieceStage | null;
  spike_status: SpikeStatus | null;

  owner: string | null;
  assigned_experts: string[];
  creator: string | null;

  council_aggregate: number | null;
  open_gaps: number;
  open_clearances: number;
  review_round: number | null;

  open_interviews: OpenInterviewRef[];
  has_complete_interview: boolean;
  failed_job: FailedJobRef | null;
  lessons_proposed: number;
  spike_assigned: boolean;

  // Staleness triage (cmw-staleness-timestamps): `updated_at` is the last write of ANY kind
  // (including a batch job completing with no human involved); `last_human_touch_at` is the
  // narrower "a person actually acted on this" signal — never set by a machine-only write. `null`
  // for a spike card (human-touch tracking only exists for pieces so far).
  updated_at: string | null;
  last_human_touch_at: string | null;

  // Provenance (cmw-brain-pieces-visibility): true when this card's Piece was registered from a
  // brain-authored drafts/ folder by the brain-draft sync rather than created through the
  // pipeline. Optional because client-side fixtures predate it; the live wire always sends it
  // (backend default false). Never set on a spike card.
  brain_synced?: boolean;
}

export interface DashboardResponse {
  /** "seed" = built-in placeholder work-state; "store" = real Mongo work-state (D3). */
  source: "store" | "seed";
  items: QueueItem[];
}
