import { describe, expect, it } from "vitest";

import { originNarrativeId } from "@/lib/spikes/origin";

describe("originNarrativeId", () => {
  it("returns the ref when the spike was seeded from a narrative", () => {
    expect(originNarrativeId({ origin: { kind: "narrative", ref: "narrative-1" } })).toBe(
      "narrative-1",
    );
  });

  it("returns null for an oracle-run origin, even with a ref present", () => {
    expect(originNarrativeId({ origin: { kind: "oracle-run", ref: "job-1" } })).toBeNull();
  });

  it("returns null for a tangent origin (no ref)", () => {
    expect(originNarrativeId({ origin: { kind: "tangent", ref: null } })).toBeNull();
  });

  it("returns null for a narrative origin with a missing ref (defensive — shouldn't happen)", () => {
    expect(originNarrativeId({ origin: { kind: "narrative", ref: null } })).toBeNull();
  });
});
