# Local development

How to run the Newsroom stack locally, run the test suites, and spin up
parallel isolated instances. The stack and constraints are defined in
[`design.md` §6](design.md).

## Topology

A Caddy TLS edge in front of three containerized services, wired over REST:

```
browser ──HTTPS──▶ edge (Caddy) ──▶ web/ (Next.js UI + BFF) ──REST──▶ agents/ (FastAPI) ──▶ mongo
              :443 (WEB_PORT)             :3000 (internal only)            :8000              :27017
```

- **`edge`** — Caddy, terminating HTTPS with a certificate from Caddy's own internal CA (`tls
  internal` — no domain, no public ACME). The **only** published route to `web`; see "Local
  HTTPS" below.
- **`web/`** — Next.js (App Router), TypeScript strict, Tailwind + shadcn/ui + Radix.
  UI and BFF only; it does **not** run orchestration. Provider keys stay server-side. Not
  published to the host directly — only reachable through `edge`.
- **`agents/`** — Python FastAPI + uvicorn + Pydantic. The seam for the deterministic
  orchestration state machine and the LLM module (docs/design.md D5, D14).
- **`mongo`** — local MongoDB with an **ephemeral tmpfs datastore** (clean slate each run).
  The persistent MongoDB (Atlas) data layer is a downstream ticket.

This is the v1 **walking skeleton**: `/health` endpoints and one stub the BFF calls. No
product features.

## Prerequisites

- Docker + Docker Compose v2 (`docker compose version`).
- For running the services outside Docker: Node 20+ and Python 3.12+.

## Run the whole stack

```bash
cp .env.example .env      # optional — every value has an in-file default
docker compose up --build
```

Then:

- Web UI + BFF → **https://localhost** (self-signed cert — see "Local HTTPS" below for what to
  expect and the optional one-time trust step)
- `web/` own health → https://localhost/api/health
- **`web/` → `agents/` health (proves the wiring)** → https://localhost/api/agents/health
- agents service directly (plain HTTP — it's never browser-facing) →
  http://localhost:8000/health and http://localhost:8000/api/status

The landing page shows a live "agents service reachable" indicator (browser → BFF → agents)
and a light/dark theme toggle.

Tear down (and drop the ephemeral datastore + the generated CA/cert):

```bash
docker compose down -v
```

## Git brain (voice kit, lessons, interview)

The Git-brain-backed features — voice kit, the lessons loop, and the interview engine — read
from a clone of [`HendoCode/content-machine-brain`](https://github.com/HendoCode/content-machine-brain)
that `docker-compose.yml` bind-mounts into the `agents` container at `/brain` (`agents/`'s own
`BRAIN_ROOT` is set to that fixed in-container path; see the orientation section of this repo's
`CLAUDE.md`/`AGENTS.md` for the full data-flow). **Before running `docker compose up`, clone the
brain repo as a sibling of this checkout:**

```bash
cd ..
git clone git@github.com:HendoCode/content-machine-brain.git
```

The default `BRAIN_HOST_PATH` (`../content-machine-brain`) already expects exactly that layout —
override it in your `.env` if your clone lives elsewhere (see `.env.example`). The mount is
read-write (not read-only): voice-kit edits and accepted lessons commit straight into this clone,
same as they would against a real developer-managed checkout, and auto-push if the clone has a
real `origin` (see this repo's `CLAUDE.md`/`AGENTS.md` "Sharp edges" — a real brain clone
auto-pushes on every commit) — keep a throwaway clone or one with no `origin` configured for
local experimentation you don't want landing upstream.

**If the brain isn't cloned**, `docker compose up` still boots cleanly (the `agents` container
stays healthy) — but `brain_root` resolves to a bind-mounted directory that either doesn't exist
or isn't a Git repo. `GET /api/brain/status` reports `"connected": false`, and every Git-brain
route 503s with a clear error (e.g. `GET /api/voices` → `{"detail":"voice kit unavailable
(brain_root not configured)"}`) instead of silently returning empty content. If you see that,
the fix is almost always the missing clone above.

## Signing in

The `web/` app is gated behind sign-in (see [`docs/auth.md`](auth.md) for the full design).
`web/auth.ts` picks the provider automatically: with no `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`
set, it falls back to a **dead-simple identity declaration** — no password, no OAuth. Visiting any
route redirects to `/signin`; entering an email (+ optional display name) signs you in as that
(pretend) identity, exactly the same way in Docker and under `npm run dev` — there is no separate
bypass to enable.

```bash
cd web
npm run dev        # http://localhost:3000/signin — enter any email, you're in (plain HTTP —
                   # this is a separate, lighter-weight iteration workflow that skips Docker/
                   # Caddy entirely; see "Local HTTPS" below for why the full stack doesn't).
```

```bash
docker compose up --build
# → https://localhost/signin — same identity login, no extra flags or override files needed.
```

**Enabling real Google login locally.** Filling in real values for `GOOGLE_CLIENT_ID` /
`GOOGLE_CLIENT_SECRET` (root `.env` for `docker compose up`, or `web/.env.local` for `npm run
dev`) switches `/signin` to Google-only, restricted to `AUTH_ALLOWED_EMAIL_DOMAIN` (default
`example.com`) — the identity-declaration form stops being reachable the moment both creds are set.
The registered redirect URI is `https://localhost/api/auth/callback/google` for the full
`docker compose up` stack at its default `WEB_PORT` (443), or
`http://localhost:3000/api/auth/callback/google` for the separate `npm run dev` workflow above.
Leaving either var blank keeps the identity-declaration fallback — no other setup needed.
**A non-default `WEB_PORT` has no registered redirect URI** — Google sign-in on an isolated
`scripts/instance.sh` instance will not complete (see below); the identity-declaration fallback
is what those instances are for.

## Parallel isolated instances

A first-class v1 requirement (docs/design.md §6): multiple worktrees/agents must run the
stack concurrently with no collisions. Every collision point is parameterized:

- `COMPOSE_PROJECT_NAME` → isolated container / network / image namespaces.
- `WEB_PORT` / `AGENTS_PORT` / `MONGO_PORT` → parameterized **host** ports (internal ports
  are fixed, so inter-service URLs never change). `WEB_PORT` is the HTTPS port `edge` publishes.
- `AUTH_URL` → must track `WEB_PORT` exactly (`https://localhost:$WEB_PORT`) so NextAuth builds
  OAuth redirect URLs against the origin the browser is actually using — see the `AUTH_URL`
  comments on `web` in `docker-compose.yml` and `docker-compose.override.yml` for why a mismatch
  here silently breaks sign-in rather than erroring loudly.
- `mongo` uses a per-instance **tmpfs** datastore (no shared named volume).

Use the launcher, which derives a non-colliding port triple from a base port, sets a distinct
project name, and exports the matching `AUTH_URL` for you:

```bash
# Instance "bob" on host ports 3200 (https web) / 3201 (agents) / 3202 (mongo), built & detached:
./scripts/instance.sh bob 3200 -- --build -d
# → https://localhost:3200/signin

# Inspect / tear down that specific instance:
./scripts/instance.sh bob 3200 -- ps
./scripts/instance.sh bob 3200 -- down -v
```

This runs happily **alongside** the default `docker compose up` (project `content-machine`
on https 443 / agents 8000 / mongo 27017). Verified: two instances up at once, each `web/`
reaching its own `agents/`, zero port/datastore/project-name collisions.

You can also drive compose directly with explicit env vars — remember `AUTH_URL` follows
`WEB_PORT` manually here, since only `scripts/instance.sh` does it for you:

```bash
COMPOSE_PROJECT_NAME=cmw-carol WEB_PORT=3300 AGENTS_PORT=3301 MONGO_PORT=3302 \
  AUTH_URL=https://localhost:3300 \
  docker compose up -d
```

**Google sign-in only works at the default `WEB_PORT` (443)** — that's the one origin already
registered on the OAuth client (docs/auth.md). An isolated instance's identity-declaration
fallback works regardless; its Google sign-in will not complete unless someone with access to
the OAuth client registers that instance's exact `https://localhost:<port>` redirect URI too.

## Run the test suites

**web/ (Vitest + Testing Library, strict TS, ESLint):**

```bash
cd web
npm install
npm run typecheck   # tsc --noEmit, strict
npm run lint        # next lint
npm run test        # vitest run
```

**agents/ (pytest):**

```bash
cd agents
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

## Brain pin (build/test reproducibility)

`agents/` reads the agent brain from a Git clone of `HendoCode/content-machine-brain` that
**runtime** tracks live (pulls the branch tip, pushes lessons/edits back). Building/testing
against a moving target isn't reproducible, so `agents/brain.lock` separately pins a known-good
brain commit for that purpose, honored via `BRAIN_REF` — unset for any normal dev/prod boot above,
set only when constructing/testing against the pin. The checked-in Git test fixture
(`agents/tests/fixtures/brain/`) is a snapshot of that same pinned commit. See
[`agents/app/git/README.md`](../agents/app/git/README.md) for the pin, the fixture-regeneration
script, and the bump workflow.

## Local HTTPS

`docker compose up` is **HTTPS-only** — `web` publishes no host port of its own; an `edge`
service (Caddy) is the sole entrypoint, serving `https://localhost` with a certificate from
Caddy's own internal CA (`tls internal` — no public ACME, no real domain needed). This isn't an
opt-in extra layered on top of a plain-HTTP default; it's the only supported local-dev path.

Mechanically, this lives in [`docker-compose.override.yml`](../docker-compose.override.yml),
not `docker-compose.yml` itself. Compose auto-loads an `override.yml` alongside the base file
whenever a command is run with **no explicit `-f`/`--file` flag** — exactly what a bare
`docker compose up` and `scripts/instance.sh` do. `docker-compose.yml` alone therefore still
describes the old plain-HTTP-on-`WEB_PORT` shape, deliberately: `docker-compose.prod.yml` (the
separate production edge-proxy overlay, `docs/deploy.md`) is documented to run as
`docker compose -f docker-compose.yml -f docker-compose.prod.yml`, an explicit `-f` invocation
that Compose never auto-extends with the override file — so that overlay's own, unrelated `edge`
service and topology are completely untouched by any of this, with no edits to it needed. (This
also means `docker compose -f docker-compose.yml up`, typed by hand, is a real if slightly
unusual way to get the old plain-HTTP behavior back — not a documented/supported path, just an
inherent property of how the override file is skipped once you name `-f` explicitly.)

**Why not keep a plain-HTTP opt-out as a supported, documented path.** An earlier version of
this setup published `web` in plain HTTP by default and offered HTTPS as a separate, opt-in
overlay. The two could drift: `AUTH_URL` (below) defaulted off the HTTP origin regardless of
which overlay was active, so turning on the HTTPS overlay for a real Google sign-in attempt
would have silently sent the wrong `redirect_uri` to Google — exactly the class of bug this
project has already lost an afternoon to once (see `AGENTS.md`/`CLAUDE.md` "Sharp edges"). Two
parallel paths meant two things to keep in sync and two places for that sync to quietly fail.
Collapsing to one default path removes the failure mode outright. The friction this trades away —
a self-signed-certificate warning on first visit — is small and one-time: clicking through it is
completely fine for a POC, and the trust step below is optional polish, not a requirement to use
the app at all.

Tear down (this also drops the generated CA/cert, requiring one re-trust on the next `up` if
you'd trusted it — see below):

```bash
docker compose down -v
```

**Trusting the certificate.** Caddy's internal CA is self-signed and not trusted by your OS/browser
by default, so the first visit shows a certificate warning — clicking through it is fine if you
just need *some* HTTPS, which is the expected default experience for this POC. For a clean
padlock instead, trust the CA once:

1. Bring the stack up (`docker compose up -d`), then pull the generated root CA cert out of its
   named volume:
   ```bash
   docker run --rm -v content-machine_caddy_dev_data:/data alpine \
     cat /data/caddy/pki/authorities/local/root.crt > /tmp/caddy-local-ca.crt
   ```
   (swap `content-machine` for `$COMPOSE_PROJECT_NAME` if you launched via `scripts/instance.sh`
   or a custom project name — the volume is named `<project>_caddy_dev_data`).
2. Trust it in your OS store:
   - **macOS:** `sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain /tmp/caddy-local-ca.crt`
   - **Linux:** `sudo cp /tmp/caddy-local-ca.crt /usr/local/share/ca-certificates/caddy-local-ca.crt && sudo update-ca-certificates`
   - Firefox keeps its own trust store separate from the OS on both platforms — import the same
     file under Settings → Privacy & Security → Certificates → View Certificates → Import.
3. Restart your browser. The CA is persisted in the `caddy_dev_data` volume, so this is a
   one-time step per machine — it survives `down`/`up` cycles as long as the volume isn't
   removed (`down -v` deletes it, and regenerates a new CA on the next `up`, requiring re-trust).

The Caddyfile behind `edge` is `deploy/Caddyfile.dev-tls` — separate from the production gate's
`deploy/Caddyfile` (`docs/deploy.md`); the two are unrelated and never loaded together.

## Production deployment

The above is the full **local** picture. Deploying a build behind the POC shared-password gate (a
reverse proxy in front of the whole app, on top of whichever sign-in provider `web/auth.ts`
resolves — Google in a real deployment, identity-declaration if no creds are configured) is a
separate compose overlay, not part of local dev: see [`docs/deploy.md`](deploy.md). The AWS POC
deploy (`infra/aws-poc/`) feeds `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` to the `web` container
from SSM the same way it does `NEXTAUTH_SECRET` — see that directory's README.

## Provider keys

Keys are **server-side only** and never exposed to the browser (docs/design.md §6, D14).
Supply them via a git-ignored `.env` (root, for compose) or the per-service `.env` files —
see `.env.example`, `web/.env.example`, `agents/.env.example`. The skeleton needs no real
keys to run; the placeholder pattern is in place for downstream tickets.

## Bedrock / AWS SSO (local dev only)

The default LLM backend is Bedrock (GLM-5 via `zai.glm-5` on Converse). For `docker compose up` (or `scripts/instance.sh`) to reach it:

1. Ensure you have an active AWS SSO session on the *host* for the profile you will use (`aws login` or `aws sso login --profile <name>`; the default profile is used unless `AWS_PROFILE` is set).
2. The compose override (`docker-compose.override.yml`) mounts `~/.aws:/root/.aws` (read-write —
   see the caveat below for why) into the `agents` container and passes `AWS_PROFILE`,
   `AWS_SDK_LOAD_CONFIG=1`, and `AWS_DEFAULT_REGION`.
3. Rebuild if you changed requirements (the `boto3[crt]` extra is required for the SSO credential provider chain inside the container): `./scripts/instance.sh <name> <port> -- --build -d`

**Token refresh caveat (read this before assuming "re-run `aws login`" fixes a credential
failure)**: the newer `aws login` flow's cached token (`~/.aws/login/cache/*.json` — not the
classic `~/.aws/sso/cache/*.json` token some older docs describe) is short-lived and, unlike
plain SSO, boto3's credential chain will try to refresh it **from inside the container**
mid-session, then write the refreshed token back to the same file on disk. If that mount is
ever `:ro`, the network refresh itself succeeds but the local write-back fails with `OSError:
[Errno 30] Read-only file system`, crashing the in-flight request as a raw 500 — and because the
refresh grant was already consumed server-side before the write failed, a few failed attempts in
a row can burn the underlying refresh token entirely, breaking `aws` CLI access on the **host**
too, not just in the container. This is why the mount above is read-write, not `:ro`: it lets the
container persist its own refreshed token back to the file the host also reads, which is the
actual fix (not a `docker compose restart agents` after re-running `aws login` — that caveat from
an earlier version of this doc does not resolve this failure, since the crash happens on write-back,
not on an already-known-expired token).

**Shared-host risk**: every local instance on a given host — including separate
`scripts/instance.sh` instances — mounts the *same* `~/.aws` source path by default. There is only
one cached refresh token per host/profile, so one instance's credential refresh (successful or
failed) can invalidate every other concurrently-running local instance's credentials, and the
host's own `aws` CLI session, all at once. If you hit AWS credential errors on the host after
running local dev, re-run `aws login` on the host to restore it.

