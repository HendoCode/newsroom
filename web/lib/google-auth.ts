/**
 * Real Google Workspace OAuth sign-in, restricted to a single email domain (docs/auth.md).
 *
 * Pure, unit-tested resolvers live here (no NextAuth, no network) so `web/auth.ts` and the
 * `/signin` screen can both decide "is Google active, and what domain does it allow" without
 * duplicating the rule. `getGoogleAuthConfig` is the one IO seam — it resolves the two creds
 * through the same secrets shim `NEXTAUTH_SECRET` already reads (`lib/secrets/factory.ts`).
 */

import { getSecret } from "@/lib/secrets/factory";

export interface GoogleAuthConfig {
  clientId: string;
  clientSecret: string;
}

export const DEFAULT_ALLOWED_EMAIL_DOMAIN = "";

/**
 * Google is the sign-in method only when BOTH creds are configured (non-blank); otherwise null,
 * and the caller falls back to the identity-declaration login. This is the single switch that
 * decides which provider is registered in `web/auth.ts` — the two are never both active, which is
 * what makes the declare-any-email path unreachable once Google is wired up.
 */
export function resolveGoogleAuthConfig(env: {
  GOOGLE_CLIENT_ID?: string;
  GOOGLE_CLIENT_SECRET?: string;
}): GoogleAuthConfig | null {
  const clientId = env.GOOGLE_CLIENT_ID?.trim();
  const clientSecret = env.GOOGLE_CLIENT_SECRET?.trim();
  if (!clientId || !clientSecret) return null;
  return { clientId, clientSecret };
}

/** The Workspace domain Google sign-in is restricted to — blank (no restriction) when unset. */
export function resolveAllowedEmailDomain(value: string | undefined): string {
  const trimmed = value?.trim();
  return trimmed ? trimmed.toLowerCase() : DEFAULT_ALLOWED_EMAIL_DOMAIN;
}

/** The domain half of an email address, lowercased — used to check against the allowed domain. */
export function emailDomain(email: string): string {
  return email.slice(email.lastIndexOf("@") + 1).toLowerCase();
}

/** Resolves `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` through the secrets shim. */
export async function getGoogleAuthConfig(): Promise<GoogleAuthConfig | null> {
  const [clientId, clientSecret] = await Promise.all([
    getSecret("GOOGLE_CLIENT_ID"),
    getSecret("GOOGLE_CLIENT_SECRET"),
  ]);
  return resolveGoogleAuthConfig({ GOOGLE_CLIENT_ID: clientId, GOOGLE_CLIENT_SECRET: clientSecret });
}

/**
 * User-facing text for a `/signin?error=...` failure. Auth.js only surfaces `AccessDenied`
 * verbatim when our own `signIn` callback in `web/auth.ts` actually ran and returned `false` —
 * every other code (`Configuration`, the catch-all a `CallbackRouteError`/`OAuthCallbackError`
 * collapses to, etc.) means the failure happened before that domain/verification check ever ran.
 * Describing those as a domain rejection is actively misleading: observed during a diagnosis of a
 * token-exchange host mismatch, where the mismatch — unrelated to the account being signed in —
 * surfaced as "you need a verified account," sending the investigation down the wrong path for
 * multiple retries before server logs proved the callback never fired.
 */
export function signInErrorMessage(
  error: string | undefined,
  google: GoogleAuthConfig | null,
  allowedEmailDomain: string,
): string {
  if (!google) return "Enter a valid email address to continue.";
  if (error === "AccessDenied") {
    return allowedEmailDomain
      ? `Sign-in failed. You need a verified @${allowedEmailDomain} Google account.`
      : "Sign-in failed. Your Google account could not be verified.";
  }
  return "Sign-in failed. Something went wrong completing Google sign-in — please try again.";
}
