import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// Avoid loading the real NextAuth wiring (`@/auth`) — the server action is irrelevant to what
// this page renders, and jsdom can't resolve next-auth's server-only internals.
vi.mock("@/lib/auth-actions", () => ({
  signInWithIdentity: vi.fn(),
  signInWithGoogle: vi.fn(),
  signOutAction: vi.fn(),
}));

const { getGoogleAuthConfig } = vi.hoisted(() => ({ getGoogleAuthConfig: vi.fn() }));
vi.mock("@/lib/google-auth", async () => {
  const actual = await vi.importActual<typeof import("@/lib/google-auth")>("@/lib/google-auth");
  return { ...actual, getGoogleAuthConfig };
});

import SignInPage from "@/app/signin/page";

afterEach(() => {
  vi.unstubAllEnvs();
  getGoogleAuthConfig.mockReset();
  getGoogleAuthConfig.mockResolvedValue(null);
});

describe("SignInPage — Google not configured (local dev fallback)", () => {
  it("asks for an email with the you@example.com placeholder — no password, no OAuth button", async () => {
    render(await SignInPage({ searchParams: Promise.resolve({}) }));

    const email = screen.getByLabelText("Email");
    expect(email).toHaveAttribute("type", "email");
    expect(email).toHaveAttribute("placeholder", "you@example.com");
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /google/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue" })).toBeInTheDocument();
  });

  it("offers an optional display name field", async () => {
    render(await SignInPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByLabelText(/Display name/)).toHaveAttribute("type", "text");
  });

  it("shows no error alert by default", async () => {
    render(await SignInPage({ searchParams: Promise.resolve({}) }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows a validation message when redirected back with an error", async () => {
    render(await SignInPage({ searchParams: Promise.resolve({ error: "CredentialsSignin" }) }));
    expect(screen.getByRole("alert")).toHaveTextContent(/valid email/i);
  });
});

describe("SignInPage — Google configured", () => {
  it("renders only a Sign in with Google button — no email/declaration form (no bypass)", async () => {
    getGoogleAuthConfig.mockResolvedValue({ clientId: "id", clientSecret: "secret" });
    render(await SignInPage({ searchParams: Promise.resolve({}) }));

    expect(screen.getByRole("button", { name: /sign in with google/i })).toBeInTheDocument();
    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Display name/)).not.toBeInTheDocument();
  });

  it("shows the generic Google wording when no allowed domain is configured", async () => {
    getGoogleAuthConfig.mockResolvedValue({ clientId: "id", clientSecret: "secret" });
    render(await SignInPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByText(/verified Google account/)).toBeInTheDocument();
  });

  it("mentions a configured AUTH_ALLOWED_EMAIL_DOMAIN instead of the default", async () => {
    vi.stubEnv("AUTH_ALLOWED_EMAIL_DOMAIN", "example.com");
    getGoogleAuthConfig.mockResolvedValue({ clientId: "id", clientSecret: "secret" });
    render(await SignInPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByText(/@example\.com/)).toBeInTheDocument();
  });

  it("shows a domain-restriction error message only for a real AccessDenied rejection", async () => {
    vi.stubEnv("AUTH_ALLOWED_EMAIL_DOMAIN", "example.com");
    getGoogleAuthConfig.mockResolvedValue({ clientId: "id", clientSecret: "secret" });
    render(await SignInPage({ searchParams: Promise.resolve({ error: "AccessDenied" }) }));
    expect(screen.getByRole("alert")).toHaveTextContent(/example\.com/i);
  });

  it("does NOT claim a domain rejection for a non-AccessDenied error (regression: a " +
    "token-exchange/config failure was previously shown as 'you need a verified account', " +
    "misdiagnosing a real account as rejected)", async () => {
    getGoogleAuthConfig.mockResolvedValue({ clientId: "id", clientSecret: "secret" });
    // "Configuration" is what Auth.js's own error-type allowlist collapses a CallbackRouteError
    // (e.g. the token-exchange redirect_uri mismatch this bug produced) down to — see
    // node_modules/@auth/core/index.js's `isClientError`/`clientErrors` set and
    // node_modules/@auth/core/errors.js's `CallbackRouteError` (not in that set).
    render(await SignInPage({ searchParams: Promise.resolve({ error: "Configuration" }) }));
    const alert = screen.getByRole("alert");
    expect(alert).not.toHaveTextContent(/example\.com/i);
    expect(alert).not.toHaveTextContent(/verified/i);
    expect(alert).toHaveTextContent(/went wrong/i);
  });
});
