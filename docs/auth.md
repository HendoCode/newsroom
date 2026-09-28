# Authentication

Sign-in for the `web/` service is **Google Workspace OAuth, restricted to a single email
domain** (default `example.com`) in any real deployment, with a **local-dev-only fallback** to a
no-password identity-declaration login when Google isn't configured. Authorization is **flat**:
signing in gates the whole app, and once signed in anyone can act on anything — roles are
attribution only and never gate permissions (domain model §1.17).

## How it works today

- **Provider selection is automatic and mutually exclusive:** [`web/auth.ts`](../web/auth.ts)
  checks whether `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are both configured
  (`web/lib/google-auth.ts` `getGoogleAuthConfig`, resolved through the secrets shim — the same
  layer `NEXTAUTH_SECRET` reads through). If both are set, NextAuth registers **only** the Google
  provider. If either is blank, it registers **only** the identity-declaration `Credentials`
  provider. The two are never both active — this is what makes the flat "declare any email"
  login unreachable once Google is wired up, not a separate feature flag.
- **Google mode (real deployments):** `/signin` renders a single "Sign in with Google" button
  (`web/app/signin/page.tsx`, wired through `signInWithGoogle` in
  [`web/lib/auth-actions.ts`](../web/lib/auth-actions.ts)). The OAuth `authorization` params
  include `hd=<allowed domain>` as a hint to Google's account chooser, but Google does not enforce
  `hd` server-side — the actual gate is `web/auth.ts`'s `signIn` callback, which rejects any
  account whose profile isn't `email_verified` or whose email domain doesn't match
  `AUTH_ALLOWED_EMAIL_DOMAIN` (default `example.com`; see `web/lib/google-auth.ts`
  `resolveAllowedEmailDomain`/`emailDomain`). Callback route: `/api/auth/callback/google`.
- **Identity-declaration mode (local dev with no Google creds):** unchanged from the original POC
  — `/signin` shows a form asking for an email (placeholder `you@example.com`) and an optional display
  name; submitting signs you in as that declared identity, no password, no OAuth round trip
  (`web/lib/identity.ts`'s `parseIdentity`, pure and unit-tested — rejects only a blank/malformed
  email). Wired through `signInWithIdentity` in `web/lib/auth-actions.ts`.
- **Session secret:** `NEXTAUTH_SECRET` is optional in both modes — `web/auth.ts` falls back to a
  fixed POC value when unset. This is orthogonal to which sign-in provider is active.
- **Typed accessor:** [`web/lib/session.ts`](../web/lib/session.ts) exposes `getCurrentUser()`
  (→ `AppUser | null`) and `requireUser()` (→ `AppUser`, redirecting to `/signin` otherwise).
  `AppUser` is `{ email, name, image }`, mirroring the domain model's User/Identity (§1.17) —
  identical shape regardless of which provider issued the session (Google populates `image` from
  the account's avatar; identity-declaration always has `image: null`). Roles are deliberately
  absent — authorization is flat.
- **Route protection:** [`web/middleware.ts`](../web/middleware.ts) requires a signed-in identity
  for every route except the public sign-in page, NextAuth's own endpoints, `/api/health` (the
  container healthcheck), and static assets. Unauthenticated requests are redirected to
  `/signin?callbackUrl=…`.
- **Sign-out:** the header's sign-out control calls `signOutAction` (`web/lib/auth-actions.ts`),
  which clears the session and returns to `/signin`.
- **Expert deep link:** `/interviews/<interviewId>` requires the same sign-in as everything else —
  not an anonymous or magic-link bypass.

This is deliberately identical in Docker (`docker compose up`) and under `npm run dev` — there is
no separate dev-only flag or override file; the provider choice is driven entirely by whether
Google creds are present, per [`docs/local-dev.md`](local-dev.md).

**Production has no outer gate — this sign-in is the whole access control.** A deployed build on
a public IP/domain used to sit behind a shared HTTP basic-auth password (a reverse proxy in front
of `web`) as well; that outer gate was removed 2026-08-08 (`cmw-remove-edge-basic-auth`) once
Hendo judged it redundant with the app's own login. That makes `AUTH_ALLOWED_EMAIL_DOMAIN`
load-bearing for the first time in a way it never was while basic-auth was also in front — see
`web/AGENTS.md`'s "Auth" section for why that check is currently verified only by
`auth.test.ts`, not by any live sign-in (Google's own org-level gate blocks a non-org account
before our `signIn` callback is ever reached, so a successful real sign-in proves Google's gate
works, not ours).

## Configuration

| Env var | Where it's read | Default | Notes |
| --- | --- | --- | --- |
| `GOOGLE_CLIENT_ID` | `web/auth.ts` via the secrets shim | — (unset) | Both this and the secret below must be set for Google mode to activate. |
| `GOOGLE_CLIENT_SECRET` | `web/auth.ts` via the secrets shim | — (unset) | Never commit a real value — placeholders only in `.env.example`. |
| `AUTH_ALLOWED_EMAIL_DOMAIN` | `web/auth.ts` (plain env — not a secret) | `example.com` | The domain a verified Google account's email must match. Only enforced when Google mode is active. |
| `NEXTAUTH_SECRET` | `web/auth.ts` via the secrets shim | fixed POC value | Session-cookie signing secret; orthogonal to which sign-in provider is active. |

A Google Cloud OAuth 2.0 Web client must be provisioned once, with these redirect URIs registered:
`https://example.com/api/auth/callback/google` (production),
`https://localhost/api/auth/callback/google` (the `docker compose up` full stack at its default
`WEB_PORT` — HTTPS-only, see `docs/local-dev.md`), and
`http://localhost:3000/api/auth/callback/google` (the separate, plain-HTTP `npm run dev`
workflow, `docs/local-dev.md` "Signing in"). Only these three exact origins work — a
non-default `WEB_PORT` or a new registered domain needs a new redirect URI added by whoever owns
the OAuth client first.

- **Local dev:** leave both blank to keep the identity-declaration fallback (zero setup), or fill
  real values into the gitignored `.env`/`web/.env.local` to exercise real Google login — see
  `docs/local-dev.md` "Signing in".
- **AWS POC deploy:** the two creds live in SSM Parameter Store
  (`/newsroom/GOOGLE_CLIENT_ID`, `/newsroom/GOOGLE_CLIENT_SECRET`, populated
  out-of-band, not Terraform-managed) and are pre-materialized into the `web` container's
  environment by `user-data` at boot — the same treatment as `NEXTAUTH_SECRET`, for the same
  Edge-runtime reason. See `infra/aws-poc/README.md` "Why web doesn't use SECRETS_BACKEND=aws".

## Not in this ticket

- **The durable Mongo user record** and attribution edges (domain model §1.17, D3): sessions are
  JWT-backed; persisting/reconciling the user record is downstream.
- **External (non-employee) interviewees** and the scoped expiring magic-link they'd need are
  deferred (design.md §9) — Google sign-in restricted to `AUTH_ALLOWED_EMAIL_DOMAIN` doesn't cover
  that use case at all.
