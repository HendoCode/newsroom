import { describe, expect, it } from "vitest";

import {
  COMMISSION_NOT_BUILT_REASON,
  DERIVATIVE_FORMATS,
  DERIVATIVE_QUALITY_BAR,
  UNIVERSAL_HARD_GATES,
  derivativeCouncilEditors,
  derivativeSlots,
  existingFromArtifact,
  formatForDestination,
  lineageOf,
  promotedHref,
} from "@/lib/pieces/derivatives";

describe("DERIVATIVE_FORMATS — the target native package", () => {
  it("includes the synthesis-named natives plus the Content Project default destination", () => {
    const ids = DERIVATIVE_FORMATS.map((f) => f.id);
    expect(ids).toEqual([
      "linkedin-post",
      "linkedin-carousel",
      "x-thread",
      "newsletter",
      "blog",
      "executive-brief",
      "talk-track",
      "email",
    ]);
  });

  it("treats HTML/PDF/Doc as not-a-format — those stay render outputs, not Pieces", () => {
    expect(formatForDestination("html")).toBeNull();
    expect(formatForDestination("pdf")).toBeNull();
    expect(formatForDestination("doc")).toBeNull();
  });
});

describe("formatForDestination", () => {
  it("matches canonical ids and aliases, case-insensitively", () => {
    expect(formatForDestination("linkedin")?.id).toBe("linkedin-post");
    expect(formatForDestination("LinkedIn-Post")?.id).toBe("linkedin-post");
    expect(formatForDestination("twitter-thread")?.id).toBe("x-thread");
    expect(formatForDestination("blog-post")?.id).toBe("blog");
    expect(formatForDestination("  newsletter  ")?.id).toBe("newsletter");
  });

  it("returns null for blank or unknown destinations", () => {
    expect(formatForDestination("")).toBeNull();
    expect(formatForDestination("   ")).toBeNull();
    expect(formatForDestination("tiktok")).toBeNull();
  });
});

describe("derivativeSlots", () => {
  it("with no existing derivatives, every catalog format is creatable", () => {
    const slots = derivativeSlots([]);
    expect(slots.every((s) => s.kind === "creatable")).toBe(true);
    expect(slots.map((s) => (s.kind === "creatable" ? s.format.id : null))).toEqual(
      DERIVATIVE_FORMATS.map((f) => f.id),
    );
  });

  it("an existing LinkedIn Piece occupies that format and is not also creatable", () => {
    const slots = derivativeSlots([
      { id: "d1", title: "Token vs storage — LinkedIn", destination: "linkedin" },
    ]);
    const existing = slots.filter((s) => s.kind === "existing");
    const creatable = slots.filter((s) => s.kind === "creatable");
    expect(existing).toHaveLength(1);
    expect(existing[0]).toMatchObject({
      kind: "existing",
      format: { id: "linkedin-post" },
      derivative: { id: "d1" },
    });
    expect(creatable.map((s) => (s.kind === "creatable" ? s.format.id : null))).not.toContain(
      "linkedin-post",
    );
    expect(creatable).toHaveLength(DERIVATIVE_FORMATS.length - 1);
  });

  it("keeps an unknown destination as existing rather than dropping it", () => {
    const slots = derivativeSlots([{ id: "d2", title: "Weird native", destination: "tiktok" }]);
    expect(slots[0]).toEqual({
      kind: "existing",
      format: null,
      derivative: { id: "d2", title: "Weird native", destination: "tiktok" },
    });
  });

  it("names the honest reason generation is not wired, and that commission records a child", () => {
    expect(COMMISSION_NOT_BUILT_REASON).toMatch(/not built yet/i);
    expect(COMMISSION_NOT_BUILT_REASON).toMatch(/child artifact/i);
  });
});

describe("lineageOf / promotedHref", () => {
  it("defaults missing lineage to child, with no piece href", () => {
    const child = { id: "d1", title: "LI", destination: "linkedin" };
    expect(lineageOf(child)).toBe("child");
    expect(promotedHref(child)).toBeUndefined();
  });

  it("links a promoted derivative to its own piece", () => {
    const promoted = {
      id: "d1",
      title: "LI",
      destination: "linkedin",
      lineage: "promoted" as const,
      promoted_piece_id: "piece-9",
    };
    expect(lineageOf(promoted)).toBe("promoted");
    expect(promotedHref(promoted)).toBe("/pieces/piece-9");
  });
});

describe("derivative quality bar — destination councils + universal gates", () => {
  it("the bar is 9/10 and the universal gates are facts + safety for every destination", () => {
    expect(DERIVATIVE_QUALITY_BAR).toBe(9);
    expect(UNIVERSAL_HARD_GATES).toEqual(["facts", "safety"]);
  });

  it("every lineup starts with the universal council editors and is deduped", () => {
    for (const dest of [
      "linkedin-post",
      "x-thread",
      "newsletter",
      "blog",
      "executive-brief",
      "tiktok",
    ]) {
      const lineup = derivativeCouncilEditors(dest);
      expect(lineup.slice(0, 3)).toEqual([
        "slop-allergist",
        "voice-guardian",
        "technical-reviewer",
      ]);
      expect(new Set(lineup).size).toBe(lineup.length);
    }
  });

  it("a LinkedIn post and a whitepaper get different destination judgment", () => {
    const linkedin = derivativeCouncilEditors("linkedin-post");
    const whitepaper = derivativeCouncilEditors("whitepaper");
    expect(linkedin).not.toEqual(whitepaper);
    expect(linkedin).toContain("puri");
    expect(whitepaper).toContain("housel");
    expect(linkedin).not.toContain("housel");
  });

  it("unknown destinations still get a council — generic judgment, never exemption", () => {
    const lineup = derivativeCouncilEditors("carrier-pigeon");
    expect(lineup).toContain("cold-reader");
    expect(lineup).toContain("structure-editor");
  });

  it("existingFromArtifact carries the quality view through", () => {
    const quality = {
      required: true,
      cleared: true,
      bar: 9,
      aggregate: 9.2,
      council_revision: "rev-1",
      reasons: [],
      editors: ["slop-allergist", "voice-guardian", "technical-reviewer"],
      universal_gates: ["facts", "safety"] as const,
    };
    const existing = existingFromArtifact({
      id: "d1",
      anchor_piece_id: "p1",
      content_project_id: null,
      destination: "linkedin-post",
      title: "LI",
      voice: null,
      lineage: "promoted",
      promoted_piece_id: "piece-9",
      quality: { ...quality, universal_gates: ["facts", "safety"] },
    });
    expect(existing.quality).toEqual(quality);
  });
});
