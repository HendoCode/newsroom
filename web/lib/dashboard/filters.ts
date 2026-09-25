/**
 * The dashboard filter model (docs/design.md D15; cmw-ui-wireframes screen 1).
 *
 * The desk redesign (Concept A, cmw-evolution-ux-audit) replaced the old five saved-filter TABS
 * with three sections (`lib/dashboard/desk.ts`: Inbox / Machine strip / Library); what survives
 * here is the one layer those sections still share — **the D15 filter bar** (voice · stage ·
 * creator · date · status), a single reusable {@link FilterState} the Library applies over the
 * full piece list. See {@link applyFilters}.
 *
 * Everything here is a pure, total function of `(items, state, now)` so it is trivially unit-tested
 * and free of hidden clocks — the caller passes `now` for the date axis.
 */

import { parseTimestampMs } from "@/lib/format/timestamp";
import type { PieceStage, QueueItem, SpikeStatus } from "@/lib/dashboard/types";

// --- The D15 filter bar -----------------------------------------------------------------------

/** A single reusable filter model across the five D15 axes. `null` on an axis means "all". */
export interface FilterState {
  voice: string | null;
  stage: PieceStage | null;
  creator: string | null;
  /** Coarse lifecycle status (see {@link statusOf}) — distinct from the fine-grained `stage`. */
  status: string | null;
  /** Date axis: only items updated within this many days. `null` means any date. */
  withinDays: number | null;
}

export const EMPTY_FILTERS: FilterState = {
  voice: null,
  stage: null,
  creator: null,
  status: null,
  withinDays: null,
};

/** Attribution "creator" for the D15 creator axis: a spike's creator, else the piece's owner. */
export function creatorOf(item: QueueItem): string | null {
  return item.creator ?? item.owner;
}

/**
 * Coarse lifecycle status for the D15 status axis (distinct from the fine `stage`):
 *  - a spike reports its pool status (proposed / picked / in-flight / vaulted);
 *  - a piece with a failed/stuck job reports `failed` (Item 4);
 *  - a finalized/lessons/published piece reports `done`; anything else is `in-flight`.
 *
 * `published` is the actual point of this predicate for Hendo's "everything looks perpetually
 * in-flight" complaint: without it here, a published piece — genuinely finished, with durable
 * public links — would still count as in-flight work on the dashboard. Not caught by a compiler
 * exhaustiveness check (this function has a catch-all `"in-flight"` return, not a switch), so any
 * future terminal-ish stage needs the same deliberate check here.
 */
export function statusOf(item: QueueItem): SpikeStatus | "failed" | "done" | "in-flight" {
  if (item.kind === "spike") return item.spike_status ?? "proposed";
  if (item.failed_job) return "failed";
  if (
    item.stage === "finalized" ||
    item.stage === "lessons" ||
    item.stage === "released" ||
    item.stage === "published"
  ) {
    return "done";
  }
  return "in-flight";
}

function withinWindow(updatedAt: string | null, withinDays: number, now: Date): boolean {
  if (!updatedAt) return false;
  const ts = parseTimestampMs(updatedAt);
  if (Number.isNaN(ts)) return false;
  const cutoff = now.getTime() - withinDays * 24 * 60 * 60 * 1000;
  return ts >= cutoff;
}

/**
 * Apply the D15 filter bar. Each axis is ANDed; a `null` axis is a no-op. A stage filter naturally
 * excludes spikes (they have no stage) — on the desk the bar only ever sees the Library's pieces,
 * but this stays total for any caller.
 */
export function applyFilters(items: QueueItem[], f: FilterState, now: Date): QueueItem[] {
  return items.filter((it) => {
    if (f.voice != null && it.voice !== f.voice) return false;
    if (f.stage != null && it.stage !== f.stage) return false;
    if (f.creator != null && creatorOf(it) !== f.creator) return false;
    if (f.status != null && statusOf(it) !== f.status) return false;
    if (f.withinDays != null && !withinWindow(it.updated_at, f.withinDays, now)) return false;
    return true;
  });
}

/** Distinct, sorted option values present in the queue for each D15 axis — to populate the selects. */
export interface FilterOptions {
  voices: string[];
  stages: PieceStage[];
  creators: string[];
  statuses: string[];
}

export function filterOptions(items: QueueItem[]): FilterOptions {
  const voices = new Set<string>();
  const stages = new Set<PieceStage>();
  const creators = new Set<string>();
  const statuses = new Set<string>();
  for (const it of items) {
    if (it.voice) voices.add(it.voice);
    if (it.stage) stages.add(it.stage);
    const c = creatorOf(it);
    if (c) creators.add(c);
    statuses.add(statusOf(it));
  }
  return {
    voices: [...voices].sort(),
    stages: [...stages].sort(),
    creators: [...creators].sort(),
    statuses: [...statuses].sort(),
  };
}
