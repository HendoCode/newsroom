/**
 * Resolves the Auth.js session-signing secret (`web/auth.ts`). Pure and unit-tested so the
 * fallback rule can be verified without booting NextAuth.
 *
 * docker-compose's `${NEXTAUTH_SECRET:-}` substitution always defines the container env var —
 * as an empty string when the host var is unset, never truly absent. A plain `??` chain only
 * falls through on null/undefined, so it would pass that empty string straight to Auth.js as
 * `secret: ""`, which throws `MissingSecret`. Treat blank as unset too, so the POC fallback
 * (docs/auth.md) actually applies when no real secret has been configured.
 */

// POC-only: the session secret has no real security role here — anyone can declare any identity
// through the login form itself, so there is nothing it protects yet. Falling back to a fixed
// value (rather than requiring env setup) is what lets the POC boot with zero configuration; a
// real `NEXTAUTH_SECRET` can still be supplied to override it.
export const POC_FALLBACK_SECRET = "cmw-poc-identity-login-not-a-real-secret";

export function resolveAuthSecret(env: {
  NEXTAUTH_SECRET?: string;
  AUTH_SECRET?: string;
}): string {
  const configured = [env.NEXTAUTH_SECRET, env.AUTH_SECRET].find(
    (value) => value !== undefined && value.trim() !== "",
  );
  return configured ?? POC_FALLBACK_SECRET;
}
