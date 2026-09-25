# Partner personas — how they work and how to keep them honest

## The design
There are NOT ten partner personas. There are TWO parameterized ones:
  - interviewers/partner-advocate.md   (zealous — surfaces the partner's relevant offerings)
  - editors/partner-brand-steward.md   (NOT zealous — fact-checks partner content already in the draft)
Each takes a partner name and reads that partner's facts file in this folder.

Why parameterized: the offerings are an ever-changing landscape. A hardcoded "AWS zealot"
rots the day a service is renamed. Keeping the persona stable and the FACTS in a file means
staying current is editing one short file, not rewriting a persona.

## Why the asymmetry (interviewer zealous, editor not)
At the INTERVIEW stage, more raw material is always good — an advocate that surfaces a
forgotten relevant service helps, and an honest "no, irrelevant" costs nothing. At the
EDITOR stage, a booster that pushes products IN would fight the slop-allergist and
voice-guardian every loop and drag the writing toward the exact hype register the voice
guide bans. So the editor only checks that partner content ALREADY in the draft is correct,
current, and on-brand. Recall goes up; bias doesn't.

## Keeping facts current (do this before publishing a partner piece)
1. Open the relevant facts file. Check its `last-verified` date.
2. If it's old, verify the product NAMES against the partner's own site/release notes.
   Cloud vendors rename constantly (see the AWS "Bedrock Agents → Bedrock Agents Classic"
   trap already in aws.md).
3. Update the file and bump `last-verified`.
The brand-steward editor will flag a stale file, but flagging isn't verifying — a human
still checks before publish.

## Adding a partner (e.g. Oracle, IBM, a specific ISV)
Copy the closest existing file, rewrite the facts, set last-verified. Done. No new persona.
Only aws.md was web-verified on creation (2026-07-24). azure/gcp/accenture are from Jan-2026
training knowledge and are marked stale on purpose — verify before first real use.

## Only aws.md is current as of creation
The others are honestly marked stale. That's not a gap to hide; it's the system telling
the truth about what it knows. Verify, then trust.
