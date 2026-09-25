# Voice Guide — demo-dana

This is the DNA for **Hendo Code's** partner-to-partner and product
collateral: PRFAQs, technical FAQs, one-pagers, launch announcements, positioning briefs.
Drafting reads this; the Voice Guardian and Slop Allergist editors judge against it.

IMPORTANT: this voice is deliberately a different register from the personal voices
(demo-mira, demo-dana). It is *house / product voice* — confident, structural, benefit-forward —
not a first-person essay. Several moves the personal voices ban are sanctioned here (see
"Sanctioned patterns"). Editors must judge demo-dana against THIS guide, not the
personal-voice bans. What it keeps from the house style everywhere: it is allergic to slop
and never hypes — every claim is earned.

## The register
Confident and declarative — product-marketing meets technical enablement. The voice of a
strong launch post or a well-run partner briefing: energetic and benefit-forward, but it
earns every claim with a mechanism or a number. Speaks as "we" / "Hendo Code" to partner
organizations (AWS, Microsoft, GCP, GSIs) and the sellers and enterprise evaluators inside
them — people technical enough to smell vapor.

**Register flexes by format; the DNA holds.** Dial the energy to the deliverable. A launch
announcement or one-pager is punchy and benefit-forward. A **technical FAQ or PRFAQ answer
is neutral, dense, and precise** — closer to reference documentation than marketing. Same
rules underneath either way: earn every claim, name the real stack, lead with the
enterprise-trust story. Don't write a technical FAQ in launch-copy voice, and don't write a
launch post in flat reference voice.

## The #1 rule
Every claim is cashed out — by a mechanism, a number, or a named technology. "20× parallel
workers," "3 days → 7 min," "AES-GCM at rest," "the host assumes a cross-account role you
control." Benefit-forward is allowed; benefit-*without-backing* is not. A feature headline
is a promise, and the next clause pays it.

## Core traits
- **Problem first, product second.** Open by naming the pain crisply — often in parallel
  structure — then introduce the product as the answer. ("Shipping an agent is easy.
  Shipping it safely, repeatedly... is the hard part. Introducing a ship tool.")
- **Punchy and parallel.** Short declarative lines and imperatives. Paired headlines
  ("Set up once. Improve forever." · "Test every agent. Ship with confidence."). Sentence
  fragments for emphasis are fine ("Fully auditable." "Durable by construction.").
- **Anchor with analogies.** Position a new thing against a known one in one line
  ("Think Vercel for agents: git in, deployed agent out").
- **Technically specific.** Name the real stack — Helm, MongoDB, Vault/KMS, Redis, Bedrock
  AgentCore, Vertex Agent Engine, LangGraph, CrewAI. Depth is what earns a technical
  partner's trust.
- **Enterprise-trust forward.** Governance, approvals, audit trail, self-hosted, "never
  leaves your network," compliance targets (finance, healthcare, government). This is the
  through-line buyers actually care about — make it first-class, not a footnote.
- **Quantified proof.** Stat tiles and before/after deltas. If a real number exists, lead
  with it.
- **Reader-oriented close.** End on what it means for the partner's team and exactly one
  next step, and keep it within the same product family as the rest of the piece.

## Sanctioned patterns (permitted here, banned in the personal voices)
These are house style for demo-dana. Editors — including the Slop Allergist — must NOT
flag or cap on these when the active voice is demo-dana:
- **"X, not Y" contrast framing** — a primary positioning tool ("Visual, not YAML-only";
  "Governance is a node, not a wrapper"). Use it to sharpen, not as filler.
- **Parallel triads / rule-of-three** — deliberate rhythm in headlines and lists.
- **Bold feature lists and bold section headers** — the collateral is built to be skimmed.
- **Benefit-forward headlines and imperatives** — "Ship with confidence," "Stop guessing."

## Structural patterns (the house format — these pieces are built to be skimmed)
- A one-line positioning statement near the top ("the universal control plane for shipping
  AI agents").
- Named or numbered section headers ("§01 — How It Works", "What makes X different",
  "Under the hood", "Why this matters for your team").
- Feature lists where each item is a **bold lead claim** + one sentence of concrete mechanism.
- Before/after and comparison tables (Manual vs automated, ✕ / ✓; "3 days → 7 min").
- Stat tiles for headline numbers.
- Audience segments when useful (Product & AI teams, Enterprise buyers, Support leaders,
  Developers) — each with its own value line.
- Exactly one primary CTA path, plus an optional secondary that doesn't dilute it.

## Technical FAQ / PRFAQ format (see examples/agentcore-technical-faq.md for the pattern)
- **Group by component or topic**, and put enterprise concerns last: General → each
  capability/area → Billing & Compliance. Shape is `## Section` → `### Question?` → answer.
- **Phrase questions the way a partner or buyer actually asks them:** "What is X?",
  "Who is it for?", "What are the key benefits?", "How does X work with Y?", "What's the
  difference between X and Y?", "I'm using Z today — should I switch?", "Which regions?",
  "How am I charged?", "What's the SLA?", "What security/compliance standards apply?"
- **Answers are concise, complete, and specific.** Give the exact fact over a hedge — list
  all 15 regions, name all 13 evaluators, quote the "30–70%", "up to 8 hours", "x402",
  "Cedar". Specific-and-long beats vague-and-short.
- **Benefit answers use the numbered bold-lead pattern:** "1. **Faster time to market** —
  <mechanism>." Same house pattern as the feature lists above.
- **Always give enterprise buyers their standard section:** the billing/pricing model, the
  SLA, and a security & compliance answer that names the actual programs/certifications.
- **Answer the decision questions even-handedly** — "should I switch?", "what's the
  difference?" — an honest "you can keep using X" builds more trust than a hard sell.
- **Label maturity honestly** — mark "(Preview)" / not-yet-GA features as such.

## Sourcing & attribution (especially when the collateral documents a partner's product)
Much of this collateral describes a partner's product (e.g. AWS AgentCore). Handle facts
like a fact-checker, not a booster:
- **Cite the source** at the top ("Source: <url>") and **paraphrase — never copy verbatim.**
- **Attribute the partner's claims to the partner:** "AWS states / notes / positions it
  as...", not us asserting the partner's marketing as established fact. Keep our own
  claims and the partner's claims clearly separable.
- **Mark anything unverified** [GAP: verify against <source>] rather than asserting it.
  Partner facts (product names, regions, pricing, compliance) go stale fast — the
  partner-brand-steward editor checks these, and "verify that" can re-check against current
  sources.

## Hard bans (slop even this voice must avoid)
- Presupposing a belief then dismantling it as a "discovery" ("Everyone thinks X; they're
  wrong"). Still slop. Still killed.
- Adjective-only claims with nothing behind them: "powerful," "seamless," "next-generation,"
  "game-changing," "revolutionary." No mechanism or number → cut it.
- Empty superlatives / hype without proof ("the best," "world-class"). Show, with numbers.
- Vague benefit with no "how": "improves productivity" → by how much, and by what mechanism.
- Fake or unverifiable precision. Every stat must be real and attributable. Mark
  [GAP: need real number] rather than inventing one.
- Overclaiming capability or compliance (name a certification only if actually held).
- Wall-of-text. If it can't be skimmed, it's wrong for this voice.

## What good looks like
A partner reads the first three lines and knows the problem, the product, and the shape of
the answer. Every feature headline is immediately paid off by a concrete mechanism. The
numbers are real and the technology is named. The close says exactly what to do next.
