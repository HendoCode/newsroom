# Newsroom webapp — agent notes

Durable project-intrinsic knowledge for the webapp repo. Prefer pointers to authoritative files over repeating what the code already shows.

## Orientation

- **Two services:** `web/` (Next.js App Router, UI + BFF) and `agents/` (FastAPI, orchestration + LLM work). They talk over REST (`web/lib/agents-client.ts` → `agents/app/main.py`).
- **Design constraints:** see `docs/design.md` §6 (forbidden list: no Vite/Vue/Angular/Svelte/Gatsby/react-router/MUI/Chakra/Antd; no agent orchestration in TypeScript).
- **Local dev:** `docker compose up` (base stack), or per-service dev in `docs/local-dev.md`.
- **Source-of-truth docs:** `docs/design.md`, `docs/local-dev.md`, `docs/deploy.md`.

## Build / test / release

| Surface | Command | Notes |
|---|---|---|
| Agents tests | `cd agents && pytest` | Runs on `mongomock-motor` + a disposable copy of `agents/tests/fixtures/brain/`. |
| Agents typecheck / lint | `cd agents && ruff check .` (and run `pyright`/`mypy` if configured) | Python 3.12. |
| Web dev | `cd web && npm run dev` | Next standalone dev server. |
| Web tests | `cd web && npm run test` | Vitest. |
| Web typecheck | `cd web && npm run typecheck` | Also enforced by `npm run build`. |
| Docker | `docker compose up` from repo root. | Caddy reverse proxy in `docker-compose.override.yml` / `docker-compose.prod.yml` overlays. |

The webapp is published as a single clean init commit into a fresh public repo; history is not carried forward. No pushes or PRs originate from this task worktree.

## Brain / content model

- The **brain** is a Git clone, not a subdirectory; `agents/app/git/` handles discover, clone, commit and push. Runtime wiring is in `agents/app/main.py` lifespan.
- The checked-in test fixture (`agents/tests/fixtures/brain/`) is the neutral demo suite: voices `demo-dana` and `demo-mira`, no real person names. Its `.fixture-source.json` and `agents/brain.lock` record the brain repo + commit it was snapshotted from — must stay in sync (enforced by `agents/tests/test_brain_fixture.py`).
- **Runtime brain is `HendoCode/masthead`.** The runtime clone target is the masthead repo (see `.gitignore`'s `/masthead/` for a clone that lands inside this repo's tree instead of alongside it), the same repo the test fixture is snapshotted from.

## Sharp edges (shortlist)

- **Local HTTPS is mandatory, not opt-in.** Compose override + Caddy edge. See `docs/local-dev.md` "Local HTTPS".
- **`AUTH_URL` must match the scheme+host+port a browser actually visits.** NextAuth replaces the origin with `AUTH_URL` unconditionally.
- **The `agents` image needs `git` and `ssh`.** `agents/Dockerfile` installs both.
- **Container healthchecks must hit `127.0.0.1`, not `localhost`.**
- **Mongo docs use string `_id` + naive-UTC timestamps.** `agents/app/models/common.py` explains why; never parse backend datetimes with bare `new Date()` on the client — use `web/lib/format/timestamp.ts`.
- **Provider keys / `AGENTS_URL` are server-side only.** Read them in `agents/app/config.py` or Next route handlers; never as `NEXT_PUBLIC_` vars.
- **Builds are staged for fast rebuilds; don't reach for `--no-cache`.** Both Dockerfiles use BuildKit cache mounts (apt, pip, npm, Playwright's Chromium, `.next/cache`), and Playwright has its own early layer (`agents/requirements-playwright.txt`). `--no-cache` bypasses the mounts too, so it re-downloads everything. Optional LAN mirrors (`NPM_REGISTRY`, `PIP_INDEX_URL`, `APT_MIRROR`, `PLAYWRIGHT_DOWNLOAD_MIRROR`) come from `.env` as **BuildKit secrets, not build args** (arg values are part of the layer cache key; secrets aren't), and default to the public sources. Any step that rewrites config for a mirror must restore it in the same `RUN`. `docker-compose.cache.yml` adds an optional shared registry layer cache under `BUILD_CACHE_PREFIX`; it's safe to keep in `COMPOSE_FILE` (an unset prefix degrades to no cache). Fonts are vendored in `web/app/fonts/` (`next/font/local`) so `next build` needs no Google Fonts access.
- **Finalize render output is disposable** (`drafts/<slug>/finalized/`, git-ignored). Only the final Doc link + provenance land in Mongo.

## Infra posture

- **No integration/test host currently exists.** Don't follow older notes or tickets that redeploy to a retired test host.
- `infra/aws-poc/` is a **sanitized historical artifact** with fake AWS account / Route53 zone placeholders. The live DNS posture is Cloudflare + OpenTofu on `hendocode.com`, maintained outside this repo. Do not attempt a real `tofu apply` from these files as written.
- `deploy/security-gate.sh` is a Trivy scan gate for the historical AWS POC; the ECR registry and account ID are placeholders.

## Maintaining this file

Keep it concise. Add only knowledge that is useful to almost every future agent session. Prefer pointers to authoritative files, commands, or docs over repeating implementation details.
