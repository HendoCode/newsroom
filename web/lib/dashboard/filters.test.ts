import { describe, expect, it } from "vitest";

import {
  applyFilters,
  creatorOf,
  EMPTY_FILTERS,
  filterOptions,
  statusOf,
  type FilterState,
} from "@/lib/dashboard/filters";
import type { QueueItem } from "@/lib/dashboard/types";

// The agents service serializes naive-UTC datetimes with no zone designator (app.models.common
// .utcnow() — never a trailing Z/+00:00). Per ECMA-262, a bare `Date.parse` on such a string is
// read as the runner's LOCAL time, so the date-axis window silently mis-filters outside UTC. Force
// a non-UTC zone here so the regression below actually exercises the bug rather than passing by
// luck of this machine's own timezone.
process.env.TZ = "America/Los_Angeles";

const ME = "me@example.com";
const OTHER = "someone@example.com";
const NOW = new Date("2026-07-30T12:00:00Z");

function piece(overrides: Partial<QueueItem> = {}): QueueItem {
  return {
    kind: "piece",
    id: Math.random().toString(36).slice(2),
    title: "A piece",
    voice: "demo-mira",
    stage: "review",
    spike_status: null,
    owner: OTHER,
    assigned_experts: [],
    creator: null,
    council_aggregate: null,
    open_gaps: 0,
    open_clearances: 0,
    review_round: null,
    open_interviews: [],
    has_complete_interview: false,
    failed_job: null,
    lessons_proposed: 0,
    spike_assigned: false,
    updated_at: NOW.toISOString(),
    last_human_touch_at: null,
    ...overrides,
  };
}

function spike(overrides: Partial<QueueItem> = {}): QueueItem {
  return piece({
    kind: "spike",
    title: "A spike",
    voice: null,
    stage: null,
    spike_status: "proposed",
    owner: null,
    creator: OTHER,
    ...overrides,
  });
}

describe("creatorOf / statusOf — the derived facets", () => {
  it("creatorOf prefers a spike's creator, else the piece owner", () => {
    expect(creatorOf(spike({ creator: "c@example.com" }))).toBe("c@example.com");
    expect(creatorOf(piece({ owner: "o@example.com", creator: null }))).toBe("o@example.com");
  });

  it("statusOf maps a piece to a coarse lifecycle status distinct from its stage", () => {
    expect(statusOf(piece({ stage: "review" }))).toBe("in-flight");
    expect(statusOf(piece({ stage: "finalized" }))).toBe("done");
    expect(statusOf(piece({ stage: "lessons" }))).toBe("done");
    // The actual regression this stage exists to fix: a published piece must never count as
    // in-flight work on the dashboard (Hendo's "everything looks perpetually in-flight" complaint).
    expect(statusOf(piece({ stage: "published" }))).toBe("done");
    expect(
      statusOf(
        piece({
          stage: "interviewing",
          failed_job: { type: "draft", code: "x", message: "m", triggered_by: ME, retryable: false, cost: 0 },
        }),
      ),
    ).toBe("failed");
  });

  it("statusOf reports a spike's pool status", () => {
    expect(statusOf(spike({ spike_status: "vaulted" }))).toBe("vaulted");
  });
});

describe("applyFilters — the D15 axes, ANDed, null = no-op", () => {
  const a = piece({ voice: "demo-mira", stage: "review", owner: "a@example.com" });
  const b = piece({ voice: "demo-dana", stage: "drafting", owner: "b@example.com" });
  const s = spike({ creator: "a@example.com", spike_status: "picked" });
  const items = [a, b, s];

  it("empty filters pass everything through", () => {
    expect(applyFilters(items, EMPTY_FILTERS, NOW)).toEqual(items);
  });

  it("filters by voice", () => {
    expect(applyFilters(items, { ...EMPTY_FILTERS, voice: "demo-dana" }, NOW)).toEqual([b]);
  });

  it("filters by stage, naturally excluding spikes (no stage)", () => {
    expect(applyFilters(items, { ...EMPTY_FILTERS, stage: "review" }, NOW)).toEqual([a]);
  });

  it("filters by creator across pieces and spikes", () => {
    expect(applyFilters(items, { ...EMPTY_FILTERS, creator: "a@example.com" }, NOW)).toEqual([a, s]);
  });

  it("filters by coarse status", () => {
    expect(applyFilters(items, { ...EMPTY_FILTERS, status: "picked" }, NOW)).toEqual([s]);
    expect(applyFilters(items, { ...EMPTY_FILTERS, status: "in-flight" }, NOW)).toEqual([a, b]);
  });

  it("filters by date window against a supplied clock", () => {
    const fresh = piece({ updated_at: new Date("2026-07-29T12:00:00Z").toISOString() });
    const stale = piece({ updated_at: new Date("2026-06-01T12:00:00Z").toISOString() });
    const undated = piece({ updated_at: null });
    const within7: FilterState = { ...EMPTY_FILTERS, withinDays: 7 };
    const out = applyFilters([fresh, stale, undated], within7, NOW);
    expect(out).toEqual([fresh]); // stale is outside 7d; undated never matches a date window
  });

  it("windows a naive-UTC updated_at (no zone designator) as UTC, not the runner's local time", () => {
    // NOW is 2026-07-30T12:00:00Z, so the 7-day cutoff is 2026-07-23T12:00:00Z. Both fixtures are
    // genuinely in UTC: the just-outside one (2026-07-23T11:00:00Z, one hour before the cutoff)
    // must be EXCLUDED, and the just-inside one (2026-07-23T13:00:00Z) must be INCLUDED. Under
    // TZ=America/Los_Angeles the old bare `Date.parse` read the naive strings as -07:00 local,
    // shifting both 7h into the future (18:00Z / 20:00Z) — so the first wrongly survived the
    // filter, exactly the silent mis-windowing this fixes.
    const justOutside = piece({ updated_at: "2026-07-23T11:00:00.000000" });
    const justInside = piece({ updated_at: "2026-07-23T13:00:00.000000" });
    const within7: FilterState = { ...EMPTY_FILTERS, withinDays: 7 };
    expect(applyFilters([justOutside, justInside], within7, NOW)).toEqual([justInside]);
  });

  it("ANDs multiple axes", () => {
    const out = applyFilters(items, { ...EMPTY_FILTERS, voice: "demo-mira", stage: "review" }, NOW);
    expect(out).toEqual([a]);
  });
});

describe("filterOptions — derived from the live queue", () => {
  it("returns the distinct, sorted values present for each axis", () => {
    const items = [
      piece({ voice: "demo-mira", stage: "review", owner: "a@example.com" }),
      piece({ voice: "demo-dana", stage: "drafting", owner: "b@example.com" }),
      spike({ creator: "c@example.com", spike_status: "vaulted" }),
    ];
    const opts = filterOptions(items);
    expect(opts.voices).toEqual(["demo-dana", "demo-mira"]);
    expect(opts.stages).toEqual(["drafting", "review"]);
    expect(opts.creators).toEqual(["a@example.com", "b@example.com", "c@example.com"]);
    expect(opts.statuses).toEqual(["in-flight", "vaulted"].sort());
  });
});
