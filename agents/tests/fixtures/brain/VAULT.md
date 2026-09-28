# Vault

Spikes surfaced by the Oracle but not taken forward. Nothing is ever thrown away.
Each entry is preserved with its convergence scoring so it can be re-picked in a later
run — ideally once a nameable subject or a real metric can be attached.

`skills/oracle` proposes the ranked list, the author picks, and everything unpicked lands
here (`skills/vault-ingest` appends entries in this shape). `engine/1-oracle.md` is the
ranking contract; this file is its archive.

> **Demo data.** Every run, subject, quote, and figure below is fictional — invented to show
> the Vault's shape and how a spike carries its provenance into a piece. Names appear in the
> demo pieces under `drafts/` and nowhere in reality.

## Entry format
Each spike entry carries exactly these fields, so a later run can re-rank without re-reading
the original material:

```
### Spike #N — "<headline>"
<two-to-four-line statement of the idea and why it has tension>

- Source: <where the raw material came from, with date>
- Maps to: <nameable subject — account, team, system, person cleared to quote — or "none yet">
- Outcome/metric: <the before/after or number, or "none yet">
- Rank rationale: <one sentence: why it landed here in the list>
- Convergence note: <what it collapses into or pairs with, and what would raise it>
```

Taken-forward spikes keep their entry and gain a line naming the piece folder, so the
provenance chain runs spike → `drafts/<slug>/piece.md` → draft → council record.

---

## Run — 2026-09-14 · Seed thesis: "retry logic is where a settlement system actually lives"

Original raw material (author's words, fictional):
> "Everyone designs the happy path for freight settlement and then discovers the retry path
> is the real system. We spent four months on idempotency keys and one afternoon on the
> diagram everyone remembers."

Taken forward this run: **Spike #1 — idempotency keys are the whole job** →
`drafts/idempotency-is-the-whole-job/` (voice: demo-dana, stage: interviewing) and
**Spike #2 — rehearse the rollback** → `drafts/rehearse-the-rollback/` (voice: demo-dana,
stage: council).

Vaulted below: #3, #4, #5, #6.

### Spike #1 — "Idempotency keys are the whole job"  → TAKEN FORWARD
The design argument: on a settlement path, the retry path IS the system, and the idempotency key
is the only contract that makes it safe. Everything else — ordering, replay, partial failure — is
a consequence of getting the key right.

- Source: author seed thesis (2026-09-14)
- Maps to: Harborline Freight settlement team (fictional)
- Outcome/metric: duplicate settlements down from 214 in one incident to 0 across 6 weeks
- Rank rationale: strongest technical spine in the set, with a nameable system and a real
  before/after. Full convergence.
- Convergence note: absorbs #4 (batches are a queue) as its middle section and #5 (what a key
  costs in storage) as its retention-window section.
- Piece: `drafts/idempotency-is-the-whole-job/` (voice: demo-dana)

### Spike #2 — "Rehearse the rollback"  → TAKEN FORWARD
The practice angle: a monthly drill that rehearsed the rollback path until the real one took
eleven minutes. The mechanism is expand-contract migrations plus a written runbook; the story is
that the drill felt pointless for the first two months.

- Source: author seed thesis (2026-09-14)
- Maps to: Harborline Freight platform team (fictional)
- Outcome/metric: drill 45 min/month; one real rollback in 14 months, 11 minutes, no data loss
- Rank rationale: outcome-bearing and mechanically concrete, but narrower than #1 — it is one
  practice, not a system.
- Convergence note: pairs with #1 as the deployment-side complement; the people angle split off
  to #6, which belongs to the narrative voice.
- Piece: `drafts/rehearse-the-rollback/` (voice: demo-dana)

### Spike #3 — "The duplicate-payment week nobody reported"
The incident where a retry storm double-paid 214 carriers, and the interesting part is that
the detection came from a bookkeeper in a different office, not from an alert.

- Source: author seed thesis (2026-09-14) + an internal incident note (fictional)
- Maps to: Harborline Freight settlement team (fictional)
- Outcome/metric: 214 duplicate payments, ~9 hours to detect, 6 days to reconcile
- Rank rationale: strongest story in the set, but it is a failure narrative about a client and
  needs explicit clearance before it can be told at all.
- Convergence note: pairs with #1 as its proof. Rises to the top the day clearance lands and
  a detection-latency number replaces "nobody noticed for a while."

