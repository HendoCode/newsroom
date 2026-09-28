---
name: draft
description: "Generates drafts/<piece>/draft.html using transcript as source and voice guides."
allowed-tools: read write cli
---

# Draft Skill

Generates `drafts/<piece>/draft.html` using `drafts/<piece>/transcript.md` as source and `voice/<active-voice>/*.md` as style manual.

## Triggers
- "draft it"
- "write the draft"
- "run step 3"
- "generate draft"

## Instructions
1. Load `drafts/<piece>/transcript.md`, `drafts/<piece>/sources.md`, and `voice/<active-voice>/voice-guide.md`.
2. Follow `engine/2-draft.md` to structure user words into self-contained HTML.
3. Structure and refine without inventing unstated facts.
4. Mark any missing factual details with `[GAP: ...]` in the non-published block.
5. Save the output to `drafts/<piece>/draft.html`.
