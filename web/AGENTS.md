# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## Auth (Google OAuth restricted to a domain, with a local-dev fallback)

- **Two mutually-exclusive providers, picked automatically** (full model: [`../docs/auth.md`](../docs/auth.md)).
  [`auth.ts`](auth.ts) registers the Google provider whenever `GOOGLE_CLIENT_ID`/
  `GOOGLE_CLIENT_SECRET` are both configured (checked via [`lib/google-auth.ts`](lib/google-auth.ts)
  `getGoogleAuthConfig()`, resolved through the secrets shim) — its `signIn` callback rejects
  anything but a verified `email_verified` account whose domain matches
  `AUTH_ALLOWED_EMAIL_DOMAIN` (default `example.com`; `hd=` is only a UI hint, never the real gate).
  **This is the app's own boundary — it is separate from and downstream of Google's own gate.**
  The Google Cloud OAuth client is Internal user-type, so Google's consent screen already blocks
  any non-org account before our code is ever reached; that means an in-domain sign-in succeeding
  in the real product proves Google's org gate works, but says nothing about whether our own
  `signIn` callback's domain check would reject a same-org-but-wrong-domain account, since that
  scenario can't currently occur live. `auth.test.ts`'s "realistic Google profile shapes" describe
  block drives the real callback (extracted from the real, unmocked config) against fixtures typed
  from the pinned `next-auth/providers/google` `GoogleProfile` — grounded in `@auth/core`'s own
  OAuth callback source, which hands `signIn` the decoded ID-token JWT claims verbatim (never a
  legacy tokeninfo-string response), so `email_verified` is guaranteed a real JSON boolean on this
  code path. That suite is the actual verification of our own gate until either the OAuth client
  is ever made External or a genuinely different-domain in-org account becomes available to test
  against live — don't treat a successful real sign-in alone as proof of the domain check.
  Otherwise it registers the original no-password identity-declaration `Credentials` provider
  (`authorize()` calls the pure, tested [`lib/identity.ts`](lib/identity.ts) `parseIdentity()`,
  which accepts any well-formed email). **The two are never both registered** — that's what makes
  the declare-any-email path unreachable once Google creds are set, not a separate check.
  `app/signin/page.tsx` mirrors the same `getGoogleAuthConfig()` check to render either a "Sign in
  with Google" button or the identity form.
- Read the signed-in user via [`lib/session.ts`](lib/session.ts) — `getCurrentUser()` / `requireUser()`
  return the typed `AppUser` (`{email,name,image}`; `image` is populated from Google's avatar under
  Google sign-in, always `null` under identity-declaration). Do NOT add per-role gates:
  authorization is **flat** (roles are attribution-only — design.md §2, domain model §1.17).
- [`middleware.ts`](middleware.ts) gates all routes except `/signin`, `/api/auth/*`, `/api/health`
  (keep `/api/health` public — the container healthcheck hits it), and static assets. Identical
  behavior in Docker and `npm run dev` — no dev-only bypass flag exists.
- `NEXTAUTH_SECRET` is optional: `auth.ts` falls back to a fixed POC value when unset (there is
  nothing real to protect — sign-in is a self-declared identity, not a credential), so the stack
  boots with zero auth configuration. **The fallback must treat an empty string as unset, not
  just `undefined`** — `docker-compose.yml`'s `${NEXTAUTH_SECRET:-}` always defines the container
  env var (empty string when the host var is unset), and Auth.js throws `MissingSecret` on
  `secret: ""`. The resolution rule lives in the pure, tested
  [`lib/auth-secret.ts`](lib/auth-secret.ts) `resolveAuthSecret()` for exactly this reason — don't
  inline a `??` chain over `process.env` in `auth.ts` again.
- `auth.ts` feeds `resolveAuthSecret` values obtained via `getSecret("NEXTAUTH_SECRET"/
  "AUTH_SECRET", ...)` (`lib/secrets/factory.ts`) rather than raw `process.env` reads — the
  provider-agnostic secrets shim, `SECRETS_BACKEND=env|aws|azure`, mirrored in
  `agents/app/secrets/` (Python) under the same config env var names. This only works because
  `NextAuth()` here is called with its **async-function config form**
  (`NextAuth(async () => ({...}))`), which `initAuth` awaits on every middleware request / RSC
  session read / route handler — the plain-object config form can't await anything. **Sharp
  edge:** `middleware.ts` bundles `auth.ts` for the Edge runtime by default, and `@aws-sdk/
  client-ssm`/`@azure/identity` are Node-only SDKs; `SECRETS_BACKEND=env` is edge-safe (a plain
  `process.env` read via `EnvSecretsProvider`), but `aws`/`azure` are not verified to work from
  edge-bundled middleware. A deployment that needs a cloud-managed `NEXTAUTH_SECRET` should run
  `middleware.ts` on the Node.js runtime (`export const runtime = "nodejs"`, stable Next 15.2+) or
  pre-materialize the value into `process.env.NEXTAUTH_SECRET` at container boot.

## Shared UI kit

- **`components/brain/brain-unavailable-banner.tsx`'s `BrainUnavailableBanner` is the ONE
  "Brain unavailable" message every brain-dependent surface shows** (`cmw-boss-facing-presentation`,
  2026-09-01 — the scout report's CRITICAL: the Git brain being down used to cascade into isolated,
  root-cause-free copy: "no voices available" on the kickoff + Radar + new-piece voice selects,
  "no personas available" on the kickoff persona picker, a bare 404 on `/interviews/[id]`). The
  banner carries the voice-kit screen's canonical phrasing ("the agents service or the Git brain
  may be unavailable") plus a link to the brain setup docs (`BRAIN_SETUP_DOCS_HREF`), and takes a
  `subject` prop ("The voice list", "This interview", …) without forking the root-cause sentence.
  New brain-dependent empty states must render this banner, never their own copy. Same ticket's
  HIGH: `components/dashboard/seeded-data-badge.tsx`'s `SeededDataBadge` is the one "seeded data"
  badge (dashboard / Spikes & Vault / Sources / piece-detail header — the last one driven by the
  agents `PieceDetailResponse.seeded` flag), and when seeded it doubles as the "how do I make
  this real?" link to `/how-it-works` (`app/how-it-works/page.tsx`), the page that names what
  turns the placeholder experience real (brain clone, Mongo, LLM creds, Google grant).

- **`components/ui/alert.tsx`'s `Alert` is the one error/warning/success/info banner every
  screen should use** (cmw-first-run-ux-batch item 1, 2026-08-10). Before this, ~16 call sites
  across `app/signin/`, `components/{spikes,interview,review-round,piece-detail,finalize,
  sources}/*` hand-rolled their own `<p role="alert" ...>`/`<div role="alert" ...>`, several with
  no border/background treatment at all — the site had no single answer to "what does an error
  look like." `Alert` is a `cva` component against semantic tokens only (`--destructive`/
  `--warning`/`--success`/`--info`, all already defined in `globals.css`, seeded from the brain's
  `voice/demo-dana/visual-identity.md`), same convention as `badge.tsx`/`button.tsx` — pick a
  variant, never hand-roll the border/bg/text classes again. `role` is derived from `variant`
  (`alert` for destructive/warning, `status` for success/info) so callers don't have to think
  about it.
