/**
 * The Spikes & Vault filter model (D15; cmw-ui-wireframes screen 5).
 *
 * TWO layers of filtering over ONE shared pool, mirroring the dashboard's `lib/dashboard/filters.ts`
 * architecture:
 *  - **Status tabs** (All / Proposed / Picked / In flight / Vaulted) are saved filters, NOT
 *    permission scopes. See {@link STATUS_TABS} and {@link applyStatusTab}.
 *  - **The D15 filter bar** (creator · topic · date · status) is a single reusable
 *    {@link FilterState} applied ON TOP of the active tab, plus a convergence sort
 *    ({@link sortByConvergence}).
 *
 * Everything here is a pure, total function of `(items, state, now)` so it is trivially unit-tested
 * and free of hidden clocks — the caller passes `now` for the date axis.
 */

import type { Spike, SpikeStatus } from "@/lib/spikes/types";
import { parseTimestampMs } from "@/lib/format/timestamp";

// --- Status tabs (saved filters over the one pool) ---------------------------------------------

export type StatusTabKey = "all" | "proposed" | "picked" | "in-flight" | "vaulted";

export interface StatusTabDef {
  key: StatusTabKey;
  label: string;
}

export const STATUS_TABS: StatusTabDef[] = [
  { key: "all", label: "All" },
  { key: "proposed", label: "Proposed" },
  { key: "picked", label: "Picked" },
  { key: "in-flight", label: "In flight" },
  { key: "vaulted", label: "Vaulted" },
];

export function applyStatusTab(items: Spike[], tab: StatusTabKey): Spike[] {
  if (tab === "all") return items;
  return items.filter((s) => s.status === tab);
}

// --- The D15 filter bar --------------------------------------------------------------------------

/** A single reusable filter model across the D15 axes. `null` on an axis means "all". */
export interface FilterState {
  creator: string | null;
  /**
   * Free-text keyword match over headline / rank-rationale / convergence-note / maps-to. A Spike
   * carries no bounded "topic" field (domain model §1.6), so — unlike Creator/Status, which ARE
   * bounded selects — Topic is a search box. A deliberate structural call, not an oversight.
   */
  topic: string | null;
  /** Date axis: only spikes updated within this many days. `null` means any date. */
  withinDays: number | null;
  status: SpikeStatus | null;
}

export const EMPTY_FILTERS: FilterState = {
  creator: null,
  topic: null,
  withinDays: null,
  status: null,
};

function withinWindow(updatedAt: string | null, withinDays: number, now: Date): boolean {
  if (!updatedAt) return false;
  const ts = parseTimestampMs(updatedAt);
  if (Number.isNaN(ts)) return false;
  const cutoff = now.getTime() - withinDays * 24 * 60 * 60 * 1000;
  return ts >= cutoff;
}

function matchesTopic(spike: Spike, topic: string): boolean {
  const needle = topic.trim().toLowerCase();
  if (!needle) return true;
  const haystacks = [
    spike.headline,
    spike.rank_rationale,
    spike.convergence_note,
    spike.customer_partner,
  ];
  return haystacks.some((h) => h != null && h.toLowerCase().includes(needle));
}

/** Apply the D15 filter bar. Each axis is ANDed; a `null`/empty axis is a no-op. */
export function applyFilters(items: Spike[], f: FilterState, now: Date): Spike[] {
  return items.filter((s) => {
    if (f.creator != null && s.creator !== f.creator) return false;
    if (f.topic != null && f.topic !== "" && !matchesTopic(s, f.topic)) return false;
    if (f.withinDays != null && !withinWindow(s.updated_at, f.withinDays, now)) return false;
    if (f.status != null && s.status !== f.status) return false;
    return true;
  });
}

/** Distinct, sorted creator values present in the pool — to populate the Creator select. */
export interface FilterOptions {
  creators: string[];
}

export function filterOptions(items: Spike[]): FilterOptions {
  const creators = new Set<string>();
  for (const s of items) creators.add(s.creator);
  return { creators: [...creators].sort() };
}

// --- Convergence sort ----------------------------------------------------------------------------

export type SortDirection = "desc" | "asc";

/**
 * Sort by convergence score. Parked tangents (§5-Q2) carry a null score and always sort last,
 * regardless of direction — there is nothing to rank them against.
 */
export function sortByConvergence(items: Spike[], direction: SortDirection = "desc"): Spike[] {
  const scored = items.filter((s) => s.convergence_score != null);
  const unscored = items.filter((s) => s.convergence_score == null);
  scored.sort((a, b) => {
    const diff = (a.convergence_score as number) - (b.convergence_score as number);
    return direction === "desc" ? -diff : diff;
  });
  return [...scored, ...unscored];
}
