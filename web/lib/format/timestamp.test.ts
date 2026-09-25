import { describe, expect, it } from "vitest";

import { parseTimestampMs } from "@/lib/format/timestamp";

describe("parseTimestampMs", () => {
  it("treats a zone-less date-time string (the backend's naive-UTC convention) as UTC", () => {
    expect(parseTimestampMs("2026-08-11T06:43:52.435000")).toBe(
      Date.parse("2026-08-11T06:43:52.435Z"),
    );
  });

  it("honors an explicit Z suffix unchanged", () => {
    expect(parseTimestampMs("2026-08-11T06:43:52.000Z")).toBe(
      Date.parse("2026-08-11T06:43:52.000Z"),
    );
  });

  it("honors an explicit numeric offset unchanged", () => {
    expect(parseTimestampMs("2026-08-11T06:43:52+00:00")).toBe(
      Date.parse("2026-08-11T06:43:52+00:00"),
    );
  });

  it("leaves a date-only string alone (already spec-defined as UTC)", () => {
    expect(parseTimestampMs("2026-08-11")).toBe(Date.parse("2026-08-11"));
  });

  it("returns NaN for an unparseable string rather than throwing", () => {
    expect(Number.isNaN(parseTimestampMs("not-a-date"))).toBe(true);
  });
});
