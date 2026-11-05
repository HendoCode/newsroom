# Interview Transcript — rehearse-the-rollback

Source material for this piece. Per the Masthead flow, the draft traces back to this
transcript: every claim, number, story, and example in `draft.html` must appear here or be cited
in `sources.md`. Answers are recorded as spoken and deliberately NOT cleaned up — the drafting
step shapes them.

> **Demo piece — FICTIONAL.** Harborline Freight, its systems, its numbers, and every quote
> below are invented for this repo. Nothing here reports a real incident.

Roster run (3 of 11), **complete** — every persona's done-when checks are met:
**operator** (steps, in order, with the trap), **architect** (mechanism and one real tradeoff),
**skeptic** (claims downgraded to what's defensible; honest caveat on the record).
Not used: customer-advocate, narrative-prober, stakes-prober, layperson, curious-generalist,
polish-breaker, tactician, domain-specialist. partner-advocate dormant (no partner configured).

---

## operator  (done)

**Q1 — If I had to do this tomorrow, what's step one?**
"Pick one path. Not the whole system — one deployable with one database, and the one you'd least
like to break. For us that was the settlement path, which is exactly why we picked it. Then write
the rollback as a numbered runbook with an owner per step and a clock: who says go, who runs the
redeploy, who watches the error rate, who decides whether the data is consistent afterward.
Step one is the runbook, not the automation."

**Q2 — Where do people screw this up? What's the trap?**
"They rehearse the redeploy and skip the data question. Redeploying the previous image is the
easy half — it's a CI job. The half that decides whether you have an incident or a bad afternoon
is: what did the version you're rolling back write while it was up? If your migration wasn't
backward-compatible, the old code reads a schema it doesn't understand and now you have two
outages. So the trap is treating rollback as a deployment problem. It's a schema problem."

**Q3 — Is there a version of this that's actually repeatable, or was it a one-off?**
"It's repeatable because we made it boring. Forty-five minutes, first Tuesday, same runbook, same
path, on a staging environment with production-shaped data. Two people run it, one watches, and
somebody who was not involved last month runs it this month — the rotation is the point. If the
same person always runs the drill you're rehearsing that person, not the team."

## architect  (done)

**Q1 — Walk me through the mechanism. What makes the rollback safe?**
"Expand-contract, and never a down-migration in production. Every schema change ships in two
releases. Release one expands: adds the new column, dual-writes to both, backfills, and leaves
the old path intact. Release two switches reads. The contract — dropping the old column — waits a
third release, and sometimes never happens. That means at any moment the previous release can read
the current schema, so rolling back is redeploying an image, not performing surgery.
Feature flags default off and are flipped after the deploy is healthy, so the rollback is
'previous image plus flag off,' both of which are states we've already run."

**Q2 — Where does state live? Who owns it, and who else can touch it?**
"The schema is owned by the service that writes it, and nothing else migrates it. The flag state
lives in the config service, which is the one shared thing, and it's the reason a rollback has to
be two steps instead of one — the image and the flag are separate systems and they can disagree."

**Q3 — Where does this break? What did you have to design around?**
"Backfills. A dual-write is safe, but backfilling forty million rows is not instant, and if you
roll back mid-backfill you have a partially populated column that the old code ignores — which is
fine — and a new code path that will read it when it comes back, which is not fine unless the
backfill is resumable. So backfills are batched by key range with a checkpoint row. That was
designed after a drill found it, which is the argument for the drill in one sentence."

**Q4 — You picked X. What did you rule out, and why?**
"Automatic rollback. We ruled out auto-reverting on an error-budget breach, which is the obvious
thing to build and which several tools will sell you. Reason: on this path the decision is never
just 'is the error rate up,' it's 'did we write money down in a way that the previous version can
read.' That needs a human, and a human who has run the drill before takes about four minutes to
make it. We also ruled out blue-green for the settlement path — worth the money on the API tier,
not on a batch worker with a schema."

## skeptic  (done)

**Q1 — How do you know the drills made the real rollback fast? What's the evidence?**
"One real rollback in fourteen months of drills. Eleven minutes, no data loss. Before the drills
started, the last rollback on that path took two hours forty and we lost about six minutes of
settlement events, which became a reconciliation project. So: two hours forty versus eleven
minutes is a real before and after, and it is n=1. I'm not going to claim the drill caused it.
What I'll claim is that the person who ran it had run the same runbook four times that quarter,
and that the schema let the old image read it, and both of those are things the drill practices."

**Q2 — What's the strongest argument against what you just said?**
"Selection. We picked the path we were most afraid of, gave it a runbook, a rotation, and
production-shaped staging data — resources most paths don't get. So the honest version is that
the drill is affordable on a path someone cares about, and the interesting question is what the
cheap version looks like for the other twelve services. Which we don't have an answer for yet."

**Q3 — What did the drill cost, and what did it cost you socially?**
"Forty-five minutes a month for three people, so call it 27 person-hours a year per path. The
social cost was the first two months, when it felt like theater and one engineer said so in the
retro, out loud. We kept it anyway, and we changed one thing: every drill has to find something.
Not a big something. If a drill finds nothing, the runbook is wrong, because a runbook that never
surprises anyone is a runbook nobody is reading. Since then the log has entries like 'flag service
timed out at 400ms, we had assumed 50' and 'backfill checkpoint row was not resumable.' Those are
the artifacts."

**Q4 — What would make you stop doing it?**
"If we ever stop changing the schema. We're not going to, so the answer is never. The other
answer is if the drill stops finding things for six months running — then it's ceremony and the
runbook needs to be rewritten to include the parts we've stopped being afraid of."
