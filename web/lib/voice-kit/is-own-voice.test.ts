import { describe, expect, it } from "vitest";

import { isOwnVoice } from "@/lib/voice-kit/is-own-voice";

describe("isOwnVoice", () => {
  it("matches when the email local part equals the voice slug", () => {
    expect(isOwnVoice("demo-mira", { email: "demo-mira@example.com", name: "Demo-mira H" })).toBe(true);
  });

  it("matches a dotted local part like demo-mira.henderson@", () => {
    expect(isOwnVoice("demo-mira", { email: "demo-mira.henderson@example.com" })).toBe(true);
  });

  it("does not match a different person's voice", () => {
    expect(isOwnVoice("demo-mira", { email: "demo-dana@example.com", name: "Demo-dana" })).toBe(false);
  });

  it("demo-dana is never someone else's — no courtesy note", () => {
    expect(isOwnVoice("demo-dana", { email: "demo-dana@example.com" })).toBe(true);
    expect(isOwnVoice("demo-dana", null)).toBe(true);
  });

  it("is false with no signed-in user info for a personal voice", () => {
    expect(isOwnVoice("demo-mira", null)).toBe(false);
    expect(isOwnVoice("demo-mira", undefined)).toBe(false);
  });

  it("falls back to matching the display name when email is absent", () => {
    expect(isOwnVoice("demo-dana", { name: "Demo-dana" })).toBe(true);
  });
});
