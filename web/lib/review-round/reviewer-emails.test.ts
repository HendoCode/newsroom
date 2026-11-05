import { describe, expect, it } from "vitest";

import { parseReviewerEmails } from "@/lib/review-round/reviewer-emails";

describe("parseReviewerEmails", () => {
  it("splits on commas and newlines, trims, and drops blanks", () => {
    expect(parseReviewerEmails("a@x.com, b@x.com\n c@x.com \n\n")).toEqual([
      "a@x.com",
      "b@x.com",
      "c@x.com",
    ]);
  });

  it("collapses an empty or whitespace-only textarea to null, not []", () => {
    expect(parseReviewerEmails("")).toBeNull();
    expect(parseReviewerEmails("   \n  ,  \n")).toBeNull();
  });

  it("preserves input order", () => {
    expect(parseReviewerEmails("z@x.com,a@x.com")).toEqual(["z@x.com", "a@x.com"]);
  });
});
