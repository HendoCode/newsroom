import { describe, expect, it } from "vitest";

import { hasWarnings, preFinalizeChecks } from "@/lib/finalize/checks";

describe("preFinalizeChecks — warns, never blocks (§5)", () => {
  it("reports clean OK checks when there are no open GAPs/clearances", () => {
    const checks = preFinalizeChecks({ open_gaps: 0, open_clearances: 0 });
    expect(checks).toEqual([
      { id: "open-gaps", severity: "ok", message: "0 open GAPs." },
      { id: "open-clearances", severity: "ok", message: "0 open clearances." },
    ]);
    expect(hasWarnings(checks)).toBe(false);
  });

  it("warns (singular) on exactly one open GAP", () => {
    const [gaps, clearances] = preFinalizeChecks({ open_gaps: 1, open_clearances: 0 });
    expect(gaps).toMatchObject({ id: "open-gaps", severity: "warn" });
    expect(gaps.message).toContain("1 open GAP ");
    expect(hasWarnings([gaps, clearances])).toBe(true);
  });

  it("warns (plural) on multiple open GAPs and clearances, but never blocks", () => {
    const [gaps, clearances] = preFinalizeChecks({ open_gaps: 2, open_clearances: 3 });
    expect(gaps).toMatchObject({ id: "open-gaps", severity: "warn" });
    expect(gaps.message).toContain("2 open GAPs");
    expect(clearances).toMatchObject({ id: "open-clearances", severity: "warn" });
    expect(clearances.message).toContain("3 open clearances");
    expect(hasWarnings([gaps, clearances])).toBe(true);
  });
});
