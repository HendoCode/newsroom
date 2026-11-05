import { describe, expect, it } from "vitest";

import { diffLines, hasChanges } from "@/lib/voice-kit/diff";

describe("diffLines", () => {
  it("marks every line unchanged when the texts are identical", () => {
    const result = diffLines("a\nb\nc", "a\nb\nc");
    expect(result).toEqual([
      { type: "unchanged", text: "a" },
      { type: "unchanged", text: "b" },
      { type: "unchanged", text: "c" },
    ]);
  });

  it("detects an appended line as added", () => {
    const result = diffLines("a\nb", "a\nb\nc");
    expect(result).toEqual([
      { type: "unchanged", text: "a" },
      { type: "unchanged", text: "b" },
      { type: "added", text: "c" },
    ]);
  });

  it("detects a removed middle line", () => {
    const result = diffLines("a\nb\nc", "a\nc");
    expect(result).toEqual([
      { type: "unchanged", text: "a" },
      { type: "removed", text: "b" },
      { type: "unchanged", text: "c" },
    ]);
  });

  it("detects a single-line replacement as remove + add", () => {
    const result = diffLines("hello world", "hello there");
    expect(result).toEqual([
      { type: "removed", text: "hello world" },
      { type: "added", text: "hello there" },
    ]);
  });
});

describe("hasChanges", () => {
  it("is false for identical text", () => {
    expect(hasChanges("same", "same")).toBe(false);
  });

  it("is true for different text", () => {
    expect(hasChanges("before", "after")).toBe(true);
  });
});
