# Piece: rehearse-the-rollback

Metadata + status for this content target. One of these folders per piece;
many can be in flight at once, each at its own stage, for its own voice.
The active piece is named in the orchestrator's state banner.

> **Demo piece — FICTIONAL.** Invented subject, invented numbers, invented quotes. This is the
> piece to read if you want to see the council fail something and the loop respond: round 1 is
> recorded in full in `sources.md`, including two hard caps, and the draft in `draft.html` is
> the v2 that came out of it.

## Metadata
- Slug:        rehearse-the-rollback
- Voice:       demo-dana
- Title:       Rehearse the rollback
- Origin:      Oracle run 2026-09-14 · Spike #2 (see VAULT.md)
- Target:      design write-up / practice note, ~1,100 words (blog); three-paragraph summary plus
               the duration figure for a social destination on the human pass
- Partners:    none configured (see partners/README.md; the council ran quality-editors-only)

## Files in this folder
- draft.html      — THE output content, v2, self-contained and browser-openable. The council
                    edits this file in place. Carries the `<section class="editorial">` block
                    with two open GAPs.
- transcript.md   — interview transcript, COMPLETE (operator, architect, skeptic; done-when met)
- sources.md      — citations table, the full round 1 council record, fixes applied, gaps routed,
                    round 2 pending, pre-publish checklist
- assets/rollback-duration.svg — source for the figure inlined into draft.html
- meta.json       — this status, machine-readable

## Council
- Editors selected (5): slop-allergist, voice-guardian, presentation-reviewer, technical-reviewer,
  specificity-auditor. partner-brand-steward not loaded (no partner configured).
- Round 1 aggregate: **7.2 / 10** — two hard caps (slop-allergist 6: presuppose-and-dismantle
  opener; presentation-reviewer 6: skipped heading level + `§` markers). Bar is 9.
- Fixes applied: 5, all recorded in sources.md.
- Round 2: **pending** — capped findings fixed, but two information gaps are still open.

## Status
- Stage:          council   (interviewing → drafting → council → ready-for-human-pass → published)
- Council score:  round 1 = 7.2 (below bar); round 2 not run
- Open GAPs:      2 — the incident artifact and the drill log. Both are routed back to Step 2
                  with a single question each, and neither may be filled with a plausible number.
- Published URL:  none yet

## Resume point
`[VOICE: demo-dana · PIECE: rehearse-the-rollback · STEP 4-5 · COUNCIL/REVISION · round 2 · machine's turn]`
Next action: close the two gaps via the routed questions (skeptic, operator), then re-run the
five editors on v2 and record round 2 in sources.md. Only an aggregate >= 9 moves this piece to
`stage=ready-for-human-pass`.
