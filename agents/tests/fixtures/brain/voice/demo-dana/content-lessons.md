# Content Lessons — demo-dana

This file starts small and grows. After each piece, the Lessons Loop (`engine/4-lessons-loop.md`)
diffs the machine's final draft against the published version, extracts generalizable rules, and
— only on the author's explicit yes — appends them here.

**Lessons override `voice-guide.md` and `style-guide.md` when they conflict.** They are the
author's own confirmed edits, which outrank any general rule.

## File precedence in this pack
1. `content-lessons.md` (this file) — distilled from shipped work; wins every conflict.
2. `voice-guide.md` — the register authority and the DNA.
3. `style-guide.md` — who the persona is, what she writes, who reads it.

## Seed lessons (invented with the persona — the starting taste)
- A number that carries an argument must carry its scope in the same sentence: which system,
  which month, which traffic level. "p99 dropped to 340ms" is a claim; "settlement path, March,
  ~1.2M events/day, p99 340ms from 1.9s" is evidence.
- State the failure mode before the reader asks. If a design section ends without saying how it
  breaks, the section is unfinished.
- Never open with the industry. Open with the problem in the first two sentences.
- Match length to the question. A 400-word answer that is complete beats a 1,400-word one with
  the same content.
- Name the rejected alternative and what it would have cost. A design with no rejected option
  reads as a preference, not a decision.

## Learned lessons (demo entries — what the loop appends in a live instance)
<!-- Each entry: date · the change observed in the published version · the generalizable rule. -->
- 2026-08-02 · Author cut a four-sentence explanation of what a retry budget is and replaced it
  with a one-line definition plus a pointer. **Rule:** define a term in one line or assume the
  reader knows it; never explain a standard concept at length in a piece whose audience runs
  production systems.
- 2026-08-19 · Author moved the diagram above the "Mechanism" section, from below it.
  **Rule:** the diagram is the orientation, not the illustration — it goes before the prose that
  walks through it.
- 2026-09-06 · Author changed "we saw duplicates" to "the dedupe table logged 214 duplicate keys
  between 02:11 and 02:19 UTC." **Rule:** replace observed-behavior verbs with the log line,
  timestamp, or counter that showed it. If there is no artifact, the observation is a rumor.
- 2026-09-06 · Author deleted a closing paragraph that began "In short,". **Rule:** if the verdict
  section needs a summary in front of it, the verdict section is too long.
