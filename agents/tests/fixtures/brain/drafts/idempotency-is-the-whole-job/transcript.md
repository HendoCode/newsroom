# Interview Transcript — idempotency-is-the-whole-job

Source material for this piece. Per the Masthead flow, the draft traces back to this
transcript: every claim, number, story, and example in `draft.html` must appear here or be cited
in `sources.md`. Answers are recorded as spoken and deliberately NOT cleaned up — the drafting
step shapes them.

> **Demo piece — FICTIONAL.** Harborline Freight, its systems, its numbers, and every quote
> below are invented for this repo. Nothing here reports a real incident.

Roster run (3 of 11): **architect** (done), **domain-specialist** (done), **skeptic** (in
progress — Q2 pending, author's turn).
Not used: customer-advocate, narrative-prober, stakes-prober, layperson, curious-generalist,
polish-breaker, tactician, operator. partner-advocate dormant (no partner configured).

State banner:
`[VOICE: demo-dana · PIECE: idempotency-is-the-whole-job · STEP 2 · INTERVIEW · persona: skeptic · Q2 · author's turn]`

---

## architect  (done — done-when checks met)

**Q1 — Walk me through it piece by piece. What are the components, and what talks to what?**
"Okay. Carrier events come off the bus — arrival, detention, delivery confirmation, an accessorial
charge. The bus gives us at-least-once delivery, which means duplicates aren't an edge case,
they're guaranteed. So the settlement worker pulls an event and the very first thing it does is
try to claim an idempotency key in a table called `settlement_claims`. Unique index on the key.
If the insert succeeds, we own it, we do the work, and we write the result — the actual response
payload, not just a flag — back onto the same row. If the insert fails because the row is there,
we read the stored response and return it. That's the whole loop."

**Q2 — Where does state live? Who owns it, and who else can touch it?**
"One table, one owner. `settlement_claims` is written only by the settlement worker. Nothing
else in the system inserts into it, and the reporting job reads a replica, never the primary.
The row holds four things: the key, a hash of the request payload, the response we produced, and
the timestamp. The key is `(tenant_id, event_type, business_key)` — for a carrier payment the
business key is the load number plus the settlement leg. So the same load can have an arrival
claim and a detention claim and they don't collide, but the same leg can't settle twice."

**Q3 — Where does this break? What did you have to design around?**
"Two places. First: the work succeeds and the response is lost — client times out, or the worker
restarts mid-write. If we only stored a boolean, the retry would see 'claimed' and have nothing
to return, so the caller can't tell success from in-flight. That's why we store the response. The
row gets written in the same transaction as the effect, outbox-style, so there's no window where
the claim exists and the money hasn't moved.
Second: same key, different payload. A producer bug re-mints an event with the same business key
but a different amount. We hash the payload and compare. Same hash, return the stored response.
Different hash, that's a 409 and it pages someone — because it means two systems disagree about
what a payment is, and deduping that silently is how you pay the wrong number twice."

**Q4 — You picked X. What did you rule out, and why?**
"We ruled out letting the server mint the key. If the server generates it, a retry from the
producer arrives without one, gets a fresh key, and you've duplicated the payment — the key has
to be minted by whoever is doing the retrying, or it isn't an idempotency key at all. We also
ruled out Redis for the claim store. It's fast and we already run it, but a claim that can
evict is a claim that can be forgotten, and this is money. Postgres with a unique index is
slower by about four milliseconds at p99 and it does not lose the answer."

## domain-specialist  (done — done-when checks met)

**Q1 — In this industry, what is that thing actually called, and who owns it?**
"In freight brokerage the artifact is a settlement packet: the load, the carrier payment, the
accessorials, and the broker margin, all tied to one load number. Nobody says 'event' out loud.
The settlement packet is owned by the settlement team; the load record is owned by operations,
and they fight about the accessorial fields constantly because ops adds them in the yard and
settlement has to pay them."

**Q2 — Is there a rule — contractual, safety, audit — that constrains this? What happens if it's
violated?**
"Yes, and it's the one that actually set our retention window. Carrier agreements and the
accounting side require every carrier payment to trace back to exactly one approved settlement
packet, and the records stay retrievable for seven years. So the claim row is an audit artifact,
not just a dedupe mechanism. If you can't show one claim per payment, you fail the audit, and a
duplicate payment isn't a bug you fix in code — it's a recovery process with the carrier, which
is a phone call nobody wants to make."

**Q3 — What's the step in that workflow that always breaks, which a generalist description skips?**
"Accessorials. Detention, lumper fees, a re-delivery. They arrive late, sometimes days after the
load is closed, and they're keyed to the same load number. If your business key is just the load
number, the detention charge collides with the original settlement and one of them gets dropped.
That's the bug that made us add the leg to the key. It's also the thing a reviewer who's never
run settlement will miss, because on the diagram it looks like one event type."

**Q4 — Who would read this and immediately know you haven't done the job?**
"Anybody who's reconciled a carrier statement. If the piece says 'we dedupe events' without
saying what the business key is and how late accessorials are handled, they'll know it was
written from the architecture diagram and not from the on-call rotation."

## skeptic  (IN PROGRESS — Q2 pending, author's turn)

**Q1 — How do you know the key scheme is right? What's the evidence, not the design intent?**
"Two things. The incident: in February we had 214 duplicate carrier payments in about nine hours,
because the retry path re-entered at the handler instead of the gateway and every retry minted a
new key. After we moved key minting to the producer and added the claim table, we ran six weeks
at about 1.2 million events a day with zero duplicate settlements. Zero. Not 'fewer.' I can point
at the reconciliation report for each week."

**Q2 — What's the strongest argument against what you just said? Where would a competitor poke?**
"Two pokes. One: six weeks of zero is six weeks — it doesn't prove the scheme survives a
producer that re-mints keys after a deploy, which is exactly how the February incident started,
so the honest claim is that we fixed the case we hit, and we have a test that replays it.
Two: the four-millisecond p99 cost is measured on the claim insert, not on the whole settlement
path, so it's a lower bound, not a total."

**Q3 — [PENDING · author's turn] You said the retention window was set by an audit rule. How long
is it, what did it cost you in storage, and what did you rule out to get there?**
*(Not yet answered. This is the question the orchestrator asks next — one question, then wait.
When answered, check the skeptic's done-when: every major claim has evidence behind it or has
been downgraded to what's defensible, and the honest caveat is on the record. Q2 already put one
caveat on the record; Q3 closes the cost side. Then Step 2 is complete and Step 3 may run.)*

---

## Provisional GAPs (promoted into draft.html's editorial block when the draft is written)
1. `[GAP: retention window length + row count + storage cost]` — skeptic Q3, unanswered.
2. `[GAP: confirm the February incident timeline with the on-call record]` — 214 duplicates and
   the nine-hour window are from memory in Q1; sources.md has no artifact behind them yet.
3. `[NOTE: Harborline Freight is a fictional demo subject]` — in a production instance this line
   would carry the clearance status for naming the client. Here it records that the demo has no
   real subject to clear.
