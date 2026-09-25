/**
 * Oracle run domain types (domain model §1.8; D7) — the on-demand run entrypoint
 * (cmw-ui-wireframes screen 8). Mirror the agents `/api/oracle/run` wire contract 1:1.
 */

/** Entry A (open scan, pure convergence) vs Entry B (a Narrative biases ranking). */
export type OracleEntryMode = "open-scan" | "narrative";

export interface OracleRunInput {
  entry_mode: OracleEntryMode;
  voice: string;
  lookback_days?: number;
  /** Required when `entry_mode === "narrative"` (Entry B). */
  narrative_id?: string | null;
  /** Override the entry mode's default rank-and-retrieve cap. */
  top_k?: number | null;
  /** Attribution — becomes the produced spikes' creator. */
  triggered_by?: string | null;
}

export interface OracleRunResult {
  job_id: string;
  status: string;
  cost_usd: number;
  error: string | null;
}
