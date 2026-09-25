import { describe, expect, it } from "vitest";

import { POC_FALLBACK_SECRET, resolveAuthSecret } from "@/lib/auth-secret";

describe("resolveAuthSecret", () => {
  it("uses NEXTAUTH_SECRET when configured", () => {
    expect(resolveAuthSecret({ NEXTAUTH_SECRET: "real-secret" })).toBe("real-secret");
  });

  it("falls back to AUTH_SECRET when NEXTAUTH_SECRET is unset", () => {
    expect(resolveAuthSecret({ AUTH_SECRET: "other-secret" })).toBe("other-secret");
  });

  it("prefers NEXTAUTH_SECRET over AUTH_SECRET when both are configured", () => {
    expect(
      resolveAuthSecret({ NEXTAUTH_SECRET: "primary", AUTH_SECRET: "secondary" }),
    ).toBe("primary");
  });

  it("falls back to the POC secret when both are missing", () => {
    expect(resolveAuthSecret({})).toBe(POC_FALLBACK_SECRET);
  });

  it("treats an empty-string env var as unset (docker-compose's `${VAR:-}` default)", () => {
    expect(resolveAuthSecret({ NEXTAUTH_SECRET: "" })).toBe(POC_FALLBACK_SECRET);
    expect(resolveAuthSecret({ NEXTAUTH_SECRET: "", AUTH_SECRET: "" })).toBe(POC_FALLBACK_SECRET);
  });

  it("treats a whitespace-only env var as unset too", () => {
    expect(resolveAuthSecret({ NEXTAUTH_SECRET: "   " })).toBe(POC_FALLBACK_SECRET);
  });

  it("falls through to AUTH_SECRET when NEXTAUTH_SECRET is blank but AUTH_SECRET is real", () => {
    expect(resolveAuthSecret({ NEXTAUTH_SECRET: "", AUTH_SECRET: "real-secret" })).toBe(
      "real-secret",
    );
  });
});
