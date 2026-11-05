import { describe, expect, it } from "vitest";

import { relativeTime } from "@/lib/format/relative-time";

describe("relativeTime", () => {
  const now = new Date("2026-08-11T12:00:00.000Z");

  it("reports sub-minute deltas as just now", () => {
    expect(relativeTime(new Date("2026-08-11T11:59:40.000Z").toISOString(), now)).toBe("just now");
  });

  it("reports minutes ago under an hour", () => {
    expect(relativeTime(new Date("2026-08-11T11:45:00.000Z").toISOString(), now)).toBe("15m ago");
  });

  it("reports hours ago under a day", () => {
    expect(relativeTime(new Date("2026-08-11T05:00:00.000Z").toISOString(), now)).toBe("7h ago");
  });

  it("reports days ago beyond a day — the piece-stuck-for-weeks case this feature exists for", () => {
    expect(relativeTime(new Date("2026-07-28T12:00:00.000Z").toISOString(), now)).toBe("14d ago");
  });

  it("returns an empty string for an unparseable timestamp rather than throwing", () => {
    expect(relativeTime("not-a-date", now)).toBe("");
  });
});
