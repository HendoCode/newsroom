import { afterEach, describe, expect, it, vi } from "vitest";

// Mock next-auth itself so we can capture the config function `auth.ts` passes it, without
// invoking real NextAuth internals (JWT encoding, route handler wiring, etc.) — the same
// isolation style as lib/session.test.ts, one level up the stack. `vi.mock` factories are
// hoisted above imports/consts, so the mock itself must come from `vi.hoisted`.
const { nextAuthMock } = vi.hoisted(() => ({
  nextAuthMock: vi.fn((config: unknown) => {
    void config; // captured only so the mock's call signature matches NextAuth's real one
    return { handlers: {}, auth: vi.fn(), signIn: vi.fn(), signOut: vi.fn() };
  }),
}));
vi.mock("next-auth", () => ({ default: (config: unknown) => nextAuthMock(config) }));
// Both provider factories are mocked to just echo their options back with a distinguishing `id`,
// so tests can tell which one `auth.ts` actually registered without invoking real OAuth/JWT
// internals.
vi.mock("next-auth/providers/credentials", () => ({
  default: vi.fn((config: Record<string, unknown>) => ({ id: "identity", ...config })),
}));
vi.mock("next-auth/providers/google", () => ({
  default: vi.fn((config: Record<string, unknown>) => ({ id: "google", ...config })),
}));

import type { GoogleProfile } from "next-auth/providers/google";

import { resetSecretsProvider } from "@/lib/secrets/factory";

import "@/auth";

afterEach(() => {
  vi.unstubAllEnvs();
  resetSecretsProvider();
});

interface AuthConfig {
  secret: string;
  providers: Array<Record<string, unknown>>;
  callbacks: {
    // `GoogleProfile` (re-exported by next-auth/providers/google from @auth/core, pinned at
    // 0.41.3 — see package-lock.json) is the REAL ID-token claim shape Google's OIDC provider
    // hands `signIn`, not a hand-rolled `{email, email_verified}` pair. The previous inline type
    // here structurally could not express a realistic payload (extra claims, a spoofed/missing
    // `hd`, etc.) — see the `realGoogleProfile` fixture below for why that gap mattered.
    signIn: (params: {
      account?: { provider: string } | null;
      profile?: Partial<GoogleProfile>;
    }) => boolean;
  };
}

/**
 * A fully-populated, realistic Google ID-token claims object — every field the pinned
 * `@auth/core@0.41.3` `GoogleProfile` type declares (node_modules/@auth/core/src/providers/
 * google.ts), not just the two fields our own callback reads.
 *
 * This shape is grounded in the library's own source, not guessed. Our Google provider
 * (web/auth.ts) is registered with no `idToken: false` override, so
 * `@auth/core`'s OAuth callback handler (node_modules/@auth/core/src/lib/actions/callback/oauth/
 * callback.ts: `requireIdToken` is true for `type: "oidc"` providers, and
 * `profile = o.getValidatedIdTokenClaims(...)`) hands `signIn` the DECODED ID-TOKEN JWT CLAIMS
 * verbatim — never a legacy tokeninfo-endpoint response. JWT claims are plain JSON, so
 * `email_verified` is guaranteed to arrive as a genuine JSON boolean on this code path, and every
 * other field below (aud/azp/exp/iat/iss/jti/sub/picture/locale/given_name/family_name/hd) is a
 * real claim Google's ID tokens carry, per that same type declaration.
 */
function realGoogleProfile(overrides: Partial<GoogleProfile> = {}): GoogleProfile {
  return {
    aud: "test-client-id.apps.googleusercontent.com",
    azp: "test-client-id.apps.googleusercontent.com",
    email: "jane@example.com",
    email_verified: true,
    exp: 9999999999,
    family_name: "Doe",
    given_name: "Jane",
    hd: "example.com",
    iat: 1000000000,
    iss: "https://accounts.google.com",
    jti: "test-jti-0000",
    locale: "en",
    name: "Jane Doe",
    nbf: 999999999,
    picture: "https://lh3.googleusercontent.com/a/test-avatar",
    sub: "109876543210987654321",
    ...overrides,
  };
}

function getConfigFn(): (request: unknown) => Promise<AuthConfig> {
  const fn: unknown = nextAuthMock.mock.calls[0]?.[0];
  if (typeof fn !== "function") {
    throw new Error("NextAuth was not called with a config function");
  }
  return fn as (request: unknown) => Promise<AuthConfig>;
}

