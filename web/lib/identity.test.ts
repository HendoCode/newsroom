import { describe, expect, it } from "vitest";

import { parseIdentity } from "@/lib/identity";

describe("parseIdentity", () => {
  it("accepts any well-formed email, trimmed and lowercased", () => {
    expect(parseIdentity({ email: "  Jane.Doe@example.com  " })).toEqual({
      email: "jane.doe@example.com",
      name: null,
    });
  });

  it("accepts a display name, trimmed", () => {
    expect(parseIdentity({ email: "jane@example.com", name: "  Jane Doe  " })).toEqual({
      email: "jane@example.com",
      name: "Jane Doe",
    });
  });

  it("treats a blank/whitespace-only name as absent", () => {
    expect(parseIdentity({ email: "jane@example.com", name: "   " })).toEqual({
      email: "jane@example.com",
      name: null,
    });
  });

  it("accepts any domain — this is a declaration, not Workspace-restricted", () => {
    expect(parseIdentity({ email: "anyone@gmail.com" })).toEqual({
      email: "anyone@gmail.com",
      name: null,
    });
  });

  it("rejects a missing or blank email", () => {
    expect(parseIdentity({})).toBeNull();
    expect(parseIdentity({ email: "" })).toBeNull();
    expect(parseIdentity({ email: "   " })).toBeNull();
  });

  it("rejects an email with no @ or no domain dot", () => {
    expect(parseIdentity({ email: "not-an-email" })).toBeNull();
    expect(parseIdentity({ email: "user@localhost" })).toBeNull();
    expect(parseIdentity({ email: "user@" })).toBeNull();
    expect(parseIdentity({ email: "@example.com" })).toBeNull();
  });

  it("rejects non-string input (defensive against unexpected form values)", () => {
    expect(parseIdentity({ email: null })).toBeNull();
    expect(parseIdentity({ email: undefined })).toBeNull();
    expect(parseIdentity({ email: 42 })).toBeNull();
  });
});
