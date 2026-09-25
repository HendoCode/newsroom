/**
 * Spikes & Vault domain types (domain model §1.6/§1.7; D15; cmw-ui-wireframes screen 5).
 *
 * Mirror the agents `/api/spikes` wire contract 1:1 (snake_case), matching the `lib/sources/types.ts`
 * / `lib/dashboard/types.ts` convention — no mapping layer.
 */

export type SpikeStatus = "proposed" | "picked" | "in-flight" | "vaulted";

/** Where a spike came from (§1.6). A parked tangent (D6) has `kind: "tangent"` and no score. */
export type SpikeOriginKind = "oracle-run" | "narrative" | "tangent";

export interface SpikeOrigin {
  kind: SpikeOriginKind;
  ref: string | null;
}

/** Audience/angle intent (§1.5/§5-Q5), carried from a seeding Narrative onto the Spike/Piece. */
export interface DistributionIntent {
  audience: string | null;
  angle: string | null;
}

export interface Spike {
  id: string;
  headline: string;
  status: SpikeStatus;
  convergence_score: number | null;
  creator: string; // attribution — never a lock (D15)
  origin: SpikeOrigin;
  source_ids: string[];
  customer_partner: string | null;
  outcome_metric: string | null;
  rank_rationale: string | null;
  convergence_note: string | null;
  intent: DistributionIntent | null;
  piece_id: string | null; // set once picked
  updated_at: string | null;
}

export interface SpikeListResponse {
  /** "seed" = the dashboard's built-in placeholder spikes; "store" = real Mongo work-state. */
  source: "store" | "seed";
  items: Spike[];
}

/** Kickoff steps 1-2 (screen 6): pick the spike, create its Piece, AND open its first Interview,
 * all in one all-or-nothing call (cmw-piece-interviewing-without-interview) — a piece must never
 * sit in `interviewing` with no Interview to conduct. */
export interface PickSpikeInput {
  voice: string;
  slug?: string;
  title?: string;
  target?: string;
  owner?: string | null;
  interviewer_personas: string[];
  assigned_expert?: string | null;
  about?: string | null;
}

export interface PickSpikeResponse {
  piece_id: string;
  slug: string;
  spike: Spike;
  interview_id: string;
}

/** The "new piece from my own idea" fast path (Option B, cmw-narrative-first-entry-point): mint
 * a Spike straight from an existing Narrative, skipping the Oracle ranking run and the
 * ranked-spikes review table. `creator` defaults server-side to the signed-in user. */
export interface MintSpikeFromNarrativeInput {
  narrative_id: string;
  headline: string;
  creator?: string | null;
}
