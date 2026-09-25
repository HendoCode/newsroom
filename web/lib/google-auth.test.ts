import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DEFAULT_ALLOWED_EMAIL_DOMAIN,
  emailDomain,
  getGoogleAuthConfig,
  resolveAllowedEmailDomain,
  resolveGoogleAuthConfig,
  signInErrorMessage,
} from "@/lib/google-auth";
import { resetSecretsProvider } from "@/lib/secrets/factory";

afterEach(() => {
  vi.unstubAllEnvs();
  resetSecretsProvider();
});

describe("resolveGoogleAuthConfig", () => {
  it("returns the trimmed creds when both are present", () => {
    expect(
      resolveGoogleAuthConfig({ GOOGLE_CLIENT_ID: " id ", GOOGLE_CLIENT_SECRET: " secret " }),
    ).toEqual({ clientId: "id", clientSecret: "secret" });
  });

  it("returns null when both are absent", () => {
    expect(resolveGoogleAuthConfig({})).toBeNull();
  });

  it("returns null when only the client id is set — never a half-configured provider", () => {
    expect(resolveGoogleAuthConfig({ GOOGLE_CLIENT_ID: "id" })).toBeNull();
  });

  it("returns null when only the client secret is set", () => {
    expect(resolveGoogleAuthConfig({ GOOGLE_CLIENT_SECRET: "secret" })).toBeNull();
  });

  it("treats blank/whitespace-only values as absent", () => {
    expect(
      resolveGoogleAuthConfig({ GOOGLE_CLIENT_ID: "  ", GOOGLE_CLIENT_SECRET: "secret" }),
    ).toBeNull();
  });
});

describe("resolveAllowedEmailDomain", () => {
  it("defaults to blank (no restriction) when unset", () => {
    expect(resolveAllowedEmailDomain(undefined)).toBe("");
    expect(DEFAULT_ALLOWED_EMAIL_DOMAIN).toBe("");
  });

  it("defaults to blank (no restriction) when blank", () => {
    expect(resolveAllowedEmailDomain("   ")).toBe("");
  });

  it("uses the configured domain, lowercased", () => {
    expect(resolveAllowedEmailDomain("Example.COM")).toBe("example.com");
  });
});

describe("emailDomain", () => {
  it("extracts and lowercases the domain half of an email", () => {
    expect(emailDomain("Jane@example.com")).toBe("example.com");
  });

  it("uses the last @ so a display name containing @ doesn't confuse it", () => {
    expect(emailDomain("weird@name@example.com")).toBe("example.com");
  });
});

describe("getGoogleAuthConfig", () => {
  it("resolves both creds through the secrets shim", async () => {
    vi.stubEnv("GOOGLE_CLIENT_ID", "client-id");
    vi.stubEnv("GOOGLE_CLIENT_SECRET", "client-secret");
    await expect(getGoogleAuthConfig()).resolves.toEqual({
      clientId: "client-id",
      clientSecret: "client-secret",
    });
  });

  it("resolves to null when unset — the local-dev-with-no-creds default", async () => {
    await expect(getGoogleAuthConfig()).resolves.toBeNull();
  });
});

describe("signInErrorMessage", () => {
  const google = { clientId: "id", clientSecret: "secret" };

  it("shows the domain-restriction wording for a real AccessDenied rejection", () => {
    expect(signInErrorMessage("AccessDenied", google, "example.com")).toMatch(/example\.com/i);
  });

  it("does NOT mention the domain/verified-account wording for any other error code — " +
    "regression coverage for a diagnosis where a token-exchange failure was collapsed to " +
    "'Configuration' by Auth.js and previously shown as a domain rejection", () => {
    for (const code of ["Configuration", "CallbackRouteError", "OAuthCallbackError", undefined]) {
      const message = signInErrorMessage(code, google, "example.com");
      expect(message).not.toMatch(/example\.com/i);
      expect(message).not.toMatch(/verified/i);
    }
  });

  it("uses the identity-form validation wording when Google isn't configured, regardless of code", () => {
    expect(signInErrorMessage("AccessDenied", null, "example.com")).toMatch(/valid email/i);
    expect(signInErrorMessage("CredentialsSignin", null, "example.com")).toMatch(/valid email/i);
  });
});
