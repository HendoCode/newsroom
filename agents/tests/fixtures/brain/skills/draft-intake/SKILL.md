---
name: draft-intake
description: "Intake for arbitrary or unseen draft inputs, diagnosing gaps against active voice."
allowed-tools: read write cli
---

# Draft Intake Skill

Intake and refinement for arbitrary or external draft text.
Diagnoses voice alignment, missing context, and factual gaps, then routes targeted interview questions.

## Triggers
- "I have a draft"
- "review this draft"
- "intake draft"
- "I wrote something, help me fix it"
- "external draft"

## Instructions
1. Accept raw draft text or a file path from the user.
2. Initialize or verify the active piece directory at `drafts/<piece>/`.
3. Save raw input to `drafts/<piece>/source-draft.md`.
4. Compare draft against `voice/<active-voice>/voice-guide.md` and identify gaps.
5. Formulate targeted interview questions to fill gaps, or proceed directly to Draft / Council.
