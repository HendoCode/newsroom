# Partner seam — optional, dormant by default

This directory is the ONE configurable slot in the machine. Everything else (voices,
interviewers, editors, engine steps) is always on. Nothing here is loaded unless a partner
is configured for the piece, and **no partner is configured by default**: the council then
runs quality-editors-only and the interview panel skips the advocate. That is the normal
path through this repo, and both demo pieces at council stage in `drafts/` take it.

## The design
There is not one persona per partner. There are TWO parameterized ones:

- `interviewers/partner-advocate.md` — zealous. Runs at Step 2 and surfaces every place the
  partner's offerings genuinely touch the topic, so the author can say yes or no.
- `editors/partner-brand-steward.md` — NOT zealous. Runs at Step 4 and fact-checks the
  partner content already in the draft: naming, accuracy, positioning, brand rules, staleness.

Each takes a partner slug as a parameter and reads that partner's file in this directory.

**Why parameterized:** the offerings landscape changes constantly. A hardcoded "vendor X
zealot" persona rots the day a service is renamed. Keeping the persona stable and the FACTS
in a file means staying current is editing one short file, not rewriting a persona.

**Why the asymmetry:** at the interview stage more raw material is always good — an advocate
that surfaces a forgotten capability helps, and an honest "no, irrelevant" costs nothing. At
the editor stage a booster that pushes products IN would fight the slop-allergist and
voice-guardian every loop and drag the writing toward the exact hype register the voice guide
bans. So the editor only checks correctness and brand compliance. Recall goes up; bias doesn't.

## Configuring a partner
1. Add `partners/<slug>.md` (copy the demo file's shape).
2. Name that partner in the piece's `piece.md` metadata (`Partners: <slug>`).
3. The loop then adds `partner-advocate` at Step 2 and `partner-brand-steward` at Step 4,
   parameterized with `<slug>`. If two partners appear in one piece, run each persona once
   per partner.

Removing a partner is `rm partners/<slug>.md`. Nothing else references it: the personas are
parameterized, the engine selects by what exists, and the pieces that ran with it keep their
council record in their own `sources.md`.

## What a partner file must contain
The steward's rubric is the file, so these sections are load-bearing:

- `last-verified:` date and a staleness warning — the steward cites this when it warns
  instead of asserting.
- **Naming conventions** — the exact current product/service names, plus known naming traps
  (a renamed service is the single most common published error).
- **Offerings relevant to the author's work** — enough for recall, not a catalogue.
- **Brand guidelines** — required styling, prohibited phrasing, disclaimers, and what the
  partner's own team would wince at.
- **Approved CTAs** — the calls to action this partner permits, verbatim. The steward flags
  any other CTA attached to that partner's name.
- **Attribution rule** — the partner's claims are attributed to the partner, never asserted
  as the author's fact.

## Keeping facts current
The steward flags a stale file, but flagging isn't verifying. Before publishing a piece that
names a partner: check `last-verified`, re-check the product NAMES against the partner's own
current documentation, update the file, bump the date. `engine/research-sidecar.md`
("verify that") is the tool for the re-check.

## This repo's contents
`meridian-cloudworks.md` is a **fictional demo partner** — an invented company with invented
products, included so the seam is legible end to end without naming a real vendor or quoting
a real brand's guidelines. In a production instance this directory holds the real partner
files, kept privately; they are never committed to a public brain.