describe("auth.ts", () => {
  it("passes NextAuth an async config function, not a plain object", () => {
    // Required so `secret` can be awaited from the secrets shim (web/AGENTS.md "Auth" section) —
    // the plain-object config form has no way to await anything.
    expect(nextAuthMock).toHaveBeenCalledTimes(1);
    expect(typeof nextAuthMock.mock.calls[0]?.[0]).toBe("function");
  });

  it("resolves `secret` from NEXTAUTH_SECRET via the env backend", async () => {
    vi.stubEnv("NEXTAUTH_SECRET", "my-real-secret");
    const config = await getConfigFn()(undefined);
    expect(config.secret).toBe("my-real-secret");
  });

  it("falls back to the fixed POC secret when NEXTAUTH_SECRET is unset", async () => {
    const config = await getConfigFn()(undefined);
    expect(config.secret).toBe("cmw-poc-identity-login-not-a-real-secret");
  });

  it("falls back to the POC secret when NEXTAUTH_SECRET resolves to a blank value", async () => {
    // Regression coverage for the MissingSecret fix (#29): docker-compose's `${VAR:-}` always
    // defines the container env var, empty string when the host var is unset — resolveAuthSecret
    // must treat that the same as truly unset even when the value arrives via the secrets shim
    // rather than a raw process.env read.
    vi.stubEnv("NEXTAUTH_SECRET", "");
    const config = await getConfigFn()(undefined);
    expect(config.secret).toBe("cmw-poc-identity-login-not-a-real-secret");
  });

  it("falls through to AUTH_SECRET when NEXTAUTH_SECRET is blank but AUTH_SECRET is real", async () => {
    vi.stubEnv("NEXTAUTH_SECRET", "");
    vi.stubEnv("AUTH_SECRET", "real-secret");
    const config = await getConfigFn()(undefined);
    expect(config.secret).toBe("real-secret");
  });
});

describe("provider selection", () => {
  it("registers only the identity Credentials provider when Google creds are absent", async () => {
    const config = await getConfigFn()(undefined);
    expect(config.providers).toHaveLength(1);
    expect(config.providers[0]?.id).toBe("identity");
  });

  it("registers only the Google provider when both creds are configured — no declare-any-email bypass", async () => {
    vi.stubEnv("GOOGLE_CLIENT_ID", "a-client-id");
    vi.stubEnv("GOOGLE_CLIENT_SECRET", "a-client-secret");
    vi.stubEnv("AUTH_ALLOWED_EMAIL_DOMAIN", "example.com");
    const config = await getConfigFn()(undefined);
    expect(config.providers).toHaveLength(1);
    expect(config.providers[0]?.id).toBe("google");
  });

  it("falls back to the Credentials provider when only one Google cred is set", async () => {
    vi.stubEnv("GOOGLE_CLIENT_ID", "a-client-id");
    const config = await getConfigFn()(undefined);
    expect(config.providers[0]?.id).toBe("identity");
  });

  it("omits the hd hint when no allowed domain is configured", async () => {
    vi.stubEnv("GOOGLE_CLIENT_ID", "a-client-id");
    vi.stubEnv("GOOGLE_CLIENT_SECRET", "a-client-secret");
    const config = await getConfigFn()(undefined);
    const authorization = config.providers[0]?.authorization as { params: { hd?: string; prompt?: string } };
    expect(authorization.params.prompt).toBe("select_account");
    expect(authorization.params.hd).toBeUndefined();
  });

  it("honors a configured AUTH_ALLOWED_EMAIL_DOMAIN for the hd hint", async () => {
    vi.stubEnv("GOOGLE_CLIENT_ID", "a-client-id");
    vi.stubEnv("GOOGLE_CLIENT_SECRET", "a-client-secret");
    vi.stubEnv("AUTH_ALLOWED_EMAIL_DOMAIN", "acme-corp.example");
    const config = await getConfigFn()(undefined);
    const authorization = config.providers[0]?.authorization as { params: { hd: string } };
    expect(authorization.params.hd).toBe("acme-corp.example");
  });
});