- **`components/ui/expand-toggle.tsx`'s `ExpandToggle` is the one collapsed-row/expand-on-click
  affordance for list surfaces** (`cmw-list-density-and-source-forms`, 2026-08-10 — Hendo:
  dashboard queue and source registry rows were "very tall," which doesn't scale once real usage
  piles in dozens of rows; the dashboard/spikes queue is "the only list of these kinds of things
  anywhere," so it has to stay scannable, not just look fine with a handful). A plain button + a
  chevron icon + local `expanded` state in the caller — no new dependency, no accordion library.
  `components/dashboard/piece-card.tsx` and `components/sources/sources-table.tsx`'s per-row
  `SourceRow` both collapse to a line or two by default (title/name + badges + a compact meta
  strip) and hide secondary detail (piece: "why here" reasoning + the full failed-job explanation;
  source: config/credential/last-refreshed) behind this toggle — never behind a second, divergent
  pattern. Any new list surface should reuse this component rather than inventing another one.
- **Interactive-state legibility was measured, not eyeballed** (`cmw-interactive-state-affordance`,
  2026-08-10 — Hendo: the palette made it "subtle to detect what elements... are active,
  preferred, clickable, not clickable"). A real WCAG contrast pass over every token pair
  (default/hover/active/focus/disabled × light/dark) found several genuine AA failures, all fixed
  at the token level in `globals.css` — `--muted-foreground`, `--accent`, `--destructive`,
  `--success`, `--warning`, `--info` darkened/re-lightened per-mode (some as low as ~2:1 against
  their own Alert/Badge panel bg, none below 4.5:1 after); `--input` decoupled from `--border` and
  strengthened from ~1.2-1.7:1 to ≥3:1 (`--border` itself stays soft — it's card/divider chrome,
  not an interactive-control boundary, and was deliberately left alone). Full before/after table
  in that ticket's PR. Two things a token change alone couldn't fix, done as `cva`-level edits: (1)
  `Button`'s `secondary` variant gained `border border-input` (bg-secondary alone measured
  ~1.1-1.4:1 against the page — no visible edge at all; the fix is a border, not darkening
  `--secondary` itself, which would have muddied the deliberate primary-vs-secondary weight
  difference) — `outline` already had this; now `default`/`destructive`/`secondary` also carry
  `active:` states, since `:active` had no distinct treatment anywhere before. (2) **Disabled is a
  flat, uniform muted look on every variant** (`Button`'s `DISABLED` const, mirrored on `Input`) —
  `bg-muted`/`text-muted-foreground`/`cursor-not-allowed`, never a translucent fade of the
  variant's own color. A 50%-opacity destructive button was measured (and, in dark mode,
  screenshotted) reading as MORE visually prominent than several actually-active outline buttons —
  opacity alone doesn't communicate "inert," collapsing every variant to the same neutral look
  does. Any new `components/ui/` control with a disabled state should reuse this same collapse
  pattern rather than reaching for `disabled:opacity-*`.
- **`.piece-content-preview` (below, "Piece detail") is the one place none of the above may ever
  reach** — it hardcodes its own hex, referencing zero tokens, by design (frozen brand preview).
  Confirmed via DOM: appending a throwaway `.piece-content-preview` element and reading
  `getComputedStyle` returns the exact frozen `#fdf6ea`/`#3d2415` regardless of `.dark` or any
  token edit. Any future token change should re-run that same check before merging, the same way
  PR #88 verified it with computed styles rather than eyeballing a screenshot.
- **`components/ui/collapsible-section.tsx`'s `CollapsibleSection` generalizes `ExpandToggle` from
  a list row to a whole page section** (`cmw-piece-detail-collapsible`, 2026-08-10 — piece detail
  is the first caller: a page with many Cards, each serving a different task, needs most of them
  collapsed on landing so the ones that answer "what stage is this at, what do I do next" aren't
  buried). Same shared icon/click affordance as `ExpandToggle`, plus a `summary` (always-visible
  headline fact, collapsed or not — "aggregate 8.0 · round 2"), a `pinned` slot (rendered
  regardless of collapse state — for a control the user must not miss, e.g. "Resume interview"),
  and an `empty` flag that skips the toggle entirely when there's nothing to expand (PR #89's
  rule, generalized). Reuse for any future page that accumulates several Cards a user shouldn't
  have to scroll past.
