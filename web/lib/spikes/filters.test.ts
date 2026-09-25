import { describe, expect, it } from "vitest";

process.env.TZ = "America/Los_Angeles";

import {
  applyFilters,
  applyStatusTab,
  EMPTY_FILTERS,
  filterOptions,
  sortByConvergence,
  STATUS_TABS,
  type FilterState,
} from "@/lib/spikes/filters";
import type { Spike } from "@/lib/spikes/types";

const NOW = new Date("2026-07-30T12:00:00Z");

function spike(overrides: Partial<Spike> = {}): Spike {
  return {
    id: Math.random().toString(36).slice(2),
    headline: "A spike",
    status: "proposed",
    convergence_score: 0.5,
    creator: "someone@example.com",
    origin: { kind: "oracle-run", ref: "job-1" },
    source_ids: [],
    customer_partner: null,
    outcome_metric: null,
    rank_rationale: null,
    convergence_note: null,
    intent: null,
    piece_id: null,
    updated_at: NOW.toISOString(),
    ...overrides,
  };
}

describe("STATUS_TABS / applyStatusTab — saved filters over one pool (not permission scopes)", () => {
  const proposed = spike({ status: "proposed" });
  const picked = spike({ status: "picked" });
  const inFlight = spike({ status: "in-flight" });
  const vaulted = spike({ status: "vaulted" });
  const items = [proposed, picked, inFlight, vaulted];

  it("has exactly the five settled tabs in order", () => {
    expect(STATUS_TABS.map((t) => t.key)).toEqual(["all", "proposed", "picked", "in-flight", "vaulted"]);
  });

  it("All = every spike, no filtering", () => {
    expect(applyStatusTab(items, "all")).toEqual(items);
  });

  it("narrows to a single status", () => {
    expect(applyStatusTab(items, "proposed")).toEqual([proposed]);
    expect(applyStatusTab(items, "vaulted")).toEqual([vaulted]);
  });
});

describe("applyFilters — the D15 axes, ANDed, null = no-op", () => {
  const a = spike({ creator: "a@example.com", status: "proposed", headline: "AWS bill reframe" });
  const b = spike({ creator: "b@example.com", status: "vaulted", headline: "Latency budget FAQ" });
  const items = [a, b];

  it("empty filters pass everything through", () => {
    expect(applyFilters(items, EMPTY_FILTERS, NOW)).toEqual(items);
  });

  it("filters by creator", () => {
    expect(applyFilters(items, { ...EMPTY_FILTERS, creator: "a@example.com" }, NOW)).toEqual([a]);
  });

  it("filters by status", () => {
    expect(applyFilters(items, { ...EMPTY_FILTERS, status: "vaulted" }, NOW)).toEqual([b]);
  });

  it("filters by topic — a keyword match over headline/rank-rationale/convergence-note/maps-to", () => {
    expect(applyFilters(items, { ...EMPTY_FILTERS, topic: "latency" }, NOW)).toEqual([b]);
    expect(applyFilters(items, { ...EMPTY_FILTERS, topic: "AWS" }, NOW)).toEqual([a]);
    const withRationale = spike({ rank_rationale: "needs a real POC figure" });
    expect(applyFilters([withRationale], { ...EMPTY_FILTERS, topic: "poc" }, NOW)).toEqual([
      withRationale,
    ]);
  });

  it("filters by date window against a supplied clock", () => {
    const fresh = spike({ updated_at: new Date("2026-07-29T12:00:00Z").toISOString() });
    const stale = spike({ updated_at: new Date("2026-06-01T12:00:00Z").toISOString() });
    const undated = spike({ updated_at: null });
    const within7: FilterState = { ...EMPTY_FILTERS, withinDays: 7 };
    expect(applyFilters([fresh, stale, undated], within7, NOW)).toEqual([fresh]);
  });

  it("windows a naive-UTC updated_at (no zone designator) as UTC, not the runner's local time", () => {
    // NOW is 2026-07-30T12:00:00Z, so the 7-day cutoff is 2026-07-23T12:00:00Z. Both fixtures are
    // genuinely in UTC: the just-outside one (2026-07-23T11:00:00Z, one hour before the cutoff)
    // must be EXCLUDED, and the just-inside one (2026-07-23T13:00:00Z) must be INCLUDED. Under
    // TZ=America/Los_Angeles the old bare `Date.parse` read the naive strings as -07:00 local,
    // shifting both 7h into the future (18:00Z / 20:00Z) — so the first wrongly survived the
    // filter, exactly the silent mis-windowing this fixes.
    const justOutside = spike({ updated_at: "2026-07-23T11:00:00.000000" });
    const justInside = spike({ updated_at: "2026-07-23T13:00:00.000000" });
    const within7: FilterState = { ...EMPTY_FILTERS, withinDays: 7 };
    expect(applyFilters([justOutside, justInside], within7, NOW)).toEqual([justInside]);
  });

  it("ANDs multiple axes", () => {
    const out = applyFilters(items, { ...EMPTY_FILTERS, creator: "a@example.com", status: "proposed" }, NOW);
    expect(out).toEqual([a]);
  });
});

describe("filterOptions — derived from the live pool", () => {
  it("returns distinct, sorted creators", () => {
    const items = [spike({ creator: "c@example.com" }), spike({ creator: "a@example.com" }), spike({ creator: "b@example.com" })];
    expect(filterOptions(items).creators).toEqual(["a@example.com", "b@example.com", "c@example.com"]);
  });
});

describe("sortByConvergence — parked tangents (null score) always sort last", () => {
  const high = spike({ convergence_score: 0.92 });
  const mid = spike({ convergence_score: 0.64 });
  const low = spike({ convergence_score: 0.38 });
  const tangent = spike({ convergence_score: null, origin: { kind: "tangent", ref: null } });

  it("sorts descending by default", () => {
    expect(sortByConvergence([low, tangent, high, mid])).toEqual([high, mid, low, tangent]);
  });

  it("sorts ascending — the tangent still sorts last", () => {
    expect(sortByConvergence([high, tangent, low, mid], "asc")).toEqual([low, mid, high, tangent]);
  });
});