describe("signIn callback (domain restriction)", () => {
  it("allows a verified account on the allowed domain", async () => {
    vi.stubEnv("GOOGLE_CLIENT_ID", "a-client-id");
    vi.stubEnv("GOOGLE_CLIENT_SECRET", "a-client-secret");
    vi.stubEnv("AUTH_ALLOWED_EMAIL_DOMAIN", "example.com");
    const config = await getConfigFn()(undefined);
    expect(
      config.callbacks.signIn({
        account: { provider: "google" },
        profile: { email: "jane@example.com", email_verified: true },
      }),
    ).toBe(true);
  });

  it("rejects a verified account outside the allowed domain", async () => {
    vi.stubEnv("GOOGLE_CLIENT_ID", "a-client-id");
    vi.stubEnv("GOOGLE_CLIENT_SECRET", "a-client-secret");
    vi.stubEnv("AUTH_ALLOWED_EMAIL_DOMAIN", "example.com");
    const config = await getConfigFn()(undefined);
    expect(
      config.callbacks.signIn({
        account: { provider: "google" },
        profile: { email: "jane@other.com", email_verified: true },
      }),
    ).toBe(false);
  });

  it("rejects an unverified email even on the allowed domain", async () => {
    vi.stubEnv("GOOGLE_CLIENT_ID", "a-client-id");
    vi.stubEnv("GOOGLE_CLIENT_SECRET", "a-client-secret");
    vi.stubEnv("AUTH_ALLOWED_EMAIL_DOMAIN", "example.com");
    const config = await getConfigFn()(undefined);
    expect(
      config.callbacks.signIn({
        account: { provider: "google" },
        profile: { email: "jane@example.com", email_verified: false },
      }),
    ).toBe(false);
  });

  it("rejects a missing email", async () => {
    vi.stubEnv("GOOGLE_CLIENT_ID", "a-client-id");
    vi.stubEnv("GOOGLE_CLIENT_SECRET", "a-client-secret");
    vi.stubEnv("AUTH_ALLOWED_EMAIL_DOMAIN", "example.com");
    const config = await getConfigFn()(undefined);
    expect(
      config.callbacks.signIn({ account: { provider: "google" }, profile: { email_verified: true } }),
    ).toBe(false);
  });

  it("allows any verified account when no allowed domain is configured", async () => {
    vi.stubEnv("GOOGLE_CLIENT_ID", "a-client-id");
    vi.stubEnv("GOOGLE_CLIENT_SECRET", "a-client-secret");
    const config = await getConfigFn()(undefined);
    expect(
      config.callbacks.signIn({
        account: { provider: "google" },
        profile: { email: "jane@anywhere.example", email_verified: true },
      }),
    ).toBe(true);
  });

  it("passes through non-Google sign-ins unchanged (the Credentials fallback path)", async () => {
    const config = await getConfigFn()(undefined);
    expect(config.callbacks.signIn({ account: { provider: "identity" } })).toBe(true);
  });
});

