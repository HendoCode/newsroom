import { describe, expect, it } from "vitest";

import { defaultInterviewerSelection, slugifyHeadline } from "@/lib/spikes/kickoff";

describe("slugifyHeadline", () => {
  it("lowercases and hyphenates non-alphanumeric runs", () => {
    expect(slugifyHeadline("You're auditing the wrong line item")).toBe(
      "you-re-auditing-the-wrong-line-item",
    );
  });

  it("strips leading/trailing hyphens", () => {
    expect(slugifyHeadline("  --Wrapped in punctuation!!--  ")).toBe("wrapped-in-punctuation");
  });

  it("falls back to 'spike' when nothing alphanumeric survives", () => {
    expect(slugifyHeadline("!!!")).toBe("spike");
  });
});

describe("defaultInterviewerSelection — the agent's editable pre-selection (screen 6 step 4)", () => {
  it("prefers the small generally-useful trio when all three exist in the brain", () => {
    const available = ["architect", "customer", "ferriss", "king", "skeptic"];
    expect(defaultInterviewerSelection(available)).toEqual(["ferriss", "skeptic", "customer"]);
  });

  it("never pre-selects a persona that doesn't exist in the brain", () => {
    const available = ["architect", "operator"];
    const selected = defaultInterviewerSelection(available);
    for (const name of selected) {
      expect(available).toContain(name);
    }
  });

  it("falls back to the first available personas when none of the preferred trio exist", () => {
    const available = ["architect", "operator", "walters", "barbaro"];
    expect(defaultInterviewerSelection(available)).toEqual(["architect", "operator", "walters"]);
  });

  it("returns an empty selection when no personas are available", () => {
    expect(defaultInterviewerSelection([])).toEqual([]);
  });
});
