import { describe, expect, it } from "vitest";

import { canFinalize, formatsForRequest, normalizeFormats, toggleFormat } from "@/lib/finalize/formats";
import { DEFAULT_FINALIZE_FORMATS } from "@/lib/finalize/types";

describe("toggleFormat", () => {
  it("adds a format that isn't selected", () => {
    expect(toggleFormat(["html"], "pdf")).toEqual(["html", "pdf"]);
  });

  it("removes a format that is selected", () => {
    expect(toggleFormat(["html", "pdf"], "html")).toEqual(["pdf"]);
  });

  it("does not mutate the input array", () => {
    const selected: readonly ("html" | "pdf" | "doc")[] = ["html"];
    toggleFormat(selected, "pdf");
    expect(selected).toEqual(["html"]);
  });
});

describe("normalizeFormats", () => {
  it("restores canonical html/pdf/doc order regardless of toggle order", () => {
    expect(normalizeFormats(["doc", "html"])).toEqual(["html", "doc"]);
  });

  it("dedupes repeated entries", () => {
    expect(normalizeFormats(["pdf", "pdf", "html"])).toEqual(["html", "pdf"]);
  });

  it("returns an empty array for an empty selection", () => {
    expect(normalizeFormats([])).toEqual([]);
  });
});

describe("canFinalize", () => {
  it("is false for an empty selection (would silently produce zero outputs)", () => {
    expect(canFinalize([])).toBe(false);
  });

  it("is true once at least one format is selected", () => {
    expect(canFinalize(["doc"])).toBe(true);
  });
});

describe("formatsForRequest", () => {
  it("collapses to null when every format is selected (the step's own default)", () => {
    expect(formatsForRequest(DEFAULT_FINALIZE_FORMATS)).toBeNull();
    expect(formatsForRequest(["doc", "pdf", "html"])).toBeNull();
  });

  it("sends the normalized subset when fewer than all formats are selected", () => {
    expect(formatsForRequest(["doc"])).toEqual(["doc"]);
    expect(formatsForRequest(["doc", "html"])).toEqual(["html", "doc"]);
  });
});
