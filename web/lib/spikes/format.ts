/**
 * Pure display helpers for the Spikes & Vault browser (cmw-ui-wireframes screen 5). Kept free of
 * React/fetch so they're trivially unit-tested, mirroring `lib/sources/format.ts`.
 */

import type { Spike, SpikeOriginKind, SpikeStatus } from "@/lib/spikes/types";

const STATUS_LABELS: Record<SpikeStatus, string> = {
  proposed: "Proposed",
  picked: "Picked",
  "in-flight": "In flight",
  vaulted: "Vaulted",
};

export function spikeStatusLabel(status: SpikeStatus): string {
  return STATUS_LABELS[status] ?? status;
}

const ORIGIN_LABELS: Record<SpikeOriginKind, string> = {
  "oracle-run": "Radar run",
  narrative: "Narrative",
  tangent: "Parked tangent",
};

export function originLabel(kind: SpikeOriginKind): string {
  return ORIGIN_LABELS[kind] ?? kind;
}

/**
 * 0..1 convergence score as a whole-number percent for the bar width, or `null` for a parked
 * tangent (§5-Q2 — there is no score to show).
 */
export function convergencePercent(score: number | null): number | null {
  if (score == null) return null;
  return Math.round(Math.max(0, Math.min(1, score)) * 100);
}

/** "0.71" display text, or "—" for a parked tangent. */
export function convergenceLabel(score: number | null): string {
  return score == null ? "—" : score.toFixed(2);
}

/** The "maps to" column (screen 5): the named customer/partner, or "none yet". */
export function mapsToLabel(spike: Pick<Spike, "customer_partner">): string {
  return spike.customer_partner ?? "none yet";
}

/** The "outcome" column (screen 5). */
export function outcomeLabel(spike: Pick<Spike, "outcome_metric">): string {
  return spike.outcome_metric ?? "none yet";
}