// This project's Google OAuth client is Internal user-type, so Google's own consent screen
// blocks any out-of-organization account before our app is ever reached — the org gate everyone
// has observed working is Google's, not ours. That leaves our own `signIn` callback's domain
// check (auth.ts:103-108) genuinely unverified: the tests above pass, but their minimal
// `{email, email_verified}` fixture is drawn from the same handful of fields every case already
// expects, never a realistic full Google ID-token payload. These tests drive the SAME real
// callback (extracted from the real, unmocked `web/auth.ts` config — see getConfigFn above) with
// a fixture shaped like what Google actually sends (realGoogleProfile, above), so a regression
// that stops rejecting an out-of-domain account fails here regardless of which extra claims a
// real profile happens to carry.
//
// What this DOES prove: our own domain/verified-email gate, in isolation, correctly rejects an
// out-of-domain account and does not accidentally key off `hd` (a UI hint, not enforced by
// Google) instead of the verified `email` claim.
//
// What this does NOT prove: it does not exercise the network OAuth handshake, Google's token
// endpoint, or ID-token signature verification — those are `@auth/core`'s own well-tested
// plumbing, not this app's code, and are unaffected by the two lines under test here. It also
// does not prove anything about Google's Internal-app org gate, which today masks this exact
// scenario in the live product: as long as the OAuth client stays Internal, an out-of-org account
// never reaches this code path in reality, so this suite is what stands behind the boundary until
// that masking condition changes (e.g. the client is ever made External) or a genuinely
// different-domain in-org Workspace account becomes available to test against live.
describe("signIn callback — realistic Google profile shapes (closes the fixture gap)", () => {
  it("allows a verified, realistic in-domain profile carrying every real ID-token claim", async () => {
    vi.stubEnv("GOOGLE_CLIENT_ID", "a-client-id");
    vi.stubEnv("GOOGLE_CLIENT_SECRET", "a-client-secret");
    vi.stubEnv("AUTH_ALLOWED_EMAIL_DOMAIN", "example.com");
    const config = await getConfigFn()(undefined);
    expect(
      config.callbacks.signIn({ account: { provider: "google" }, profile: realGoogleProfile() }),
    ).toBe(true);
  });

  it("rejects a verified, realistic out-of-domain Workspace profile — the boundary this task exists to verify", async () => {
    vi.stubEnv("GOOGLE_CLIENT_ID", "a-client-id");
    vi.stubEnv("GOOGLE_CLIENT_SECRET", "a-client-secret");
    vi.stubEnv("AUTH_ALLOWED_EMAIL_DOMAIN", "example.com");
    const config = await getConfigFn()(undefined);
    const outOfDomain = realGoogleProfile({ email: "jane@acme-corp.example", hd: "acme-corp.example" });
    expect(config.callbacks.signIn({ account: { provider: "google" }, profile: outOfDomain })).toBe(
      false,
    );
  });

  it("rejects a verified personal Google account (no hd claim at all, as real personal accounts send)", async () => {
    vi.stubEnv("GOOGLE_CLIENT_ID", "a-client-id");
    vi.stubEnv("GOOGLE_CLIENT_SECRET", "a-client-secret");
    vi.stubEnv("AUTH_ALLOWED_EMAIL_DOMAIN", "example.com");
    const config = await getConfigFn()(undefined);
    const personal = realGoogleProfile({ email: "jane.doe@gmail.com" });
    delete personal.hd;
    expect(config.callbacks.signIn({ account: { provider: "google" }, profile: personal })).toBe(false);
  });

  it("gates on the verified email domain, not the hd hint — rejects even when hd matches the allowed domain", async () => {
    // Regression guard for auth.ts's own documented invariant ("hd is only a UI hint... the
    // signIn callback is the actual gate") — hd is Google-attested, not user-forgeable, but
    // nothing stops a future edit from reading the wrong field. This fixture is the shape Google
    // sends when the hd hint round-trips as requested but the signed-in account itself belongs to
    // a different domain (e.g. picking a non-hinted account from the chooser).
    vi.stubEnv("GOOGLE_CLIENT_ID", "a-client-id");
    vi.stubEnv("GOOGLE_CLIENT_SECRET", "a-client-secret");
    vi.stubEnv("AUTH_ALLOWED_EMAIL_DOMAIN", "example.com");
    const config = await getConfigFn()(undefined);
    const mismatchedHd = realGoogleProfile({ email: "jane@acme-corp.example", hd: "example.com" });
    expect(config.callbacks.signIn({ account: { provider: "google" }, profile: mismatchedHd })).toBe(
      false,
    );
  });

  it("documents current strict-boolean behavior for a non-boolean truthy email_verified (defense-in-depth only — the real ID-token decode path above guarantees this can't occur in production)", async () => {
    // Gift for cmw-email-verified-check-review, not acted on here: this fixture requires an
    // unsafe cast because a real Google ID token cannot produce this shape (see realGoogleProfile's
    // doc comment) — but the TS type alone no longer prevents expressing it, which is the fixture
    // gap this task was asked to close. Today's `profile?.email_verified !== true` (auth.ts:106)
    // rejects this truthy-but-non-boolean value; that strictness is intentionally left unchanged.
    vi.stubEnv("GOOGLE_CLIENT_ID", "a-client-id");
    vi.stubEnv("GOOGLE_CLIENT_SECRET", "a-client-secret");
    vi.stubEnv("AUTH_ALLOWED_EMAIL_DOMAIN", "example.com");
    const config = await getConfigFn()(undefined);
    const stringVerified = {
      ...realGoogleProfile(),
      email_verified: "true",
    } as unknown as Partial<GoogleProfile>;
    expect(
      config.callbacks.signIn({ account: { provider: "google" }, profile: stringVerified }),
    ).toBe(false);
  });
});