- **`components/ui/modal.tsx`'s `Modal` is the one dialog primitive for long-form content across
  the app** (`cmw-piece-detail-collapsible` — Hendo asked for this explicitly, not scoped to one
  screen: "modals for long text should apply across the UI"). A thin, token-driven wrapper over
  `@radix-ui/react-dialog` (same org-sanctioned headless-primitive pattern as
  `dropdown-menu.tsx` — real focus-trap/Escape/scroll-lock, not hand-rolled). Piece detail's
  `DraftView` is the first caller (clamps a long draft body to a fixed height with a fade, then
  "Read full draft" opens the full text in this modal). **`cmw-modal-long-text-elsewhere` judged
  the three places PR #91 flagged next, applying the same clamp-then-modal pattern to two of
  them and deliberately leaving the third alone**: an interview turn's answer, in both
  `transcript-record.tsx` (piece-detail, read-only) and `transcript-panel.tsx` (the interactive
  interview surface — the read view clamps, the edit textarea never does, since editing needs the
  complete text regardless of display), share one clamp threshold in
  `lib/interviews/answer-length.ts` (`LONG_ANSWER_CHARS`, smaller than `DraftView`'s own since a
  turn renders in a compact list row, not as the page's own content); a council editor's fix/gap
  notes (`council-record.tsx`'s `EditorNotes`) were previously entirely invisible (counts only,
  never the actual text) and now clamp-then-modal too, since `editorial_fixes`/
  `information_gaps` are free-form Opus output with no length ceiling. A review round's routing
  log (`between-rounds-log.tsx`) was deliberately left alone: each line is templated around an
  80-char preview (`app/review/routing.py`'s `_ASK_PREVIEW`), capped by construction to roughly a
  sentence — never free-form long-form content, so a modal there would add an affordance nothing
  could ever need. Any other screen that needs to show a large text/HTML block without it
  dominating the page should reuse `Modal` the same way.

## App hub (post-login landing page)

- Route `/` (`app/page.tsx`) is the platform-level app hub — the post-login landing destination —
  not the Newsroom dashboard. The dashboard moved to `/newsroom`
  (`app/newsroom/page.tsx`, otherwise unchanged); every other Newsroom route
  (`/spikes`, `/sources`, `/voice-kit`, `/pieces/*`, `/interviews/*`) is unmoved. This needed no
  redirect-callback change: [`lib/auth-actions.ts`](lib/auth-actions.ts)'s sign-in action already
  defaults `redirectTo` to `/` when there's no deep-link `callbackUrl`, so moving the hub onto `/`
  is what makes login (and revisiting while signed in) land there.
- The hub's own frame is [`components/hub/hub-shell.tsx`](components/hub/hub-shell.tsx) —
  deliberately NOT `AppShell`: `AppShell`'s nav row is Newsroom's internal sections, which
  don't belong one level up on the app picker. It reuses the same token-driven header chrome plus
  the shared `ThemeToggle`/`UserMenu` controls so it still feels like one system.
- The app catalog is DATA, not layout: [`lib/hub/apps.ts`](lib/hub/apps.ts)'s `HUB_APPS` array
  (id/name/blurb/icon/href/enabled) is what
  [`components/hub/app-hub.tsx`](components/hub/app-hub.tsx) renders — a future second app is a
  one-line array addition, never a hub layout change. `enabled: false` is the seam for an app
  that's being built but not ready (renders a disabled, non-navigable card); the static "more apps
  coming" tile is separate and never represents a real app.
- `AppShell` gained a small `LayoutGrid` icon link back to `/` next to its brand lockup, since
  Newsroom is no longer the root — its own brand/nav links point at `/newsroom` now,
  not `/`. Keep any new top-level Newsroom "back to home" link pointed at `/newsroom`
  (see `components/interview/interview-surface-view.tsx` and
  `components/piece-detail/piece-detail-view.tsx` for the existing pattern), not `/`.

## Dashboard / operator desk — Inbox + Machine strip + Library (Concept A, approved 2026-08-31)

- The dashboard was redesigned from the five saved-filter tabs (Needs my action / My pieces /
  All in flight / Spikes / Sources) to THREE sections over the one shared queue
  (cmw-evolution-ux-audit report §6/§7, captain-approved Concept A):
  **Inbox** (only real human decisions, grouped by decision type), **Machine strip** (ambient,
  non-clickable visibility of pieces running a batch job), and **Library** (every piece across
  every stage — published/finalized included — filterable, nothing hidden, with honest
  in-flight/done/failed counts via `statusOf`). Killed with the tabs: the duplicate Spikes and
  Sources tabs (both already have their own pages), and "All in flight"'s lie of counting
  terminal pieces as in flight. The layout model lives in
  [`lib/dashboard/desk.ts`](lib/dashboard/desk.ts) as pure, unit-tested functions (`buildInbox`,
  `machineWorking`, `libraryPieces`, `librarySummary`); the old `TABS`/`applyTab` model is gone
  from [`lib/dashboard/filters.ts`](lib/dashboard/filters.ts) (only the D15 filter bar survives
  there, and it now filters the Library only — never the Inbox or the strip).
- **The Inbox consumes the expanded `needsMyAction` predicate (PR #140) unchanged** — attribution
  only, never a gate (§1.17) — and `decisionGroupFor` maps each predicate hit to its decision
  group (answer / enough-input / review-round / sign-off / lessons / recover / pick-spike, plus
  `resume` for the predicate's paused+owner branch, which fits none of the report's seven). TWO
  deliberate routing decisions, both documented in `desk.ts`: (1) the predicate's
  incorporating+owner branch ("wait for it, or check in") is NOT an actionable decision — it
  renders on the Machine strip instead, per the audit's "batch-running jobs are the strip, not the
  inbox" rule; (2) a piece that is both a predicate hit and batch-running is exactly one of the
  two, never both. **SYNC DISCIPLINE**: `decisionGroupFor` mirrors `needs-my-action.ts`'s branch
  structure 1:1 — if the predicate ever grows a branch, extend `desk.ts` in the SAME commit; the
  no-loss test in `desk.test.ts` (every predicate hit lands in exactly one of inbox ∪ strip) is
  the tripwire.
- **Mounting**: `/newsroom` (`app/newsroom/page.tsx`) is the redesigned Dashboard
  — Inbox + Machine strip + Library — as the Newsroom home screen. The PR #120 Operator
  Desk tracer is no longer the home (it leaked internal enum names into copy and only listed ~6
  recent pieces). Library is the complete all-pieces queue (every stage, published/finalized
  included), also reachable from the `Library` nav item (`/newsroom#library`). The tracer
  form still lives in `app/newsroom/operator-desk.tsx` (unmounted; content-workflow first-mile
  tests keep it) and `/content-projects` remains the project list.
- Work-state is read through the data layer via the BFF: `web/` calls the agents read-model at
  `GET /api/dashboard` (see [`lib/agents-client.ts`](lib/agents-client.ts) `fetchDashboard` and the
  [`app/api/dashboard/route.ts`](app/api/dashboard/route.ts) proxy). The `viewer` email only
  attributes SEED cards — it is **never** a permission filter. The agents side
  (`agents/app/dashboard.py`) serves real Mongo work-state when present, else built-in seed entities.
- [`components/dashboard/piece-card.tsx`](components/dashboard/piece-card.tsx) is the SHARED card the
  later piece-detail / spikes screens reuse. Stage-contextual actions and non-dashboard destinations
  are clean SEAMS routing to placeholder pages (`/pieces/[id]`, `/spikes/[id]`) — the repo's
  established `/interviews/[id]` seam convention.
- **Archiving a piece (`cmw-archive-piece`) hides it from this queue entirely server-side** —
  `agents/app/dashboard.py`'s `build_queue` excludes any `Piece.archived_at`-set piece before
  building `QueueItem`s at all, so `DashboardResponse.items` never contains one. **Found and
  rejected**: a client-side equivalent (an `archived: boolean` on `QueueItem`) was considered and
  rejected — the desk derives all three sections from the one `items` state through several
  scattered selectors (`lib/dashboard/desk.ts`, `needsMyAction`), and `statusOf`'s own docstring
  already flags that this file's catch-all-return style isn't compiler-exhaustive; a single
  server-side filter can't be forgotten at any one of those call sites the way a client-side check
  could. `needs-my-action.ts` needed no change either way — it only ever operates on whatever
  `items` the dashboard fetch already returned. The archive/unarchive REST pair
  (`agents/app/pieces.py`, `POST /api/pieces/{id}/{archive,unarchive}`) is deliberately separate
  from the generic `/api/pieces/[pieceId]/trigger` proxy — see root `AGENTS.md`'s dedicated bullet
  for why (not a `PieceStage`/`PieceTrigger` at all). The dashboard's own per-card "Archive" button
  (`piece-card.tsx`, piece items only) removes the item from `Dashboard`'s local `items` state on
  success rather than a full `/api/dashboard` refetch — since all three sections derive from that
  one state, the card leaves Inbox, strip, and Library at once.
- **`PieceCard` is collapsed by default; the "why here" reasoning and the full failed-job
  explanation are behind the shared `ExpandToggle`** (`cmw-list-density-and-source-forms`,
  2026-08-10 — see the Shared UI kit entry above). Title/badges + a compact voice/owner/assigned/
  council/gaps/cost strip stay always visible (still a line or two) so a row is identifiable at a
  glance without a click; the toggle itself only renders when there's actually something to
  expand (a "needs my action" card, or a failed job) — a card with neither renders no toggle at
  all. Archive + the primary action stay in the collapsed header, never behind the toggle.
- **`components/dashboard/pipeline-mini-rail.tsx`'s `PipelineMiniRail`** (`cmw-pipeline-depiction-
  design`, 2026-08-11) is a card-density echo of piece-detail's `Pipeline` rail, not a second
  design — three short segments for the same intake/loop/ship clusters
  (`lib/pieces/stage.ts`'s `STAGE_CLUSTER`) joined by connector lines, rendered next to `StageBadge`
  in the badge row. Hendo refined this live from an initial plain-dot-strip proposal ("dots
  connected by horizontal lines would help") — always aria-hidden (the badge text is the real
  accessible state) and renders nothing for a spike item or `paused` (off-rail, same as the main
  rail's own paused chip). The current segment reads accent instead of primary once
  `QueueItem.review_round > 1`, matching the main rail's loop-escalation language at a smaller
  size. **Found but out of scope**: `stage-badge.tsx`'s own `BATCH_STAGES` set duplicates
  `lib/pieces/stage.ts`'s `BATCH_STAGES`/`isBatchStage` rather than importing it (unlike
  `LOOP_STAGES`, fixed to import from there in this same pass) — a future stage added to the
  batch set could update one and silently miss the other; not touched here since it predates this
  ticket and isn't part of what it was asked to build.
- **Each desk section names what it actually holds before showing rows** — the Inbox renders a
  per-group heading + count + one-line decision description (`DECISION_GROUPS` in
  `lib/dashboard/desk.ts`), the strip says `idle` vs `N pieces in motion`, and the Library prints
  its honest `{total} pieces · {inFlight} in flight · {done} done · {failed} failed` summary.
  This carries forward Hendo's 2026-08-10 point that these are genuinely different semantic
  lists, not filtered views of one uniform table — now expressed as sections instead of tabs.

## Source registry (manage what the Oracle reads)

- Route `/sources` (mounted like the dashboard: `AppShell` + `requireUser()`) is the source
  registry (cmw-open-decisions §Item-6, cmw-ui-wireframes screen 7). Client state/orchestration
  lives in [`components/sources/source-registry.tsx`](components/sources/source-registry.tsx);
  the table, add/edit form, and clip-in form are separate components in the same directory so the
  screen stays self-contained (it was built to run in parallel with the piece-detail ticket).
- BFF routes proxy straight to the `agents/` data layer, same pattern as `/api/dashboard`:
  [`app/api/sources/route.ts`](app/api/sources/route.ts) (list/create),
  [`app/api/sources/[sourceId]/route.ts`](app/api/sources/[sourceId]/route.ts) (edit/retire), and
  [`app/api/connectors/{refresh,clip}/route.ts`](app/api/connectors/) proxying the existing
  connectors' on-demand refresh + credential-free LinkedIn/X clip-in entrypoints. **Never** enter
  or display a credential anywhere on this screen — the add/edit form sets `config` (what to
  read), never secrets (D14); real connector credentials only ever live in `agents/` server-side
  env.
- The agents side ([`../agents/app/sources.py`](../agents/app/sources.py)) is CRUD for the
  `Source` registry collection — the counterpart to `agents/app/connectors/` (which owns
  ingest/refresh, not registry management). `GET` follows the dashboard's store-vs-seed fallback;
  writes 503 until Mongo is configured. See that repo's `agents/AGENTS.md` sharp-edges note on why
  edits there re-validate the full merged document rather than doing a raw partial `$set`.
- `AgentsRequestError` in [`lib/agents-client.ts`](lib/agents-client.ts) carries the agents
  service's real HTTP status (400/404/503) through to the BFF response instead of collapsing
  every failure to a generic 502 — reuse it for any new BFF route that proxies agents writes.
- **A pasted Google Drive folder LINK (what a normal business user actually has, not the bare id
  buried inside it) used to silently fail** — `folder_ids` goes straight into the connector's
  Drive API query (`'<folder_id>' in parents`), so a full URL there matches nothing, and the old
  shared placeholder ("Folder IDs, channel names, or feed URLs") never said which one the field
  actually wanted (cmw-first-run-ux-batch item 3, reproduced live 2026-08-10). Fixed two ways:
  `lib/sources/format.ts`'s `extractDriveFolderId` parses `.../drive/folders/<id>`,
  `.../drive/u/0/folders/<id>`, and `.../open?id=<id>` out of a pasted link — `parseConfigList`
  runs it for `kind === "gdrive"` only, so either a link or a bare id saves as the same clean id;
  and `source-form.tsx`'s per-kind placeholder/hint now says a link works and that the folder must
  be shared with (or owned by) whichever Google account the org admin connected for Drive access
  (`agents/app/connectors/README.md`'s "incremental OAuth on the SSO identity") — reachability,
  not just syntax, is the actual gotcha a picker would also need to teach. A real modal folder
  picker (Drive's own file-picker widget) was considered and rejected for this batch as too large
  a scope addition — it would need a Google Picker API key/OAuth client wiring `web/` doesn't have
  yet; this inline fix ships the same outcome (no wrong-format silent failure) for near-zero cost.
- **Per-source refresh failures are warn-not-block by design (§5) but were completely
  invisible** — `agents/app/connectors/refresh.py`'s `SourceRefreshService` always reported a bad
  source's error in its response, but `source-registry.tsx`/`sources-table.tsx` only ever showed
  an aggregate "(N warned)" count with no way to see which source or why (cmw-first-run-ux-batch
  item 2, reproduced live against a real Drive source with no OAuth configured). Fixed by keeping
  the last refresh's per-source errors in `SourceRegistry` state (`refreshErrors: Record<sourceId,
  message>`) and having `SourcesTable` render an `Alert` row directly under the failed source —
  never a tooltip/hover-only affordance.
- **Fixed 2026-08-10 (`cmw-source-registry-ux`), three first-real-use gaps on this screen, live
  hardened by driving a real browser against an isolated instance:**
  (1) **A source added here could appear to vanish on navigating away and back** — not data loss;
  `refetchSources()`'s "Refresh sources now" always revealed it was there all along. Root cause,
  confirmed by reproducing it with the browser's own Back button (not just reasoning from the
  fetch directives): `app/sources/page.tsx`'s server render had no `force-dynamic`, AND — the part
  that actually bites — every mutation here goes through a plain client `fetch()` to a Route
  Handler, which gives Next.js's App Router **zero signal** to invalidate the client-side Router
  Cache for this route (that invalidation is automatic only for Server Actions). A `<Link>`
  soft-navigation away and back happened to refetch fresh in testing, but the browser Back button
  reliably served the STALE snapshot cached from the last time this route was entered — before the
  most recent mutation. Fixed with both halves: `page.tsx` now declares `export const dynamic =
  "force-dynamic"` (matching `/api/sources`'s own directive), and `source-registry.tsx` calls
  `router.refresh()` (`next/navigation`) after every mutation (create/edit/toggle/retire/refresh)
  to invalidate that cache for future back/forward visits — safe to call because this component's
  `sources` state is independent `useState`, so a background RSC re-render never clobbers what's
  already on screen. **Any other client component here that mutates via plain `fetch()` and
  expects a later browser-back to this route to be accurate needs the same `router.refresh()`
  call** — this is not sources-specific, it's how this app's whole BFF-proxy-plus-client-fetch
  pattern interacts with the Router Cache, and no other screen in this codebase does this yet.
  (2) **Saving gave no visible confirmation and didn't reset the form** — traced to
  `SourceForm`'s remount key being keyed only on `formTarget`; saving a *new* source keeps
  `formTarget` at `"new"` before and after, so the key never changes and React never remounts the
  form's internal field state, even though the row landed in the table correctly. (Editing an
  *existing* source already worked, since its target changes away from a real id back to `"new"`.)
  Fixed with a `formResetKey` counter folded into the key, bumped on every successful save/retire
  and by `resetForm`, so the form remounts blank even on a `"new"` → `"new"` save — plus a
  `variant="success"` `Alert` (reusing PR #79's shared banner) naming what was saved, and an
  attention-moving `scrollIntoView` on the alert+table wrapper. (3) **"+ Add source" looked
  inert** — it really was calling `setFormTarget("new")`, but that's a same-value no-op re-render
  whenever the form was already showing "add" (the common case, since "new" is the default
  target), and even when it *did* change something (leaving an edit), it never scrolled the
  off-screen form into view. Fixed by routing it through the same `resetForm` + an explicit
  `scrollIntoView` on the form section, so the button now visibly does something on every click.
- **Fixed 2026-08-10 (`cmw-list-density-and-source-forms`): the add-source form (`SourceForm`) and
  the clip-in form (`ClipInForm`) used to render side by side, always, unconditionally** — Hendo's
  third distinct complaint about this screen: "having both 'green' and 'clip in' input forms
  visible at once implies I might use either or both in the same movement regardless of how the
  two forms might be related or not." Fixed with an `activePanel: "source" | "clip"` switch in
  `SourceRegistry` — exactly one of the two ever renders, chosen by one of two clearly labeled
  toolbar buttons ("+ Add source" vs. "Clip in a LinkedIn/X post", styled like a segmented control
  so whichever is active reads solid). **Deliberately not merged into one kind-aware form**:
  registering a source (rare, admin-ish setup) and pasting a clip (the frequent day-to-day action)
  are genuinely different tasks that happen to share this screen; folding them into one form would
  just relocate the ambiguity into that form's own "kind" field. `SourceForm` still supports the
  `linkedin-x-clip` kind (the only way to create/rename that registry entry) but now says so
  explicitly next to the Kind field ("this registers the *channel*... to add an actual post, use
  'Clip in a LinkedIn/X post' instead") and the empty `ClipInForm`'s "no clip-in source yet" state
  gained a "Set up a clip-in source" button that jumps to the add-source panel with that kind
  preselected (`SourceForm`'s new `defaultKind` prop) — the one guided path between the two rather
  than expecting a person to find the right dropdown option unassisted. Same pass also fixed
  **`cmw-source-edit-button-scroll`**: the row-level Edit button only ever called `setFormTarget`
  with no `scrollIntoView`, unlike "+ Add source" (fixed in the entry above) — `handleEdit` now
  scrolls the form into view too, and also switches `activePanel` back to `"source"` in case the
  clip-in panel was showing. **Sharp edge hit while wiring this up**: `resetForm` gained an
  optional `kind?: SourceKind` param for the "set up a clip-in source" shortcut — passing the bare
  function reference as `SourceForm`'s `onCancel={resetForm}` (as the code already did) would have
  silently fed the button's click `SyntheticEvent` into that param as a truthy non-`SourceKind`
  value. Any callback with a newly-added optional parameter needs the same check before being
  handed to a DOM `onClick` as a bare reference — wrap it (`onClick={() => resetForm()}`) rather
  than assume extra JS call-args are harmless just because the old, param-less version was.

## Narrative → Radar → spike kickoff hand-off

- **The angle-intent field on `/narrative` (`components/narrative/narrative-oracle.tsx`) is a
  `TextArea`, not a single-line `TextInput`** (cmw-first-run-ux-batch item 4) — it carries the
  same kind of free-text intent as the adjacent narrative textarea and audience field, so it
  needs the same affordance to actually write in.
- **A spoken narrative's full `seed_text` used to be genuinely unrecoverable once the Radar page
  moved on** — the Narrative model always retained it server-side
  (`agents/app/narratives.py`'s `GET /api/narratives/{id}`, pre-existing), but nothing in `web/`
  ever called that route, and only the Oracle's distilled spike `headline` survives onto anything
  downstream (cmw-first-run-ux-batch item 6). Fixed with the missing BFF half
  (`fetchNarrative` in [`lib/agents-client.ts`](lib/agents-client.ts),
  `app/api/narratives/[narrativeId]/route.ts`) and
  [`components/spikes/narrative-reveal.tsx`](components/spikes/narrative-reveal.tsx) — a
  load-on-demand (never on mount) "View the narrative that produced this spike" toggle rendered
  on `spike-kickoff.tsx`'s step 1 whenever `spike.origin.kind === "narrative"`. Any other place
  that surfaces a narrative-originated spike/piece should reuse this component rather than
  re-deriving the fetch. **Done for piece-detail itself in `cmw-archive-piece`** — see root
  `AGENTS.md`'s dedicated bullet; the `origin.kind === "narrative" && origin.ref` check this
  bullet describes is now the shared pure `lib/spikes/origin.ts` `originNarrativeId()`, used here
  and there, rather than inlined twice.
- **The Voice chosen on the Radar form didn't carry onto the spike-kickoff page — it silently
  reset to `voices[0]`** (cmw-first-run-ux-batch item 7): `spike-kickoff.tsx`'s `voice` state
  always initialized from `voices[0] ?? ""` with no way to know what the Radar run actually used.
  Fixed by threading it through the URL rather than any new backend field (the Spike/Narrative
  models have no "which voice ran this" concept, and adding one would be a bigger change than the
  UX gap warranted): `SpikesTable`'s optional `voiceHint` prop appends `?voice=` onto its own
  "Pick & assign" link only when the caller has that context (`narrative-oracle.tsx` passes its
  own `voice` state; the plain `/spikes` Vault browser passes nothing, so its links are
  unchanged), and `app/spikes/[spikeId]/page.tsx` reads `searchParams.voice`, passing it to
  `SpikeKickoff` as `radarVoice` — used only if it's actually one of this piece's real `voices`,
  else the old `voices[0]` fallback stands.
- **Creating the piece (spike-kickoff step 2) gave no acknowledgement and no next-step
  invitation** — a muted one-line paragraph replaced the form with no visual signal anything had
  happened (cmw-first-run-ux-batch item 8). Fixed with a `variant="success"` `Alert` (green,
  checkmark) that names the created piece/voice, keeping the "Open piece" link as a secondary
  option rather than the only one. **Superseded in shape, not intent, by
  `cmw-piece-interviewing-without-interview` (2026-08-10)**: steps 3-4 (assign expert, interviewer
  set) now execute *before* pressing "Create piece," not after — `pick_spike` opens the Piece's
  first Interview atomically with the Piece itself, so there is no longer a "steps 3-5 below"
  gap for a fresh pick to invite the user into; the success `Alert`'s copy is now conditional on
  whether the Interview is already open (the normal case) vs. a legacy piece that still has none
  (the one remaining case the old manual "Generate link" flow serves — see root `AGENTS.md`'s
  dedicated bullet for the full story and why atomicity, not a bigger stage-model change, was the
  chosen fix).
- **Resolved 2026-08-10 (`cmw-narrative-first-entry-point`, Hendo's Option B):** the whole-shape
  objection `cmw-first-run-ux-batch` left open above ("that whole run the radar page as the way to
  kickstart a purely narrative-based piece feels incorrect") is fixed by giving "I already know
  what I want to write" its own front door, `app/pieces/new/` — separate from `/narrative`, which
  stays purely discovery (both its entry modes still land on the ranked-spikes table). The new
  page (reached from the dashboard's "Start a piece from my idea" button, not from `/narrative`)
  speaks a narrative and mints its Spike directly (`POST /api/spikes/from-narrative`, no Oracle
  ranking run), then routes straight to this same `/spikes/[spikeId]?voice=` kickoff page — it
  never skips the Spike itself, only the ranking: see root `AGENTS.md`'s spikes-REST-surface entry
  for why a spike-less piece would silently reintroduce the wrong-subject-draft bug PR #74 fixed.
  `components/new-piece/new-piece-from-idea.tsx` is the whole new screen; nothing in
  `narrative-oracle.tsx`/`spike-kickoff.tsx` changed.

## Voice kit (screen 11 — view/edit/rollback Git-backed voice packs + the lessons gate)

- Route `app/voice-kit/page.tsx` (server) picks a default voice (`demo-mira` if present, else the
  first voice the brain returns) and fetches that voice's pack, its `voice_guide` file history,
  and its pending lessons via the BFF client (`lib/agents-client.ts`), then hands off to the
  client component `components/voice-kit/voice-kit-screen.tsx`, which holds voice/file/pack/
  history/lessons as state so switching voice or file is a plain refetch-and-set, no page reload.
- Everything voice-kit-specific is self-contained under `lib/voice-kit/` (wire types, the pure
  `is-own-voice.ts` courtesy-note predicate + `diff.ts` line-diff, both unit-tested) and
  `components/voice-kit/` (selector, file list, editor pane, version history, lessons gate,
  courtesy note) — mirrors the source-registry ticket's isolation so it stays conflict-free with
  sibling `web/` screens built in parallel.
- **There is no Voice-to-User mapping in the domain model** (§1.17 attribution is piece/spike
  scoped, not voice-scoped) — `is-own-voice.ts`'s courtesy-note predicate is a best-effort match
  against the signed-in user's email local-part/name, and `demo-dana` never triggers it (D12:
  shared by everyone). This is deliberately a heuristic, non-blocking convenience note, never a
  gate — do not tighten it into an access check.
- The agents side had no REST for direct voice-pack edits before this ticket (only the lessons
  loop's `accept` path reached `content-lessons.md`, via `GitContentStore.commit_accepted_lesson`).
  This ticket added the generic voice-pack write/history/rollback methods on `GitBrain`
  (`agents/app/git/brain.py`) and the REST module `agents/app/voices.py` — see root `AGENTS.md`'s
  "voice kit" entry. `web/`'s BFF routes under `app/api/voices/` and `app/api/lessons/` proxy
  straight through, same pattern as `/api/sources`; `AgentsRequestError` passes through real
  agents-service statuses (404 unknown voice, 503 unconfigured, 422 bad file key) rather than a
  generic 502.
- The proposed-lessons gate reuses the existing lessons-loop REST (`/api/lessons/pending`,
  `/{id}/accept`, `/{id}/reject`) unchanged — this screen is a second UI consumer of that API,
  not a new backend path. Accept folds "edit" in: sending `rule_text` overrides the proposed rule
  in one call: the machine never self-commits (D12), only a human `accept` reaches Git.

## Piece detail (screen 2 — one piece's whole lifecycle)

- Route `app/pieces/[pieceId]/page.tsx` (server) fetches via `fetchPieceDetail` (BFF client,
  `lib/agents-client.ts`) against agents' `GET /api/pieces/{id}` (`agents/app/piece_detail.py`),
  then hands off to the client component `components/piece-detail/piece-detail-view.tsx`, which
  holds the piece as state so firing a trigger can refresh the whole screen from one refetch.
- Everything piece-detail-specific is self-contained under `lib/pieces/` (types, the pure
  `stage.ts` rail/cluster helpers, `actions.ts` stage→action mapping, `draft-html.ts` editorial-
  block split) and `components/piece-detail/` — it only *reads* `lib/dashboard/*` (the
  `PieceStage` type, `stageLabel`) and the shared `StageBadge`, never edits them, to stay
  conflict-free with sibling `web/` screens.
- **The unified `Pipeline` block** (`components/piece-detail/pipeline.tsx`,
  `cmw-pipeline-depiction-design`, 2026-08-11) is the page's single answer to "what stage is this
  at, what do I do next" — it replaced seven independent renderings of `Piece.stage` that used to
  exist across this app (the old `StageRail` Card, `NextActionCard` Card, the top-of-page failure
  banner, and the separate "Stage → primary action" `CollapsibleSection`, all deleted) with one
  card: the loop-aware rail, the stage-contextual CTA (folded in, no card boundary — same fetch/
  fire logic `NextActionCard` used to own), any open failure (folded in per decision B, no more
  separate banner), and the stage→action reference table as the ONE internal, still-collapsible
  sub-section (`ExpandToggle`-driven, matching PR #89's idiom) — collapsing that never hides the
  rail or the CTA, which is what "never gets a collapse control" actually protects. `pipelineTone`
  is the single function deciding *why* the current stage is current (`running` a batch job,
  `warning` a failure or `paused`, `accent` an interactive decision — review/finalized always,
  lessons only while something's unresolved, `default` otherwise) — both the current rail node's
  styling and the CTA's icon/ring read off the same value, so the two halves of the block can
  never disagree. The review/council/incorporating loop draws as a dashed bracket
  (`lib/pieces/stage.ts`'s `STAGE_CLUSTER`/`stagesInCluster`, the "intake"/"loop"/"ship" grouping
  a future stage addition should declare itself into rather than hand-positioning) with a round
  chip that's always shown — plain/muted at round 1 ("hasn't looped yet"), escalating to a solid
  accent pill with an explicit "· loop N×" count once round > 1 — so a piece on its third pass
  through review no longer renders pixel-identical to one on its first. Decision A (pending-
  lessons chip, equal visual weight next to Publish) is `lib/pieces/actions.ts`'s `NextAction.chip`
  field rendered as a solid `bg-accent`/`text-accent-foreground` pill sized like the button next to
  it (`EqualWeightChip`) — deliberately NOT the design artifact's translucent `bg-accent/18`
  badge, since that pairing was never contrast-verified for text the way
  `warning`/`success`/`info` were (cmw-interactive-state-affordance only fixed the
  solid-fill `accent`/`accent-foreground` pairing) — any future accent-tinted-panel-plus-text
  affordance should verify contrast first rather than assume this token generalizes. Decision D
  (archived dimming) is a single `opacity-60` on the block's outer `Card` — every control inside
  stays fully enabled, dimming is purely visual. **Incidental fix**: since `Pipeline` now renders
  above the two-column body grid instead of inside its right column, the narrow-viewport gap noted
  below (next action not visible without scrolling under `lg`) no longer reproduces — not
  re-verified with a dedicated ticket, just a side effect of where the block now lives.
- **The page's many Cards default collapsed except the ones the page exists to answer**
  (`cmw-piece-detail-collapsible`, 2026-08-10 — Hendo: "collapsable elements that start that way"
  + "modal pop-ups for long form content"; the page had accumulated a Card per ticket — draft,
  council, transcript, at-a-glance, two audit logs, a static reference table — fine one at a time,
  unscannable stacked). The rule applied: **the Pipeline block never gets a collapse control on
  its rail or its CTA** — the one hard requirement is that current stage + next action are obvious
  with nothing expanded, so neither can be accidentally hidden (its own internal stage→action
  reference sub-section is the one exception — see above). **At a glance stays open** — cheap to
  show fully and still bears on the next decision (open GAPs before finalizing). Published
  outputs now live in the post-publish tablist (see Derivatives bullet below), not as a second
  always-open right-column card. **Everything else** (Council record, Interview transcript, Activity log,
  Between-rounds log) **defaults collapsed** via
  `components/ui/collapsible-section.tsx`'s `CollapsibleSection` (see Shared UI kit above), each
  with a `summary` that keeps its headline fact scannable anyway (aggregate score, round/turn
  counts, latest activity). The transcript section's `pinned` slot keeps a "Resume interview"
  button visible even collapsed whenever an interview is genuinely open — the one actionable
  control on that Card. `DraftView` (`components/piece-detail/draft-view.tsx`) is **always
  expanded on landing when content exists** (`cmw-piece-draft-visibility`, 2026-08-31 — Hendo:
  users landing on in-progress pieces, especially the 11 brain-synced `drafts/` briefs, could
  not tell whether a draft existed because the card collapsed to a git SHA). Length still
  decides clamp-vs-full inside the body: a tweet/LinkedIn-post-sized draft (under
  `LONG_CONTENT_CHARS`, currently 2000 plain-text chars via `lib/pieces/draft-html.ts`'s
  `plainTextLength`) renders in full; a genuinely long draft clamps to a fixed height with a
  fade + a "Read full draft" button that opens the complete text in `components/ui/modal.tsx`'s
  `Modal` — that is the actual fix for "much longer and complex content is expected" without
  burying the rest of the page, and it no longer also hides the body behind a collapsed card.
  The collapsed summary still carries a `draftExcerpt` of the opening words so collapsing the
  section never leaves the user wondering whether content exists. Brain-synced pieces (no
  `draft.html`, content from `piece.md`) render through the same `draft_html` field — agents
  `piece_detail.draft_content_from_files` already falls back — and the badge reads "brain draft"
  rather than "master draft". The trailing editorial
  block (GAP/clearance notes) is that same `CollapsibleSection`'s `pinned` content — visible
  regardless of the draft body's collapse state, the same "must not miss" treatment PR #89 gave
  the piece failures banner, since it's the open-item list a piece owner must see before
  finalizing. **Sharp edge hit building this**: `CollapsibleSection`'s `CardHeader` override must
  include `flex-row` explicitly, not just `flex-wrap` — `Card`'s own `CardHeader` base class
  already carries `flex-col`, and omitting `flex-row` leaves it in column mode (title and summary
  each centered on their own line, not left/right on one row) even though `flex-wrap`/
  `items-center`/`justify-between` all appear to be "obviously" a row layout; `tailwind-merge`
  only dedupes the *same* utility group (`flex-row` vs `flex-col`), so a later class list that
  never repeats `flex-row` doesn't cancel an earlier one. Caught by actually loading the page in a
  browser, not by the unit tests (jsdom has no layout engine) — any future `cn()`-merged override
  of a component with its own base flex-direction needs the same explicit re-assertion, not just
  the properties that look new.
- **Archive/unarchive (`cmw-archive-piece`) is deliberately NOT in `lib/pieces/actions.ts`** —
  `components/piece-detail/archive-toggle.tsx` renders unconditionally in the header instead.
  Both `nextAction` (a total `switch (piece.stage)`) and `secondaryActions` in that file assume
  every action is stage-conditional; archiving must work from every stage (including `published`),
  so wedging it into either would mean either inventing a fake per-stage branch or breaking that
  file's exhaustiveness contract. See root `AGENTS.md`'s dedicated archive bullet for the backend
  half and the dashboard's own found-and-rejected filtering note above.
- **The piece's originating narrative is now visible here too** (`cmw-archive-piece`) — an
  optional `originNarrativeId` prop, resolved server-side in `page.tsx` (`piece.origin_spike_id →
  fetchSpike → lib/spikes/origin.ts`'s `originNarrativeId()`), renders the shared
  `components/spikes/narrative-reveal.tsx` right under the header's existing origin-spike line
  when non-null. `null` (no origin spike, a non-narrative origin, or an unreachable spike) renders
  nothing — never an error. See the "Narrative → Radar → spike kickoff hand-off" section above and
  root `AGENTS.md`'s bullet for the full story.
- The Pipeline rail renders the 9 non-`paused` states in `lib/pieces/stage.ts`'s `RAIL_STAGES` order
  (batch stages flagged); `paused` is a distinct off-rail chip (no rail position — `resume` always
  lands back on `interviewing` regardless of where it was paused from, so its prior position isn't
  recoverable from the wire data). `published` (agents' `agents/AGENTS.md` "publish" bullet) is the
  last rail step, terminal — `finalized`'s primary action is now `publish` (mints durable public
  outputs, terminal), with `capture-lessons` demoted to a secondary action alongside it since the
  two are independent, not sequenced. `components/piece-detail/published-outputs.tsx` renders the
  three resulting links (branded HTML/PDF in S3, the externally-shared Doc) once
  `piece.published_release > 0` — deliberately always on piece-detail itself (not gated to a
  stage-specific secondary link the way `OutputsList`/`finalize` is), since piece-detail is the one
  screen that stays reachable regardless of stage. `lib/dashboard/filters.ts`'s `statusOf` gained
  an explicit `published` → `"done"` branch (the actual fix for "a published piece must stop
  counting as in flight" — this function has a catch-all `"in-flight"` return, not a switch, so it
  is NOT compiler-forced and is easy to miss on a future stage addition);
  `lib/dashboard/needs-my-action.ts` needed no change — its `stage === "finalized"` branch-5 check
  already excludes `published` by construction, covered by a new regression test rather than a
  new code path.
- **Derivatives tab (post-publish mode, `cmw-repurposing-derivatives-ia`)** — publish is no
  longer the last beat in the IA. Once `stage === "published"` (or `published_release > 0`),
  `components/piece-detail/post-publish-workspace.tsx` renders a tablist (Outputs |
  Derivatives) between the Pipeline and the two-column body, defaulting to Derivatives so ship
  does not land on "here are three public links." Outputs is the pre-existing
  `published-outputs.tsx` panel. Derivatives (`derivatives-section.tsx`) lists existing natives
  plus the creatable catalog in `lib/pieces/derivatives.ts` — LinkedIn post/carousel, X thread,
  newsletter, blog, executive brief, talk track, email. **Child artifacts of the anchor by
  default** (`cmw-lesson-lineage-impl`): Commission records a child via
  `POST /api/pieces/{id}/derivatives` (not the unimplemented content-workflow
  `commission-derivative` command). Promote (`POST .../derivatives/{id}/promote`) mints a real
  Piece with its own owner/review/publish state. Native generation is still not built — the child
  is a lineage record. HTML/PDF/Doc stay render formats, not Pieces. Piece Studio
  (`app/content-projects/[projectId]/piece-studio.tsx`) reuses the same section when the project
  is `completed` or a family piece is `released`, listing only anchors + promoted derivatives as
  "pieces in this project." The later desk/inbox restack can lift this tablist into the artifact
  tabs (Draft / Council / Review / Outputs / Lessons / Derivatives) without rewriting either panel.
- The single stage-contextual primary action (`lib/pieces/actions.ts` `nextAction`) is usually a
  REAL orchestration trigger fired through `app/api/pieces/[pieceId]/trigger/route.ts` → agents'
  `orchestration/routes.py`, then refetches full detail (a batch chain can advance several stages
  in one call) — but `NextAction` also has a `kind: "link"` variant for `review` (see below) and an
  optional `chip` field (finalized-with-pending-lessons only, see the Pipeline bullet above) for
  informational emphasis that isn't itself a second control. Whenever an action needs configuration
  or a preview before it's safe to fire blind, it becomes a link to a dedicated screen instead of a
  bare button. This needs the piece to actually exist in
  Mongo — against the walking-skeleton seed (no Mongo) every trigger 503s, which the UI surfaces
  inline rather than treating as a bug.
- `agents/app/dashboard.py`'s seed pieces use **deterministic, slug-derived ids**
  (`seed-<slug>`), not `new_id()`: the seed has no Mongo behind it and is regenerated fresh per
  request, so a dashboard card's `/pieces/{id}` link must resolve against a *later, independent*
  `/api/pieces/{id}` call. Keep any new seed entity id-stable the same way if it's ever linked
  cross-request.
- `draft_html` is rendered via `dangerouslySetInnerHTML` (`components/piece-detail/draft-view.tsx`)
  — it is trusted, Git-committed content the internal pipeline writes to the brain clone
  (`HendoCode/content-machine-brain`, via `agents/app/git`), never third-party input.
- **The interview transcript (D16b) is reachable from piece-detail** via
  `components/piece-detail/transcript-record.tsx` — before this it was only reachable through the
  kickoff share link (`spike-kickoff.tsx`), unrecoverable once that moment passed. Fetches
  `fetchTranscriptTurns(pieceId)` (already-existing BFF route, `app/pieces/[pieceId]/page.tsx`
  passing `initialTurns` through) alongside `PieceDetail.interviews`. Deliberately, genuinely
  read-only — no edit/recap props exist on the component at all, unlike the interactive interview
  surface's `transcript-panel.tsx` — with a "Resume interview" link to `/interviews/{id}` shown
  only for an interview whose `status === "open"` (Hendo's call, 2026-08-08): a still-open
  interview stays resumable there, a `complete` one never should be. `interviews` renders as its
  own list rather than one summary, and `turns` as a separate shared block, so a later
  multi-round change (turns keyed to a specific interview) can nest under its own list item
  without restructuring this component — today's wire shape has one piece-scoped, unattributed
  turn list, not turns split per round. **When `interviews` is empty** (a piece stuck at
  `interviewing` with zero Interviews — see root `AGENTS.md`'s
  `cmw-piece-interviewing-without-interview` bullet), the optional `originSpikeId` prop (from
  `PieceDetail.origin_spike_id`) renders a link to `/spikes/{originSpikeId}` — that kickoff screen
  is the only place that can open the missing Interview; before this, the empty state was a dead
  end ("No interviews opened yet.") with nothing else on piece-detail able to reach one.
- The piece↔Doc link (domain model §1.14/§1.15) is `PieceDetail.review_round.doc_url` (already on
  the wire type, `lib/pieces/types.ts`); `components/piece-detail/review-doc-link.tsx` renders the
  header's "Open review Doc" button from it when `stage === "review"`, falling back to a subtle
  note when the field is null. Mirrored by the dedicated review-round screen below
  (`cmw-ui-wireframes/04-review-round.html`) so the two feel like one system.
- Piece-detail's "Finalize" secondary action (`lib/pieces/actions.ts` `secondaryActions`) is a
  **link** (`kind: "link"`) to `/pieces/[pieceId]/finalize`, not a blind trigger-fire. Format
  selection and the warn-not-block pre-finalize checks must always be seen before a render is
  fired; see the section below.
- The `lessons` stage's primary action is **conditional on `piece.lessons`**, the one exception to
  "each stage maps to one fixed action kind": `nextAction` returns a `kind: "propose-lessons"`
  action (rendered as `components/piece-detail/propose-lessons-form.tsx`) while
  `proposed.length === 0` (nothing to accept/edit/reject yet), and only then falls back to the
  pre-existing `finish-lessons` trigger. This closes what was a real UI hole (PR #14 shipped the
  lessons-loop backend at `POST /api/lessons/{piece_id}/propose`, but nothing in `web/` ever called
  it — a human could flip a piece into the `lessons` stage and then had no way to generate the
  first proposal). `POST /api/lessons/{piece_id}/propose` requires a real body
  (`published_content` — the diff source, since distribution/publishing is out of v1's scope so the
  machine has no other way to know what actually shipped), so — like review-round's mint panel and
  finalize's format picker — it gets its own form rather than the generic blind trigger fire.
  Its BFF route is `app/api/pieces/[pieceId]/lessons/propose/route.ts`, **not**
  `app/api/lessons/[lessonId]/propose/route.ts`: Next.js forbids two different dynamic-segment
  names (`lessonId` vs. `pieceId`) at the same route-tree level, and the existing accept/reject
  routes already claim `[lessonId]` under `app/api/lessons/`. Nest any future piece-scoped lessons
  route under `app/api/pieces/[pieceId]/lessons/` for the same reason.
- `PieceDetail.review_rounds` (plural, EVERY round, ascending — distinct from the singular
  `review_round` convenience field, which is just the latest) backs
  `components/piece-detail/between-rounds-log.tsx`: the between-rounds routing log
  (open-decisions Item 7), "what happened between rounds and where content went." Each round
  carries its own `routing_log: string[]` — the one-line-per-item audit trail
  `agents/app/review/routing.py` already produced but never surfaced until this ticket
  (`agents/app/schemas.py` `ReviewRoundOut.routing_log` + `piece_detail.py`). Always visible on
  piece-detail itself (a deliberate Hendo call, 2026-08-07) — not gated behind the review-round
  screen below, so the history stays in view after a piece moves past `review`.
- **Status facets, not one flattened status** (v1 launch wave "ui-state-facets", 2026-08-31): the
  header's single `StageBadge` was replaced by `components/piece-detail/status-facets.tsx` — six
  badge-buttons in lifecycle order (stage / execution / review / attention / lineage / learning),
  each opening its own detail drawer (`Modal`). Derivation is pure, in `lib/pieces/facets.ts`
  (`facetSummaries` + per-facet state helpers), over EXISTING `PieceDetail` fields only — no new
  wire fields: execution reads the activity log's "{type} job {status}" lines (`RUNNING_RE`) +
  `failures`, attention sums open GAPs + clearances + open interviews + failures, learning counts
  lessons by status, lineage reads revision/origin-spike/brain-synced. Keep any future "what state
  is this piece in" surface a facet on this strip rather than a new flattened badge.
- **Claim-level citation chips + the expandable sources drawer** (v1 launch wave
  "evidence-ui-scope", 2026-08-31): drafts annotate claims with footnote chips
  (`<sup class="fn"><a href="#srcN">N</a></sup>` — styled as pills by globals.css, an app-chrome
  overlay on the frozen preview, not part of the brand face). `DraftView` intercepts chip clicks
  via event delegation (only hrefs referencing a KNOWN parsed source; unknown anchors keep native
  behavior) and opens `components/piece-detail/sources-drawer.tsx` scrolled to + briefly
  highlighting the entry (`openSignal` seq counter makes repeat clicks re-fire). The drawer's full
  list — draft footnote sources then `sources.md` research citations grouped by the file's own
  headings — comes off `PieceDetail.evidence_sources`/`evidence_citations`, parsed read-time by
  `agents/app/evidence.py` from `draft.html` + `sources.md` (regex/`html.unescape` only, no new
  dependency; URL-less sources.md bullets are annotations, not sources, and stay out). A piece
  with no annotations shows no drawer — never an empty one.

## Review round (screen 04 — mint, assisted "reviews done" preview; D4/D11/open-decisions Item 7)

- Route `app/pieces/[pieceId]/review/page.tsx` mirrors the finalize page's fetch/auth pattern
  exactly, then hands off to `components/review-round/review-round-view.tsx`. Reachable ONLY from
  piece-detail's review-stage primary action (`nextAction`'s `kind: "link"` case, above) — never a
  blind "reviews done" button. This was a deliberate Hendo decision (2026-08-07, needs-decision →
  resolved) over two alternatives: an inline panel bolted onto piece-detail, or a bare
  fetch-preview-then-`confirm()` click handler — both rejected because the preview's whole point is
  showing sample comment/edit TEXT, which neither alternative surfaces well.
- `components/review-round/mint-panel.tsx` — internal/external radio (`lib/review-round/types.ts`
  `ShareMode`, re-exported from `lib/pieces/types.ts`), a reviewer-emails textarea parsed by the
  pure `lib/review-round/reviewer-emails.ts` `parseReviewerEmails` (empty → `null`, not `[]`), and
  the D11 warn-not-block banner shown as soon as external is selected (before minting) — the
  round's own returned `warnings` (open GAPs/clearances) render again after. Posts to
  `app/api/pieces/[pieceId]/review/mint/route.ts` → `agents-client.ts` `mintReviewRound` →
  `POST /api/pieces/{id}/review/mint` (`agents/app/review/routes.py`, pre-existing — this ticket
  only added the `web/` side).
- `components/review-round/reviews-done-panel.tsx` — the assisted ingest preview: "Confirm —
  reviews done" stays disabled until a preview has successfully loaded (`preview !== null`), so
  there is no code path to a blind fire. Preview reads `GET /api/pieces/{id}/review/preview`
  (also pre-existing); confirm fires the ordinary `reviews-done` trigger through the existing
  generic `/api/pieces/[pieceId]/trigger` route — no new trigger-firing endpoint was needed, only
  the preview gate in front of it.
- Both panels disable and explain themselves (not hide) outside the `review` stage, mirroring
  `FinalizePanel`'s convention — the flexibility principle (§5) warns, it doesn't hard-block
  navigating here, it just makes the illegal-stage case honest.

## Finalize / outputs (screen 10 — the render step; D13/open-decisions Item 5)

- Route `app/pieces/[pieceId]/finalize/page.tsx` (server) mirrors the piece-detail page's
  fetch/auth pattern exactly (`fetchPieceDetail` + `AppShell`), then hands off to the client
  component `components/finalize/finalize-view.tsx`, which holds the piece as state. Reachable
  only from piece-detail's "Finalize" link (above) — never a top-level `AppShell` nav item, since
  it's per-piece. The "Then" card no longer says distribution is out of v1 — after publish, the
  piece workspace opens a Derivatives tab (surface only; generation is not built). See the
  Derivatives bullet under Piece detail.
- Self-contained under `lib/finalize/` (format options + pure `toggleFormat`/`canFinalize`/
  `formatsForRequest` helpers in `formats.ts`, unchanged since introduction; the warn-not-block
  `preFinalizeChecks` in `checks.ts`) and `components/finalize/` (`destination-matrix.tsx`,
  `pre-finalize-checks.tsx`, `finalize-panel.tsx`), following the piece-detail/source-registry
  convention of keeping sibling `web/` screens conflict-free.
- **(cmw-drive-piece-folders) `destination-matrix.tsx` replaces the old `format-selection.tsx` +
  `outputs-list.tsx` pair** with one destination-by-format grid: rows are Branded HTML/PDF/Clean
  Google Doc, columns are Drive/S3. Drive's three checkboxes are the real chooser (unchanged
  mechanism — still `Job.formats` via `lib/finalize/formats.ts`); every cell also links straight to
  the artifact once one exists. There is no S3×Doc cell (a Doc is a Drive object); S3's two cells
  are status/links only — populated by the separate, later "Publish" action on piece-detail, never
  triggerable from this screen. `PieceDetail` gained `drive_folder_url`/`final_drive_html`/
  `final_drive_pdf`/`published_drive_html`/`published_drive_pdf` (all optional, so pre-existing
  test fixtures didn't need updating) for this — see `agents/AGENTS.md`'s Drive-folder entry for
  the backend half. `components/piece-detail/published-outputs.tsx` gained two more rows for the
  Drive-side published copies, parallel to its existing S3/Doc rows.
- The Finalize action posts through its own BFF route (`app/api/pieces/[pieceId]/finalize/
  route.ts` → `lib/agents-client.ts` `finalizePiece`) rather than the generic `.../trigger` route,
  because it is the one trigger whose body carries more than plain attribution: a selectable
  `formats` subset (`html`/`pdf`/`doc`). Selecting every format (or none, which the UI blocks with
  an inline hint rather than allowing) collapses to `formats: null` on the wire — the finalize
  step's own default.
- **Backend plumbing added alongside this screen** (not just UI): `Job.formats` existed on the
  model (`agents/app/models/job.py`) but was never threaded through before this ticket.
  `PieceMachine.finalize(..., formats=...)` → `JobRunner.enqueue(..., formats=...)` now carries it,
  and `POST /api/pieces/{id}/finalize` accepts an optional `{"formats": [...]}` JSON body
  (`agents/app/orchestration/routes.py`). `PieceDetailResponse` (`agents/app/schemas.py` +
  `piece_detail.py`) now also surfaces `final_doc`/`final_template_version`/`final_rendered_at` —
  existing `Piece` fields (§1.19) that the read-model simply hadn't exposed yet.
- **Superseded by cmw-drive-piece-folders**: this used to be the one place branded HTML/PDF were
  genuinely unreachable (no serving route for the disposable `drafts/<slug>/finalized/` files).
  That's now solved by uploading real copies into the piece's Drive folder instead of adding an
  agents download route — `destination-matrix.tsx`'s Drive cells link straight to them once
  `GOOGLE_SHARED_DRIVE_ID` is configured. The disposable local files are unchanged/still local-only
  when it isn't.
- Like every other orchestration trigger against the walking-skeleton seed, firing Finalize
  currently 501s (no step registered) or 503s (no Mongo) — surfaced inline via the same
  error-`Alert` pattern the Pipeline block's CTA uses, not a bug in this screen.

## Interview surface (screen 3 — the interviewee view)

- Route `app/interviews/[interviewId]/page.tsx` (server) is the SSO-gated expert deep link (D10,
  use case C) — the same `/interviews/[id]` seam the dashboard/piece-detail cards already route
  to. It fetches the Interview, the owning Piece (for title/voice/owner), and the sacred
  transcript turns via the BFF client, then hands off to the client component
  `components/interview/interview-surface-view.tsx`, which holds all of that as state so a turn
  updates the screen in place.
- **Focused interview mode** (2026-08-31, `cmw-interview-focused-mode`): this route mounts into
  `components/shell/interview-shell.tsx`, a slim sibling of `AppShell` with **no section nav**
  (Dashboard/Spikes/Sources/Voice-kits) — the interviewee is an external expert mid-question,
  usually on a phone, so the operator chrome is dropped entirely. The view itself is
  single-column and mobile-first: question (`ConversationPanel`) + `Composer` + sacred
  `TranscriptPanel`, plus the kept affordances (assignment banner, per-turn Edit + Recap,
  skip-without-pending-question, mark-complete, stop-for-the-day/where-are-we). The D6 doctrine
  prose that used to sit under the composer is hidden (placeholder + paragraph removed from
  `composer.tsx`) — classification still runs on every submission, the "Detected as:" chips
  remain as a quiet confirmation. The persona roster panel (`persona-panel.tsx`) was **removed
  from the focused surface** with the component file deleted: add/drop-interviewer is a
  coordinator move, deliberately out of an interviewee's view — fast-follow if it ever comes
  back, and note `lib/interviews/personas.ts`'s `personaRoster` (still tested) is the roster
  logic to reuse then. The route no longer fetches the interviewer roster
  (`fetchInterviewerPersonas`) for that reason; the `GET /api/personas/interviewers` endpoint
  still exists and is used by the piece-detail/kickoff surfaces.
- **The engine's `respond()` call requires a pending question** (`NoPendingQuestionError`
  otherwise) — so the composer's answer submit, persona add/drop, and session controls
  (stop-for-day/reorient) are all gated on `Boolean(interview.current_question)`. This is a real
  engine constraint, not a UI choice: add/drop-interviewer and stop-for-the-day are D6
  meta-commands, and meta-commands (other than skip/go-back, below) only route through the same
  classifier as an answer.
- **Skip/go-back are the one exception, and are NOT gated on a pending question** (Hendo,
  2026-08-10, `cmw-interview-skip-and-nudge` — "I should be able to skip to the next persona
  without having to force it to generate a question I'm not going to answer"). Unlike every other
  meta-command, roster navigation is pure index arithmetic with no classifier call
  (`InterviewEngine.advance_persona`, `agents/app/interview/engine.py`), so the composer's Skip
  button calls a dedicated `POST /api/interviews/{id}/advance-persona` (`direction: "skip" |
  "go-back"`) directly — never `respond()` with a synthetic answer — and is enabled whenever the
  interview is open and the roster isn't exhausted, independent of `canAct`/`current_question`.
  `Composer`'s `skipDisabled`/`skipPending` props are deliberately separate from its
  `disabled`/`pending` (answer-submit) props for this reason.
- **Per-persona wrap-up nudge (v1 heuristic)**: `lib/interviews/wrapup.ts`'s `shouldNudgeWrapUp` —
  a simple "has the active persona asked `WRAPUP_NUDGE_THRESHOLD` (5) questions" count, rendered
  as a non-blocking banner in `ConversationPanel` with its own inline Skip action. Deliberately
  isolated behind that one function so a future replacement (the model self-assessing against each
  persona's own "you are done when" criteria — see the interviewer persona docs in the Git brain)
  only touches `wrapup.ts`, not every place a persona's question count is rendered. Never disable
  "Ask next question" or the composer because of this nudge — it must stay a suggestion.
- Two small READ-ONLY endpoints were added to `agents/app/interview/routes.py` for this screen —
  `GET /api/personas/interviewers` (the full ~10-name roster, via the existing
  `GitBrain.list_personas`) and `GET /api/pieces/{id}/transcript/turns` (the transcript
  pre-parsed via the existing `parse_turns`) — both reuse engine internals rather than
  reimplementing parsing/roster logic in TypeScript. Live/manual testing against a real Interview
  writes real Git commits (one per answered turn) — see root `AGENTS.md`'s sharp-edges note on
  where those commits land and how to avoid polluting a real brain clone while testing.

## Testing conventions

- **`vi.fn()`'s `.mock.calls[n]` types as possibly-`undefined`** (vitest's mock typing has no way
  to know a call at that index actually happened) — destructuring it directly
  (`const [url, options] = fetchMock.mock.calls[0]`) fails `tsc --noEmit` with TS2488, and a
  fallback like `fetchMock.mock.calls[0] ?? []` silences the compiler but produces `undefined`
  members if the mock was never called, masking a real failure behind a `toBe`/property-access
  error instead of a clear one. Guard and narrow instead: `const call = fetchMock.mock.calls[0];
  if (!call) throw new Error(...); const [url, options] = call;` — see
  `components/sources/source-registry.test.tsx` / `clip-in-form.test.tsx`, or `auth.test.ts`'s
  `getConfigFn()` for the equivalent single-arg form. This repo has no CI, so `npm run typecheck`
  is never enforced pre-merge — run it yourself before pushing test changes that touch mocks.

## Interview transcript provenance (anchor-only after 2026-08-14 fix)

- Legacy `[RESEARCH-DERIVED] ` inline marker (pre-fix `append_turn`) is stripped at every read boundary (`parse_turns`, `read_transcript`, `PromptAssembler.transcript_block`) so `TranscriptTurn.answer` (and thus every UI display + every LLM prompt) is always clean interviewee text. Provenance lives ONLY in the `research:true` anchor boolean (structural). Mid-prose mentions of the string survive; no stored data rewritten. See root `AGENTS.md` Sharp edges and `agents/app/interview/transcript.py:strip_legacy_research_markers`. All web consumers (`transcript-panel.tsx`, `transcript-record.tsx`, `interview-surface-view.tsx` etc.) go through the parsed `TranscriptTurn` so never render the raw marker.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
