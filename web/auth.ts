import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";

import { resolveAuthSecret } from "@/lib/auth-secret";
import { emailDomain, getGoogleAuthConfig, resolveAllowedEmailDomain } from "@/lib/google-auth";
import { parseIdentity } from "@/lib/identity";
import { getSecret } from "@/lib/secrets/factory";

/**
 * NextAuth (Auth.js v5) wiring for the `web/` service (docs/design.md §6 "Auth"; domain model
 * §1.17; docs/auth.md). Two sign-in providers, mutually exclusive:
 *
 *  - **Google**, restricted to `AUTH_ALLOWED_EMAIL_DOMAIN` (no default restriction — any
 *    verified Google account when unset), active whenever
 *    `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` are both configured — real deployments.
 *  - **Identity-declaration** (no password, no OAuth — declaring a well-formed email signs you in
 *    as that pretend identity), active ONLY when Google isn't configured — local dev with no
 *    creds set. The two are never both registered, so the declare-any-email path is unreachable
 *    once Google is wired up.
 *
 * Design notes:
 *  - Authorization is FLAT: sign-in gates the app; once in, roles are attribution-only and are
 *    NOT carried on the session (domain model §1.17, design.md §2). No per-role gating here.
 *  - Sessions are JWT-backed. The durable Mongo user record (§1.17, D3) is a downstream ticket;
 *    this module is the identity seam the rest of the app reads via `lib/session.ts`.
 */

// NextAuth's config-as-function form (awaited by initAuth on every middleware request / RSC
// session read / route handler — see next-auth's own index.ts) is what lets `secret` resolve
// through the secrets shim (web/lib/secrets/) instead of a raw process.env read: with
// SECRETS_BACKEND=aws/azure this picks up a rotated NEXTAUTH_SECRET with no rebuild/restart. The
// `env` backend (the default) is edge-safe (a plain process.env read); aws/azure are not — see
// web/AGENTS.md's "Auth" section for that limitation on the edge-bundled middleware path.
// `resolveAuthSecret` (lib/auth-secret.ts) still owns the fallback rule itself — treating a
// blank/whitespace-only value as unset too (docker-compose's `${VAR:-}` always defines the
// container env var; Auth.js throws MissingSecret on `secret: ""`) — fed values resolved through
// the shim instead of raw `process.env` reads.
export const { handlers, auth, signIn, signOut } = NextAuth(async () => {
  const google = await getGoogleAuthConfig();
  const allowedEmailDomain = resolveAllowedEmailDomain(process.env.AUTH_ALLOWED_EMAIL_DOMAIN);

  return {
    // Required by Auth.js whenever the deployment host isn't NEXTAUTH_URL's default
    // (auth.js.org/reference/nextjs#trusthost). Does NOT by itself make OAuth callback URLs
    // correct on a bare Next.js standalone server — see AUTH_URL below (docker-compose.yml),
    // which is the setting that actually fixes redirect_uri construction. Observed during a
    // diagnosis of a token-exchange host mismatch: trustHost alone let a request's inferred
    // origin silently resolve to the container's own bind address instead of the real host.
    trustHost: true,
    secret: resolveAuthSecret({
      NEXTAUTH_SECRET: await getSecret("NEXTAUTH_SECRET"),
      AUTH_SECRET: await getSecret("AUTH_SECRET"),
    }),
    session: { strategy: "jwt" },
    pages: {
      // Our own sign-in landing (Google button, or the identity form — see app/signin/page.tsx);
      // unauthenticated access is redirected here with a callbackUrl. Sign-in failures (a
      // rejected domain, a blank/malformed email) also land here.
      signIn: "/signin",
      error: "/signin",
    },
    providers: google
      ? [
          Google({
            clientId: google.clientId,
            clientSecret: google.clientSecret,
            // `hd` is only a UI hint to Google's account chooser — Google does not enforce it
            // server-side, so the `signIn` callback below is the actual gate. When no domain is
            // configured the hint is omitted entirely (no restriction).
            authorization: {
              params: {
                prompt: "select_account",
                ...(allowedEmailDomain ? { hd: allowedEmailDomain } : {}),
              },
            },
          }),
        ]
      : [
          Credentials({
            id: "identity",
            name: "Identity",
            credentials: {
              email: { label: "Email", type: "email" },
              name: { label: "Display name", type: "text" },
            },
            // No password check, no lookup — this IS the sign-in: declaring a well-formed email
            // signs you in as that (pretend) identity. `parseIdentity` is the only validation
            // (lib/identity.ts). Registered ONLY as the no-Google-creds local-dev fallback.
            authorize(credentials) {
              const identity = parseIdentity({ email: credentials?.email, name: credentials?.name });
              if (!identity) return null;
              return { id: identity.email, email: identity.email, name: identity.name, image: null };
            },
          }),
        ],
    callbacks: {
      // Middleware gate (see web/middleware.ts): allow the public sign-in route; require a
      // declared identity for everything else. Flat once signed in — no per-role checks here
      // (domain model §1.17). Returning false makes NextAuth redirect to `pages.signIn` with a
      // callbackUrl.
      authorized({ auth: session, request }) {
        const { pathname } = request.nextUrl;
        if (pathname.startsWith("/signin")) return true;
        return Boolean(session?.user?.email);
      },
      // Domain restriction (docs/auth.md): only relevant for the Google provider — the
      // Credentials fallback has no OAuth profile to check, so it passes through unchanged.
      // With no allowed domain configured, any verified Google account signs in; otherwise
      // reject anything but a verified @<allowedEmailDomain> account.
      signIn({ account, profile }) {
        if (account?.provider !== "google") return true;
        const email = profile?.email;
        if (!email || profile?.email_verified !== true) return false;
        if (!allowedEmailDomain) return true;
        return emailDomain(email) === allowedEmailDomain;
      },
    },
  };
});
