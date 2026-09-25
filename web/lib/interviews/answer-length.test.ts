import { describe, expect, it } from "vitest";

import { LONG_ANSWER_CHARS, isLongAnswer } from "@/lib/interviews/answer-length";

describe("isLongAnswer", () => {
  it("is false for a short answer", () => {
    expect(isLongAnswer("About 10TB.")).toBe(false);
  });

  it("is false right at the threshold", () => {
    expect(isLongAnswer("a".repeat(LONG_ANSWER_CHARS))).toBe(false);
  });

  it("is true once an answer exceeds the threshold", () => {
    expect(isLongAnswer("a".repeat(LONG_ANSWER_CHARS + 1))).toBe(true);
  });
});