No credentials are baked into images or committed files — only host passthrough. Production uses instance role (no change needed).

**`ANTHROPIC_API_KEY` is required for the interview "/research" sidecar even when `LLM_BACKEND=bedrock` is otherwise fully self-sufficient.** The research sidecar (`agents/app/interview/research.py`) deliberately resolves its own direct-Anthropic provider (a carve-out so the `web_search_20260209` server tool keeps working — GLM-5 on Bedrock has no web-search tool), independent of the app's main `llm_backend`. Leaving it blank doesn't crash anything — a `/research` request degrades to a clear "research unavailable" message rather than a raw error — but the feature itself needs a real key configured to actually work.

## LLM backends: OpenRouter (`LLM_BACKEND=openrouter`)

OpenRouter is a first-class inference backend, not an overlay trick. Selection is
`LLM_BACKEND` (root `agents/app/config.py`; env var `LLM_BACKEND`, documented in
`.env.example` and `agents/.env.example`):

- `bedrock` (default) — `BedrockGLMProvider`, ambient IAM, `zai.glm-5` on Converse (section above).
- `openrouter` — the OpenAI-compatible provider (`OpenAILLMProvider`) pointed at
  `https://openrouter.ai/api/v1`. Set `OPENAI_API_KEY` to an OpenRouter key. `OPENAI_BASE_URL`
  is optional and overrides the endpoint for both this backend and `openai`. The step-tier
  model is `OPENROUTER_DEFAULT_MODEL_ID` (default `z-ai/glm-5` — the same GLM-5 tier the
  bedrock backend uses, under OpenRouter's vendor/model slug; the tier map in
  `agents/app/llm/tiering.py` routes every step to it when this backend is selected, so no
  call site changes).
- `openai` — the same OpenAI-compatible provider against api.openai.com. The pre-existing path
  is unchanged: leaving `OPENAI_BASE_URL` unset lets the openai SDK read its own
  `OPENAI_BASE_URL` env var, so an existing `LLM_BACKEND=openai` + `OPENAI_BASE_URL=
  https://openrouter.ai/api/v1` deployment keeps working exactly as before (use
  `LLM_BACKEND=openrouter` for new setups).
- `anthropic` — direct Anthropic API.

`docker compose up` forwards `LLM_BACKEND`/`OPENAI_BASE_URL`/`OPENROUTER_DEFAULT_MODEL_ID` to
the agents container (root `docker-compose.yml`); `agents/.env` does the same for non-Docker
local runs. The interview `/research` sidecar stays on the direct Anthropic carve-out regardless
of backend (see above). Cost readouts price the OpenRouter slug at the GLM-5 rates
(`agents/app/llm/pricing.py`) — if you point `OPENROUTER_DEFAULT_MODEL_ID` at a different
model, add its rates there or the cost readout shows 0.0 for it.
