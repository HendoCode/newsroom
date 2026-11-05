---
name: council
description: "Runs editorial council loop over drafts/<piece>/draft.html with mandatory editors."
allowed-tools: read write cli
---

# Council Skill

Runs the editorial council loop over `drafts/<piece>/draft.html`.
Mandatory editors: `slop-allergist` and `voice-guardian`.
Scores >= 9/10 required before publication handoff.

## Triggers
- "run council"
- "editorial review"
- "revise draft"
- "step 4"
- "check the draft"
- "editors on this"

## Instructions
1. Read `drafts/<piece>/draft.html` and `engine/3-revision-loop.md`.
2. Evaluate the draft against each selected editor persona in `editors/*.md`.
3. Score each dimension out of 10 and enforce the mandatory checks (`slop-allergist`,
   `voice-guardian`, `presentation-reviewer`) and every hard cap they raise. Add
   `partner-brand-steward` only when the piece names a configured partner, and then enforce
   the naming and brand rules in `partners/<partner>.md` (see `partners/README.md`).
4. Apply editorial revisions directly or route information gaps back to Step 2 (Interview).
5. Iterate until all scores reach >= 9/10.
