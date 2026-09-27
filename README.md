# Newsroom

A personal content-creation pipeline that takes a rough idea and drives it through a
deterministic, six-stage workflow — from an initial idea, through structured interviews,
a drafted article, an editor council, and on to branded, publishable output — with an
LLM doing the heavy lifting and a human holding the wheel at every gate.

## Origin

This was originally built as an internal tool for an AI company, and has since been
reworked into an open-sourced personal project. It was built solo, with the heavy lifting
done alongside an AI agent crew (Firstmate). The code here is the clean-room result of that
journey: a working system, not a demo, but honest about being a one-person project rather
than a corporate product.

## What it is

- **Six-stage content pipeline** — Oracle (idea ranking) → Interview (multi-turn expert
  extraction) → Draft (transcript → HTML) → Council & Revision (editor personas score and
  rewrite until the piece clears the bar) → Finalize/Publish (branded HTML, PDF, Google Doc)
  → Lessons (the diff between final and published becomes reusable voice rules).
- **A deterministic per-piece state machine** — every stage transition is an
  expected-source compare-and-set, with explicit human triggers (`enough_input`,
  `reviews_done`, `finalize`) and flag-not-rollback failure recovery. Nothing silently
  advances; nothing silently wedges.
- **A background-job engine** — atomic queued claims, heartbeats, stuck-job sweeps,
  bounded retries, and a per-run cost ceiling as the one hard stop.
- **Multi-provider LLM routing** — a swappable provider seam (Bedrock GLM, Anthropic,
  OpenAI) with per-step model tiering, prompt-cache-aware assembly, and cost/usage capture
  on every call.
- **A Git-backed "brain"** — voices, editor personas, engine prompts, and partner fact
  files live in their own repo and are cloned read-write by the backend; every voice-kit
  edit, accepted lesson, and piece revision is a real Git commit.

## Architecture

Two containerized services, wired over REST:

- **`web/`** — Next.js (App Router, TypeScript), Tailwind + shadcn/ui + Radix. The UI and
  the backend-for-frontend. Handles Google sign-in and talks to `agents/`; it never runs
  orchestration itself.
- **`agents/`** — Python FastAPI + uvicorn + Pydantic. Hosts the orchestration state
  machine, the job engine, the LLM provider layer, and the content lake. It talks to a
  MongoDB work-state store and the Git brain.

The brain (voices, personas, engine docs, drafts) lives in a separate repository and is
cloned/pulled/pushed by `agents/` over SSH — see
[`agents/app/git/README.md`](agents/app/git/README.md).

The authoritative design and constraints doc is [`docs/design.md`](docs/design.md).

## Getting started

The entire stack runs locally with Docker Compose:

```bash
docker compose up --build
# → web UI at https://localhost (local HTTPS via a bundled Caddy edge proxy)
```

Full instructions — running the stack, running the test suites, and standing up parallel
isolated instances — are in [`docs/local-dev.md`](docs/local-dev.md).

The test suites (no cloud setup required):

```bash
cd agents && pytest
cd web && npm run typecheck && npm test
```

## Repository layout

- `web/` — the Next.js UI + BFF
- `agents/` — the FastAPI orchestration service
- `docs/` — design, auth, and local-dev docs
- `infra/` — optional AWS deployment (OpenTofu) for the POC
- `deploy/` — the security-scan deploy gate and reverse-proxy config
