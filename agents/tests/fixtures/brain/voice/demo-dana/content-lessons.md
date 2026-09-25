# Content Lessons — demo-dana

Starts from patterns distilled from example collateral and grows. After each piece, the
Lessons Loop diffs the shipped version against the draft and (with approval) appends
generalizable rules here. Lessons override the voice/style guide when they conflict.

## File precedence (when guides conflict)
When two references in this directory give conflicting guidance, apply them in this order
(earlier wins):
1. **content-lessons.md** (this file) — distilled from shipped work; overrides everything below.
2. **voice-guide.md** — the authoritative register/DNA for demo-dana (partner-facing
   voice: PRFAQs, technical FAQs, partner collateral). This is the primary voice reference.
3. **style-guide.md** — author persona and audience.
4. **brand-guidelines.md** — Hendo Code's shared writing-style reference (tone,
   prohibited language, formatting conventions). Use it for brand facts everyone shares.
   Where its register differs from voice-guide.md, **voice-guide.md wins for demo-dana
   pieces.**

**Visual (a separate axis — governs look, not words):** `visual-identity.md` is the
canonical color/font/component reference for any piece that renders as HTML (draft.html),
a deck, or a graphic. Canon is the **slate/amber/cream + Josefin Sans / Georgia** system.
It doesn't conflict with the voice files — apply it alongside them.

## Seed lessons (from source examples, 2026-07-28)
- Lead with the problem in parallel structure, then name the answer. ("Shipping an agent
  is easy. Shipping it safely... is the hard part.")
- Anchor positioning to a known product in one line when you can ("Vercel for agents").
- Every feature is a bold claim + a concrete mechanism in the same breath. No claim floats.
- Prefer before/after deltas and stat tiles over adjectives ("3 days → 7 min",
  "40% → 98%+", "20× workers").
- Make governance/security a first-class part of the story, not a footnote — self-hosted,
  "never leaves your network", audit trail, compliance targets.
- Name the real stack (Helm, MongoDB, Vault/KMS, Bedrock AgentCore, Vertex Agent Engine,
  LangGraph/CrewAI). Specific tech beats generic "integrations".
- Segment by audience when it helps (Product/AI, Enterprise buyers, Support, Developers),
  each with its own value line.
- Close on "why this matters for your team" + exactly one next step.
- "X, not Y" contrast framing and parallel triads are encouraged here — the opposite of the
  personal voices. Still: no empty adjectives, no hype without a number behind it.

## Seed lessons (from a technical-FAQ example: AWS AgentCore FAQ reference, 2026-07-28)
- Register flexes by format: a technical FAQ/PRFAQ answer is neutral, dense, and precise —
  reference-doc register, not launch-copy energy. Same DNA, lower voltage.
- FAQ structure: group Q&A by component/topic, enterprise concerns (billing, SLA, security &
  compliance) last. `## Section` → `### Question?` → answer.
- Phrase questions as a partner actually asks them (what / who / key benefits / how does it
  work with / what's the difference / should I switch / regions / pricing / SLA / security).
- Give the exact fact, listed out — all 15 regions, all 13 evaluators. Specific-and-long
  beats vague-and-short in a FAQ.
- Answer decision questions even-handedly ("you can keep using X"); honesty out-converts a
  hard sell with this audience. Label "(Preview)" / not-GA features honestly.
- When documenting a partner's product: cite the source, paraphrase (never copy), and
  attribute the partner's claims to the partner ("AWS states/notes"). Mark unverified
  partner facts for check — they go stale fast.

## Learned lessons
<!-- Appended over time. Each entry: date, the change observed, the generalizable rule. -->
