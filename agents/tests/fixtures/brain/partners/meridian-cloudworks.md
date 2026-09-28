# Partner Facts: Meridian Cloudworks  — FICTIONAL DEMO PARTNER

> **This company does not exist.** Every product name, version, region count, and brand rule
> below is invented for the demo suite, so the partner seam in `partners/README.md` can be
> read end to end without naming a real vendor or reproducing a real brand's guidelines.
> Do not cite this file as a source. Do not "verify" it against the web — there is nothing
> there to find. In a production instance, real partner files live here privately.

last-verified: 2026-09-14 (demo data — invented, not checked against anything real)
staleness-warning: Treated as a live file for demo purposes: the steward should warn that
  naming in this space changes fast and recommend a re-check before publish. Real files carry
  a genuine date and get re-verified against the partner's own documentation.

## Naming conventions (exact styling the steward enforces)
- **Meridian Cloudworks** — two words, both capitalized, in prose. Never "MeridianCloudworks",
  never "Meridian" alone on first reference.
- **Meridian Relay** — the managed message-bus service. Not "Relay", not "Meridian Relays".
- **Meridian Ledger Store** — the append-only audit store. Not "LedgerDB", not "the ledger".
- **Meridian Edge Points** — always plural, always capitalized, when referring to the network.
- **Meridian Control Desk** — the support/operations console. Not "the Meridian dashboard".

## Naming traps to catch in drafts
- **Meridian Relay Classic** is the OLD (pre-2025) bus service, renamed and closed to new
  tenants. Calling it just "Meridian Relay" in new content points at the wrong product.
- **"Meridian Stream"** was a marketing name used for about six months and never shipped.
  If it appears in a draft, it is almost certainly a hallucination.
- Edge Points are numbered, not named: "Edge Point 4", never "the Frankfurt edge".

## Offerings relevant to the author's work (invented)
- **Meridian Relay** — ordered, exactly-once delivery between services; per-tenant topics;
  replay window measured in days, not hours.
- **Meridian Ledger Store** — append-only, hash-chained audit records; read replicas for
  analytics; the write path is the only source of truth.
- **Meridian Edge Points** — 12 fictional regions; same-region traffic between a tenant's
  services stays on the private network and is not metered.
- **Meridian Control Desk** — tenant-scoped runbooks, on-call rotation, and the incident
  timeline that comms teams quote from.

## Brand guidelines (the steward's rubric)
- Register: plain, technical, no superlatives. "Durable" and "ordered" are acceptable;
  "industry-leading", "seamless", "revolutionary", and "AI-powered" are prohibited.
- Never claim a compliance certification for Meridian in the author's voice. Attribute it:
  "Meridian states that Ledger Store is audited annually." Nothing stronger.
- Never quote a price, an SLA percentage, or a region count without attributing it to
  Meridian's own published documentation and dating it.
- No comparative claims against other vendors. Meridian's own team would wince, and it costs
  the author credibility with them.
- Capability claims must be present tense and shipped. Anything unreleased is labeled
  "(announced, not generally available)" or cut.

## Approved CTAs (verbatim; anything else attached to this partner is a finding)
- "Read the Meridian Relay architecture notes."
- "Ask your Meridian contact for the Ledger Store audit walkthrough."
- No pricing CTA, no "sign up" CTA, no discount or trial language.

## Attribution rule
Meridian's claims belong to Meridian: "Meridian states / documents / positions it as…".
The author's claims stay separate and unattributed. If a sentence could be read as the author
vouching for a Meridian number, rewrite it or mark it `[GAP: verify against Meridian docs]`.