### Spike #4 — "Settlement batches are a queue wearing a cron job's clothes"
The architecture argument: the nightly batch is a queue with a scheduler bolted on, and
every property the team wants (replay, ordering, partial failure) is a queue property they
are reimplementing badly.

- Source: author seed thesis (2026-09-14)
- Maps to: none yet
- Outcome/metric: none yet
- Rank rationale: durable and technically meaty, but it is an argument without a scene —
  needs one concrete batch that broke.
- Convergence note: becomes the middle section of #1 if the author supplies a real batch
  failure; otherwise it stands alone as an opinion piece for the durability-reader path.

### Spike #5 — "What an idempotency key costs you in storage"
The unglamorous follow-up: key retention windows, the size of the dedupe table at scale, and
why the window is a business decision about refunds, not an engineering preference.

- Source: author seed thesis (2026-09-14)
- Maps to: Harborline Freight (fictional)
- Outcome/metric: none yet — needs the retention window and row count
- Rank rationale: useful and specific, but narrow; reads as an appendix until the refund-policy
  angle is made explicit.
- Convergence note: strongest as a section inside #1, weakest as its own piece.

### Spike #6 — "The on-call rotation that made rollback rehearsals stick"
The people angle: a team that rehearsed rollback every month until the real one was boring,
and what it cost them in goodwill to keep doing it after the first two felt pointless.

- Source: author seed thesis (2026-09-14)
- Maps to: Vantage Grid Cooperative metering team (fictional)
- Outcome/metric: rehearsal time 45 min/month; one real rollback in 14 months, 11 minutes
- Rank rationale: great human material, thin on the technical mechanism — belongs to the
  narrative voice, not the technical one.
- Convergence note: re-pick under `demo-mira` with the stakes-prober and narrative-prober
  panel; it is a story about discipline, not a story about deployment.

---

## Run — 2026-09-16 · Seed thesis: "the last manual scheduling board in the bay"

Original raw material (author's words, fictional):
> "The ferry terminal ran its daily schedule on a board with magnets for forty years. When
> they finally replaced it, the superintendent kept the board's brass rail. That's the piece."

Taken forward this run: **Spike #1 — the board on the wall** →
`drafts/the-board-on-the-wall/` (voice: demo-mira, stage: ready-for-human-pass).

Vaulted below: #2, #3.

### Spike #1 — "The board on the wall"  → TAKEN FORWARD
The object piece: forty years of daily ferry scheduling run on a board with magnets, and the
brass rail the superintendent kept after it was replaced.

- Source: author seed thesis (2026-09-16)
- Maps to: Kestrel Bay Ferry Authority (fictional), superintendent cleared to be quoted by role
- Outcome/metric: none — this spike carries no metric, and that is fine for this voice
- Rank rationale: top of the list on material alone: a real object, a named witness, a turn
  (the cutover), and a detail nobody outside would think to include.
- Convergence note: absorbs #3 (the magnet colors were a schema) as its middle section; #2
  (the eleven worse days) was deliberately left out to keep one through-line.
- Piece: `drafts/the-board-on-the-wall/` (voice: demo-mira)

### Spike #2 — "Why the replacement system was worse for eleven days"
The cutover's honest middle: the new system was correct and the board was legible, and for
eleven days the terminal ran slower because legibility had been doing real work.

- Source: author seed thesis (2026-09-16)
- Maps to: Kestrel Bay Ferry Authority (fictional)
- Outcome/metric: 11 days of slower turnarounds; one missed sailing
- Rank rationale: the best counter-argument to any modernization story, but it undercuts the
  taken-forward piece and would need to be its own essay to be fair.
- Convergence note: pairs with the "tools encode judgment" thread in the author's notebook;
  rises if a second cutover example is found so it isn't a single-case argument.

### Spike #3 — "The magnet colors were a schema"
Forty years of tacit convention: which magnet meant a relief vessel, which meant a yard day,
who was allowed to move them, and what was lost when that became a dropdown.

- Source: author seed thesis (2026-09-16)
- Maps to: Kestrel Bay Ferry Authority (fictional)
- Outcome/metric: none yet
- Rank rationale: gorgeous detail, no arc — it is a section, not a piece.
- Convergence note: already absorbed as the middle section of the taken-forward spike; kept
  here in case it wants to be a standalone essay on tacit knowledge.
