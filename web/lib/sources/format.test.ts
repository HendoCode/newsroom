import { describe, expect, it } from "vitest";

process.env.TZ = "America/Los_Angeles";

import {
  configListText,
  configSummary,
  credentialLabel,
  extractDriveFolderId,
  kindLabel,
  parseConfigList,
  relativeRefreshLabel,
} from "@/lib/sources/format";

describe("kindLabel / credentialLabel", () => {
  it("labels every kind and never leaks a secret value", () => {
    expect(kindLabel("gdrive")).toBe("Google Drive");
    expect(kindLabel("linkedin-x-clip")).toBe("Clip-in");
    expect(credentialLabel("gdrive")).toBe("server-side OAuth");
    expect(credentialLabel("linkedin-x-clip")).toBe("none — no scraper");
    expect(credentialLabel("web-rss")).toMatch(/none/);
  });
});

describe("configSummary", () => {
  it("summarizes a gdrive source's folder count", () => {
    expect(configSummary({ kind: "gdrive", config: { folder_ids: ["a", "b", "c"] } })).toBe(
      "3 folder IDs",
    );
  });

  it("summarizes a web-rss source's feed count (singular vs plural)", () => {
    expect(configSummary({ kind: "web-rss", config: { feed_urls: ["a"] } })).toBe("1 feed URL");
    expect(configSummary({ kind: "web-rss", config: { feed_urls: ["a", "b"] } })).toBe(
      "2 feed URLs",
    );
  });

  it("reports not-configured when the list is empty", () => {
    expect(configSummary({ kind: "slack", config: {} })).toBe("not configured");
  });

  it("always reports the clip-in source as manual paste, ignoring config", () => {
    expect(configSummary({ kind: "linkedin-x-clip", config: { anything: true } })).toBe(
      "manual paste (below)",
    );
  });
});

describe("relativeRefreshLabel", () => {
  const now = new Date("2026-07-30T12:00:00.000Z");

  it("renders — when never refreshed", () => {
    expect(relativeRefreshLabel(null, now)).toBe("—");
  });

  it("renders hours-ago under a day", () => {
    expect(relativeRefreshLabel("2026-07-30T10:00:00.000Z", now)).toBe("2h ago");
  });

  it("renders days-ago at or beyond 24h", () => {
    expect(relativeRefreshLabel("2026-07-28T12:00:00.000Z", now)).toBe("2d ago");
  });

  it("renders relative time for a naive-UTC lastRefreshed (no zone designator) as UTC, not the runner's local time", () => {
    // now is 2026-07-30T12:00:00Z. A naive "2026-07-30T10:00:00.000000" is genuinely 2h ago in UTC.
    // Under TZ=America/Los_Angeles the old bare `Date.parse` read it as 10:00 local (17:00Z),
    // producing a negative diff and wrongly returning "just now".
    expect(relativeRefreshLabel("2026-07-30T10:00:00.000000", now)).toBe("2h ago");
  });
});

describe("extractDriveFolderId", () => {
  it("extracts the id from a pasted folder link (what a business user actually has)", () => {
    expect(extractDriveFolderId("https://drive.google.com/drive/folders/1AbCdEf012")).toBe(
      "1AbCdEf012",
    );
  });

  it("extracts the id from a /drive/u/0/folders/ link and strips a trailing query", () => {
    expect(
      extractDriveFolderId("https://drive.google.com/drive/u/0/folders/1AbCdEf012?resourcekey=x"),
    ).toBe("1AbCdEf012");
  });

  it("extracts the id from an /open?id= link", () => {
    expect(extractDriveFolderId("https://drive.google.com/open?id=1AbCdEf012")).toBe("1AbCdEf012");
  });

  it("passes a bare id through unchanged", () => {
    expect(extractDriveFolderId("1AbCdEf012")).toBe("1AbCdEf012");
  });

  it("trims whitespace around a bare id", () => {
    expect(extractDriveFolderId("  1AbCdEf012  ")).toBe("1AbCdEf012");
  });
});

describe("parseConfigList / configListText round-trip", () => {
  it("splits newline/comma separated input into the kind's config key", () => {
    expect(parseConfigList("gdrive", "abc\n def ,ghi\n\n")).toEqual({
      folder_ids: ["abc", "def", "ghi"],
    });
  });

  it("auto-extracts a pasted Drive folder link's id for gdrive only (item 3)", () => {
    expect(
      parseConfigList("gdrive", "https://drive.google.com/drive/folders/1AbCdEf012\nbareId2"),
    ).toEqual({ folder_ids: ["1AbCdEf012", "bareId2"] });
    // A different kind must never run the Drive-specific extraction.
    expect(parseConfigList("web-rss", "https://drive.google.com/drive/folders/1AbCdEf012")).toEqual(
      { feed_urls: ["https://drive.google.com/drive/folders/1AbCdEf012"] },
    );
  });

  it("returns an empty config for a kind with no list key (linkedin-x-clip)", () => {
    expect(parseConfigList("linkedin-x-clip", "abc")).toEqual({});
  });

  it("round-trips a stored config back into editable text", () => {
    const source = { kind: "slack" as const, config: { channel_ids: ["#a", "#b"] } };
    expect(configListText(source)).toBe("#a\n#b");
    expect(parseConfigList("slack", configListText(source))).toEqual({
      channel_ids: ["#a", "#b"],
    });
  });
});
