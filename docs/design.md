# Content Machine Webapp — Design & Requirements Specification (v1)

This is the authoritative design and requirements reference for **v1** of the
content-machine-webapp. It describes *what* the system does and *why* the key
decisions were made. It is deliberately not an implementation plan: there are no
tasks, sprints, or code-level designs here. Where a topic is deferred or not yet
decided, this document says so plainly rather than filling the gap.

---

## 1. Overview & goal

**North star.** Generate very on-brand, high-quality content easily, as a team,
with clean hand-offs between teammates and with expert knowledge pulled in through
short interviews (CTO, execs, subject-matter experts).

The content-machine-webapp is a **harness around an existing content-creation
agent**. That agent already exists, in its own repo,
[`HendoCode/content-machine-brain`](https://github.com/HendoCode/content-machine-brain)
(cloned read-write by `agents/` — see `BRAIN_ROOT`/`BRAIN_REPO_URL` in
`agents/app/config.py`), as a set of markdown files — voice kits, interviewer and
editor personas, and per-step prompts. Today those files are pasted into a Claude
Project and driven by hand. The webapp turns that manual,
single-operator workflow into a **shared, multi-person application**: it drives a
real LLM through those same files, tracks the state of work as a team, and provides
the hand-offs (author → coordinator → expert → reviewer) that a Claude Project
cannot.

**v1 gets a finished, on-brand piece all the way to a genuinely done, published state** — see
D13's "Published is a terminal state with durable public outputs" note. This reverses an earlier
v1 boundary (a piece used to stop at a final, reviewed artifact with no further state, "distribution
is out of scope"); Hendo's call was that a piece needs a way to be *done*, not just finished, or
every piece looks permanently in-flight on the dashboard. **Channel-specific distribution — picking
where a piece goes (LinkedIn, a blog, a newsletter) and the payoff of the audience/angle intent
captured along the way — is still explicitly out of scope for v1** (see §9): publishing mints
durable public *links* to the piece's outputs; it does not push the piece to any channel.

### Vocabulary

These terms carry the meanings the agent already gives them (see `PANEL.md` and
`PROJECT-INSTRUCTIONS.md` in
[`HendoCode/content-machine-brain`](https://github.com/HendoCode/content-machine-brain)).
A reader new to the project should read this section first.

- **Voice** — one identity the machine writes *for* (e.g. a specific person, or the
  shared team voice). Each voice is a markdown pack: a voice guide (the "DNA" the
  drafting step writes against), a style guide (who the person is and what they
  promote), and a growing `content-lessons.md`. Exactly one voice is active per piece;
  voices never mix within a piece.
- **Piece** — one unit of content being produced, from idea through final artifact.
  Each piece belongs to exactly one voice, has a status/stage, and moves through the
  pipeline. Several pieces can be in flight at once.
- **Spike** — a candidate content topic proposed by the Oracle. Spikes persist, carry
  a convergence score, and are attributed to whoever's run or narrative produced them.
- **Oracle** — the ranking step that turns raw source material into ranked candidate
  topics (spikes). It reads from the content lake over a lookback window.
- **Vault** — the shared pool of proposed-but-not-yet-picked spikes and parked ideas.
  Nothing is thrown away; unused ideas go to the Vault rather than being discarded.
- **Interviewer** — an extraction persona (there are roughly ten). Interviewers run
  *before* any draft exists to pull raw material out of an expert. They are
  voice-neutral by design — an interviewer sounds like itself, not like the voice
  being written for.
- **Editor / council** — judgment personas that run *after* a draft exists. The
  "council" is the selected set of editors for a piece; each scores the draft and
  splits its feedback into editorial fixes the machine can apply and information gaps
  that route back to a targeted interview. The council loops with revision until the
  draft clears the quality bar.
- **Lessons** — generalizable voice lessons captured by diffing a piece's final draft
  against its published/finished version, which flow back into that voice's kit so the
  next draft starts smarter.

### Relationship to the existing agent

The agent markdown is the **living brain**; the webapp is the harness around it. The
agent's own guidance frames it this way: the harness "can wire the loop," while "your
agent owns the orchestration" (`PANEL.md`, in the brain repo). The webapp does not
reimplement the agent's judgment or personas — it reads those packs, drives an LLM
through them, and commits edits and new lessons back. See §5, D1–D2.

---

## 2. Actors & roles

Authorization in v1 is **flat**: any signed-in employee can curate sources and act on
any piece. Roles below are **informational only** — they exist for attribution and to
power a "needs my action" dashboard filter, not to gate permissions.

- **Source-curator** — anyone. Maintains the source list.
- **Author / voice-contributor** — seeds narratives and owns pieces (ownership is
  attribution, not a lock).
- **Coordinator** — picks spikes, assigns experts, kicks off interviews.
- **Interviewee / expert** — an internal employee (CTO, exec, SME) who answers
  interview questions.

All actors are internal employees in v1. External interviewees are deferred (§9, D10).

---

## 3. The pipeline

The system is best understood as a **shared work queue of pieces**, each carrying a
**status/stage**. Any employee can see the queue, and the dashboard can filter it to
"what needs my action." Pieces advance through the stages below; several pieces sit at
different stages simultaneously.

```
  Sources ──▶ ORACLE ──▶ Spikes / Vault ──▶ (pick + assign) ──▶ INTERVIEW
                                                                    │
                                                                    ▼
                                        DRAFT ◀── (human: "enough input") ──┘
                                          │
                                          ▼
                           COUNCIL ──▶ GOOGLE-DOC REVIEW ──▶ (human: "reviews done")
                             ▲                                        │
                             └────────── REVISION LOOP ◀──────────────┘
                                          │
                                          ▼
                                    FINALIZE ──▶ LESSONS
```

Two kinds of work happen along this path:

- **Batch steps** (Oracle, draft, council, incorporate-edits) run as **background
  jobs** that flip a piece's status when they finish.
- **Interactive steps** (the interview, human review decisions) are turn-taking, with
  a human in the loop.

The webapp code sequences this as a deterministic **state machine** (D5); the *content*
of each step's prompt stays in the agent markdown. The exact set of per-piece stages
and their transitions is a spec-detail still to be pinned down (§10).

---

## 4. Use cases

### A. Source management
Maintain the Oracle's source list: add, retire, and edit sources, with a configurable
**lookback window** (default: a rolling 7 days). Source kinds:

- **Web / RSS** — scraped periodically (a legitimate programmatic pull).
- **LinkedIn / X** — no clean legitimate read path, so these are **manual clip-in**
  ("read-as-needed") sources: a human pastes/clips the material in.
- **Folders of call/webinar transcripts** — toggled on/off as sources.

Each source is classified along a key distinction: **scraped-periodically** (legit
programmatic pull) versus **read-as-needed** (clipped in by a human). Per-source
metadata is captured when it can't be inferred.

### B. Upfront narrative → Oracle → spikes
An author speaks a **narrative** in their own voice, carrying **audience/angle intent**
(this intent matters later, for distribution). On commit, the Oracle runs and returns
candidate topics (**spikes**). Spikes persist and are attributed to their creator and
origin.

### C. Spike selection + expert assignment + interview kickoff
A **coordinator** browses spikes, picks one (which stays attributed to its creator),
assigns an internal **expert**, and shares a link (via Slack or paste) that drops the
expert directly into **their assigned interview** in the app. There is **no
scheduling/calendar** in v1.

### D. Interview
The interviewee is presented with a menu of suggested **interviewer personas** (~10;
the agent can pre-select the fitting set for this piece) and a clear signal of who is
assigned and what the interview is about. Interviewers run **serially** — one asks
several questions, then the next takes over. The interviewee answers by **voice-to-text
(Whisper Flow)** or by typing, can **review and edit their own responses**, and
**marks the interview complete**, which flips the piece's status for the coordinator.

### E. Draft
A human **with authority over the piece** decides the accumulated input is sufficient
and triggers drafting. This is a deliberate button-press, not an automatic advance (see
D16a).

### F. Google-Doc review
The **council runs first** (a toggle can force a council pass). Then a button **mints a
Google Doc** from the current revision and returns a link. The human takes that link to
reviewers, who mark it up **inline and in comments**.

### G. Consume review → revise → loop → finalize
A human declares **"reviews done for this iteration."** The agent folds in all comments
and edits, produces a **new revision**, and re-runs the council; then it is back to
human review. This loops until the piece is final. The system records the **final
piece** and its **final Google-Doc link**.

### H. Content-lessons capture
A button assembles the **content lessons** learned while producing a piece, for that
author's voice — which may be their own voice, someone else's, or the team voice — and
those lessons flow back into that voice's kit.

### I. Voice-kit versioning
Voice kits (markdown packs) are **viewable, editable, rollback-able, and team-shared**.

### J. Final outputs / formats
Final outputs are usually **Google Doc + HTML + PDF**. The Google Doc is best for
editing but strips styling; Hendo branding only looks right as HTML/PDF. Formats are
**selectable at finalize**.

---

## 5. Architecture & key decisions

### Cross-cutting principle: favor flexibility over guardrails
The app **warns; it does not block**. It trusts users and corrects afterward rather
than being paternalistic. **Hard blocks are reserved for genuinely destructive or
irreversible actions only.** This principle governs the decisions below wherever they
touch what a user is or isn't allowed to do.

### D1. Agent-as-engine
The agent markdown stays the **living brain**. The webapp drives a real LLM through
those actual files. This is a harness, **not a reimplementation** of the agent's logic.

### D2. Git is the versioned source of truth for the brain
Voice kits, personas, and prompts live in Git, and **Git *is* the versioning** —
history, diff, and rollback come for free. The webapp reads the packs and commits
edits and new lessons back. A database would be the wrong store for the brain.

Git is a **deliberate additional store alongside MongoDB**, not the org datastore: the
**`agents/` service holds and commits to a Git repo** (for both the versioned brain and,
per D4, content revisions), and it coexists with Mongo, which is the datastore for
work-state and the content lake (§6). The two stores hold different kinds of thing and
do not substitute for each other.

### D3. A webapp-owned database is the system of record for work-state
A dedicated database holds everything that is *state*, not *brain*:

- piece statuses/stages,
- spikes and their ownership,
- the source registry,
- users / identity and continuity,
- assignments,
- expert-link routing,
- piece ↔ Google-Doc links.

**Notion is retired as a source of truth.** (An optional one-way, read-only Notion
mirror may come later — §9.)

### D4. The webapp/Git is the master of content; Google Docs is transient
Every draft **revision** is versioned in Git as agent-native files, giving a full,
diffable lineage. **Google Docs is a transient, per-review-round surface**: export the
current revision to a Doc → humans mark it up → on the human **"reviews done"**
trigger, pull edits and comments back → the agent produces the next revision. Canonical
content returns to Git between rounds. A Doc is authoritative **only during its open
window**, so **round boundaries must be explicit in the UI**.

### D5. The webapp drives the loop as a deterministic state machine
The deterministic orchestration state machine lives in the **Python / FastAPI
`agents/` service, not in TypeScript**. That service owns sequencing and turn-taking;
the **markdown** supplies each step's prompt content. The Next.js `web/` service is
**UI + BFF only** — it does not run the orchestration. Batch steps (Oracle, draft,
council, incorporate-edits) run as **background jobs that flip piece status**. (See
§6, Tech stack & constraints.)

### D6. Inside interactive steps, free-form input is classified into bounded operations
Within an interactive step, human input is free-form natural language that the LLM
**classifies into a bounded, defined set of operations**:

1. **An answer** (editable).
2. **"Research this"** → a research sidecar returns a sourced draft answer to review
   and accept.
3. **A meta-command** mapped to a real state operation — add/drop an interviewer,
   restart the step (with confirmation), stop-for-the-day (→ paused/resumable),
   go-back/skip/switch-piece (per the agent's reorient commands).
4. **A tangent** → parked to the **Vault**, never silently dropped.

The rule: **any invokable move must be a defined move** (so it can persist and resume);
a novel move is recorded as a note, never a silent no-op.

### D7. One on-demand Oracle, two entry points
The source registry and lookback window are **persisted settings**, but a scan runs
**when a human asks** — not on a schedule. (The scheduled/proactive scanner is deferred
to v2, §9.)

- **Entry B** — the narrative's audience/angle **biases ranking** (a soft bias, not a
  hard filter).
- **Entry A** — an open scan with **pure convergence ranking**.

The lookback window is a **per-run parameter**.

### D8. Green connectors only; no scrapers
- **Green connectors for v1:** Google Drive transcripts, Slack, web/RSS. (Gmail is
  opt-in/later.)
- **LinkedIn / X** have no clean legitimate read path → they are **manual clip/paste
  "read-as-needed" sources** (a bookmarklet may come later).
- The app **builds no scrapers and uses no gray-market scraping.** The Oracle does not
  auto-harvest LinkedIn/X.

### D9. A durable content lake with a hybrid index
A **content lake** is the single ingest target for **everything** — human pastes/clips,
dumps, output from externally-run scrapers, and Green-connector pulls. Everything is
**indexed on ingest** with a **hybrid index**:

- semantic embeddings,
- keyword / full-text,
- structured metadata (date/recency, source, author, tags).

The Oracle is an **on-demand query over this lake**, filtered by the window. Ingestion
is push / on-refresh. The research sidecar and drafting can also retrieve from the lake.
*(Infra note: a single MongoDB (Atlas) instance serves both the work-state store (D3)
and this content-lake hybrid index — Atlas Vector Search for embeddings, Atlas Search
for keyword/full-text, and native document fields for structured metadata. See §6.)*

### D10. Google Workspace SSO, company-domain-restricted
Sign-in is **Google Workspace SSO restricted to the company domain**, implemented with
**NextAuth using the Google provider**, domain-restricted to the company Workspace
(§6). Because all
interviewees are internal, the expert "link" is an **SSO-gated deep link** to the
assigned interview — **not** an anonymous or magic-link bypass. Authorization is flat:
any signed-in employee can curate sources and act on pieces. External interviewees are
deferred; supporting them would add a scoped, expiring magic-link (§9).

> **v1 POC interim:** ships with a simplified **identity-declaration login** instead (anyone
> signs in by declaring an email, no password/OAuth) so the boss + wider team can kick the tires
> without provisioning Google credentials. Real Google Workspace SSO per this decision is deferred
> until a company admin provisions it. Authorization stays flat either way. See
> [`docs/auth.md`](auth.md).

### D11. Google-Doc review round-trip
The review round-trip works as described in use cases F and G. **External sharing warns,
it does not block** (per the flexibility principle): an external share **auto-strips the
editorial/GAP block**, adds a **"DRAFT — not for external distribution"** banner, and
prominently warns about open clearances/GAPs — but it proceeds.

### D12. Voice-kit governance
**Any employee can edit any voice kit** — no approval workflow. Git is the visible,
attributable, reversible safety net. Editing a voice that isn't yours triggers a
**non-blocking courtesy note**. The Lessons Loop keeps one light human step: the
machine **proposes** lessons (by diffing final vs. published), a human
**accepts/edits/rejects in one click**, and accepted lessons commit to that voice's
`content-lessons.md`. **The machine never self-commits a brain change.**

### D13. Branding is a versioned render template applied at finalize
Content stays **plain/semantic** and is the master. The webapp owns a **versioned
branded template** and brand assets (sourced from the team voice's
`visual-identity.md`). At finalize, the webapp **injects content into the template**.
Outputs are on-demand and selectable per piece:

- **branded HTML**,
- **PDF** (rendered from that branded HTML, so the two match),
- **clean final Google Doc.**

Note the two distinct HTML notions: the agent's **semantic draft HTML is the master**;
the **branded distribution HTML rendered at `finalizing` is a disposable render** — regenerable
on demand from the semantic master, never a system of record. That disposability doctrine is
unchanged by the note below; it describes a *second*, deliberately durable render minted later, at
publish.

**Published is a terminal state with durable public outputs (v1 reversal, superseding the
"distribution is out of scope" line this section used to carry).** A piece's original v1 state
machine ended at `finalized` — a finished, reviewed artifact with no further state, since
distribution was deferred. Hendo reversed that call: "it seems that all docs are always going to be
in-flight" — a piece needs a way to be genuinely *done*, not just finished. So the settled machine
gained one more state, entered by an explicit **human button press, never automatic**:
`finalized → published`, terminal (no edge back out — a published link, once shared, can't be
un-shared, so the state shouldn't imply the action is reversible). It is independent of the
existing `lessons` gate (either can happen, in either order, or not at all) — lessons capture feeds
*future* pieces' voice packs; publishing ships *this* piece, an unrelated concern.

Unlike the disposable finalize render above, publishing mints outputs that ARE durable and public
by design: a fresh branded HTML + PDF render, uploaded to a plain, public-read S3 bucket under an
**immutable key per publish** (never overwritten in place, so an already-shared link survives a
later re-render, re-publish, template-version bump, or even Git history rewriting), plus a Google
Doc snapshot shared anyone-with-the-link. No signed URLs, no unguessable keys, no access-control
layer — generally public by policy, an explicit, deliberately simple v1 call that can be tightened
later (signed URLs, a CDN) without any app-level rework; what it *cannot* do is retroactively
un-share a link someone has already copied into Slack or a deck. See
`agents/app/publish/README.md` for the mechanism and `infra/aws-poc/publish_bucket.tf` for the
bucket. This is the one deliberate exception to the "content stays plain/semantic, renders are
disposable" doctrine above — everywhere else in D13, disposable still means disposable.

**Terminology note:** this "published" state is a *different* sense of the word than D12's lessons
loop, which diffs "the machine's final draft" against "what was actually published" — that phrase
predates this section and refers to a human-supplied, possibly hand-edited copy of whatever text
actually went out on some external channel (LinkedIn, a blog), pasted in by hand; it is unrelated to
whether the *piece* has ever reached this state machine's `published` stage. Don't conflate the two
when reading `agents/app/lessons/`.

### D14. Claude via one company key, server-side, model-tiered
The app calls **Claude through a single company Anthropic key, server-side**. Users
bring no keys; billing is centralized. Model choice is **tiered by step**:

- **Claude Opus 4.8** for draft, council, and lessons;
- **Claude Sonnet 5** for interview-turn classification and light steps.

Keys are held **server-side** (in the Next.js route handlers and the Python service),
never client-exposed. Per-piece / per-run **cost is shown in the UI as a courtesy** —
never blocking. There
are **no per-user quotas in v1**. Server-side hygiene: protect the key and enforce
**sane per-run ceilings** against runaway spend.

### D15. Spikes and the Vault are a shared, team-visible pool
Spikes are attributed to their **creator and origin** (run/narrative) and carry a
**convergence score** and **status** (proposed / picked / in-flight / vaulted). They are
**browsable and filterable** by creator, topic, date, and status. **Ownership is
attribution, not a lock** — anyone can pick or advance any spike.

### D16. Draft is human-triggered; the transcript is sacred
- **D16a — Draft is a human-in-the-loop button-press, not auto-advance.** An interview
  being marked complete is a **signal, not the trigger**: an interviewee is not the
  arbiter of input sufficiency, and multiple inputs may feed one piece. A human with
  authority over the piece judges "we have enough" and triggers drafting.
- **D16b — The interview transcript is the sacred source.** The interviewee's actual
  answers are the source, and the interviewee can **freely edit their own transcribed
  answers**. Any machine "here's what I heard" recap is a **confirmation view over their
  words**, never a separate authoritative artifact. This upholds the agent's
  "invent nothing" discipline and builds interviewee trust.

---

## 6. Tech stack & constraints

The following are **decided project norms** for how v1 is built (source: this project's
spec). They are constraints, not options.

### Topology
Two separate, containerized services:

- **`web/`** — Next.js (App Router), TypeScript in strict mode. Provides the **UI and
  the BFF** (backend-for-frontend) layer.
- **`agents/`** — Python **FastAPI** + uvicorn + Pydantic. Hosts the deterministic
  orchestration state machine (D5), the LLM calls, and the agent-facing work.

Next.js talks to the Python service over **REST / streaming HTTP**. Provider keys are
held **server-side** — in the Next.js route handlers or in the Python service — and are
**never client-exposed**. **Each service has its own Dockerfile.**

### Frontend (`web/`)
- **Next.js, App Router** (explicitly *not* Vite/SWC-vite).
- **Tailwind**, **shadcn/ui + Radix**, **lucide-react**.
- **class-variance-authority + tailwind-merge + clsx** for styling composition.
- Tests: **Vitest + @testing-library**.

### Backend / agents (`agents/`)
- **Python FastAPI.**
- Agent stack: **OpenAI**, **Anthropic**, **boto3 / AWS**. **LangGraph** is
  acceptable if a graph is genuinely needed.
- Tests: **pytest**.

### LLM
**Claude, tiered** (this refines D14): **Opus 4.8** for draft/council/lessons; **Sonnet
5** for interview-turn classification and light steps.

### Auth
**NextAuth with the Google provider, restricted to the company Workspace domain.** This
is *how* D10's Google SSO is implemented. **v1 POC interim:** NextAuth with a Credentials
provider backing a simple identity-declaration login (no Google setup required) — see D10's
POC note and [`docs/auth.md`](auth.md).

### Datastore
**MongoDB (Atlas).** A single MongoDB serves **both** the work-state store (D3) **and**
the content-lake hybrid index (D9), via **Atlas Vector Search** (embeddings) + **Atlas
Search** (keyword/full-text) + **native document metadata**. Git remains a deliberate
*additional* store for the versioned brain and content revisions (D2, D4); it coexists
with Mongo and is not the org datastore.

### Forbidden (org)
**Vite, Vue, Angular, Svelte, Gatsby, react-router, MUI, Chakra, Antd**, and **agent
orchestration written in TypeScript** (orchestration lives in the Python `agents/`
service — D5).

### Deployment & local dev
- **Local-first:** the **entire stack must run locally via Docker (`docker compose`)**
  for local debug, UAT, and development.
- **Production target:** a **private AWS VPC provisioned with Terraform.**
- **Parallel isolated instances (first-class v1 requirement):** the local Docker stack
  must be runnable as **parallel, isolated instances**, so multiple local agents / git
  worktrees can develop and test concurrently **without collisions** — e.g.
  parameterized ports, per-instance / ephemeral datastores, and distinct Compose project
  names. This constraint drives how the local environment is structured.

### Open build-time question
Whether the orchestration drives Claude via **an agent SDK** or via **direct Anthropic API calls** is not yet decided (see §10).

---

## 7. Data & storage model

The system deliberately splits storage by the *kind* of thing being stored.

| Concern | Store | Rationale |
| --- | --- | --- |
| **The brain** — voice kits, personas, prompts, and committed lessons | **Git** (held/committed by the `agents/` service) | Git *is* the versioning: history, diff, rollback. The webapp reads packs and commits edits + new lessons (D1, D2, D12). A deliberate additional store alongside Mongo. |
| **Work-state** — piece statuses/stages, spikes + ownership, source registry, users/identity, assignments, expert-link routing, piece ↔ Doc links | **MongoDB (Atlas)** | System of record for state; Notion retired (D3). Same Mongo instance also backs the content lake below. |
| **Content revisions** — every draft revision | **Git** (agent-native files, committed by the `agents/` service) | Full, diffable content lineage; the webapp/Git is the master of content (D4). Coexists with Mongo. |
| **The content lake** — all ingested raw material | **MongoDB (Atlas), hybrid index** | Single ingest target; Atlas Vector Search (embeddings) + Atlas Search (keyword/full-text) + native document metadata; queried on demand by the Oracle, research sidecar, and drafting (D9). |
| **Review surface** — one Google Doc per review round | **Google Docs (transient)** | Authoritative only during its open review window; content returns to Git between rounds (D4, D11). |

*Infra note (D9):* a **single MongoDB (Atlas) instance backs both the work-state store
and the content lake** — Atlas Vector Search, Atlas Search, and native document
metadata in one datastore. **Git is a separate, deliberate store** for the versioned
brain and content revisions (D2, D4), held and committed by the `agents/` service; it
coexists with Mongo and is not the org datastore.

---

## 8. Integrations

- **NextAuth + Google provider** — sign-in via Google Workspace SSO, restricted to the
  company domain (D10, §6).
- **Google Drive** — Green connector for call/webinar transcripts (D8).
- **Google Docs** — the per-review-round markup surface, minted from a revision and
  read back on "reviews done" (D4, D11); also a selectable final output format (D13, J).
- **Slack** — Green connector for source material (D8); also a channel for sharing the
  expert deep link (C).
- **Web / RSS** — Green connector, scraped periodically (D8).
- **Anthropic / Claude API** — one company key, called **server-side** (never
  client-exposed), model-tiered by step: Opus 4.8 for draft/council/lessons, Sonnet 5
  for classification and light steps (D14, §6).
- **Whisper Flow (or similar voice-to-text)** — how interviewees answer by voice (D).
- **LinkedIn / X** — **not** integrated as read connectors; manual clip/paste only, with
  no scrapers (D8).

---

## 9. Deferred / out of scope for v1

- **Channel-specific distribution** — picking a destination (LinkedIn, a blog, a newsletter) and
  the payoff of the audience/angle intent captured in the narrative. This is a later effort. **Not
  deferred:** the piece reaching a genuinely done, terminal `published` state with durable public
  *links* to its outputs — that shipped in v1 (D13's "Published is a terminal state" note) as a
  direct reversal of this bullet's original, broader scope.
- **Playwright / end-to-end tests** — deferred for v1; unit tests (Vitest in `web/`,
  pytest in `agents/`) cover v1.
- **The scheduled/proactive Oracle scanner** (D7) — v1's Oracle is on-demand only; the
  scheduled scanner is a v2 item.
- **External (non-employee) interviewees** (D10) — would add a scoped, expiring
  magic-link.
- **A LinkedIn/X clip bookmarklet** — the manual clip/paste path stays manual in v1.
- **A Notion read-only mirror** (D3) — optional, one-way, later.
- **Gmail as a source** (D8) — opt-in, later.

---

## 10. Open / to be detailed

These are spec-level details that are **not yet decided**. They are listed here, not
resolved.

- **Build-time:** whether the orchestration drives Claude via **an agent SDK** (org
  "primary") or via **direct Anthropic API calls** (§6).
- The exact per-piece state-machine **stages and transitions**.
- **Dashboard layout** and the specifics of the "needs my action" filter.
- **Error / failure handling** for background jobs.
- The **branded-template visual design**.
- **Connector setup / configuration** specifics.
- How **"reviews done"** is surfaced and assisted in the UI.
