import { describe, expect, it } from "vitest";

import { humanTouchStaleness } from "@/lib/format/staleness";

describe("humanTouchStaleness", () => {
  const now = new Date("2026-08-11T12:00:00.000Z");

  it("reports never for a piece with no recorded human touch", () => {
    expect(humanTouchStaleness(null, now)).toBe("never");
  });

  it("reports fresh for a touch within the last week", () => {
    expect(humanTouchStaleness(new Date("2026-08-10T12:00:00.000Z").toISOString(), now)).toBe(
      "fresh",
    );
  });

  it("reports stale once a touch is over a week old — the piece-stuck-since-before-the-fix case", () => {
    expect(humanTouchStaleness(new Date("2026-07-01T12:00:00.000Z").toISOString(), now)).toBe(
      "stale",
    );
  });

  it("reports never for an unparseable timestamp rather than throwing", () => {
    expect(humanTouchStaleness("not-a-date", now)).toBe("never");
  });
});
