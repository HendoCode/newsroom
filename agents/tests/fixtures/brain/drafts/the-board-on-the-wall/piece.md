# Piece: the-board-on-the-wall

Metadata + status for this content target. One of these folders per piece;
many can be in flight at once, each at its own stage, for its own voice.
The active piece is named in the orchestrator's state banner.

> **Demo piece — FICTIONAL.** Invented place, invented people, invented quotes — and the
> clearances in `sources.md` are part of the fiction, shown in the shape a real piece's
> checklist takes. This is the piece to read if you want to see a finished artifact: a draft that
> cleared the council at 9.2 and is waiting on the only step the machine never performs.

## Metadata
- Slug:        the-board-on-the-wall
- Voice:       demo-mira
- Title:       The board on the wall
- Origin:      Oracle run 2026-09-16 · Spike #1 (see VAULT.md); absorbed spike #3 (the magnet
               colors were a schema); spike #2 (the eleven worse days) deliberately scoped to one
               paragraph — recorded in draft.html's editorial block
- Target:      field-notes essay, ~1,500 words (blog); two excerpts plus one connective sentence
               for a social destination on the human pass
- Partners:    none configured (see partners/README.md; the council ran quality-editors-only)

## Files in this folder
- draft.html      — THE output content, v4 (final), self-contained and browser-openable. The
                    council edited it in place across four revisions. Its editorial block is
                    retained with nothing open in it, because the `<section class="editorial">`
                    string is a parser contract; the human pass removes it.
- transcript.md   — interview transcript, COMPLETE (narrative-prober, stakes-prober, layperson)
- sources.md      — provenance table for every detail, the cut-for-lack-of-provenance list, both
                    council rounds with per-editor scores, and the pre-publish checklist
- assets/board-schematic.svg — editable source for the figure inlined into draft.html
- meta.json       — this status, machine-readable

## Council
- Editors selected: round 1 = 6 (slop-allergist, voice-guardian, presentation-reviewer,
  cold-reader, closer, idea-density); round 2 added durability-reader.
  partner-brand-steward not loaded — no partner is configured for this piece.
- Round 1 aggregate: **7.8 / 10** — no hard caps; the shortfall was voice drift into the
  technical register and a summary ending.
- Fixes applied: 8, all recorded in sources.md. Two information gaps routed back to Step 2 and
  closed (one with a negative answer, which still closes a gap).
- Round 2 aggregate: **9.2 / 10 — clears the 9 bar.**

## Status
- Stage:          ready-for-human-pass   (interviewing → drafting → council → ready → published)
- Council score:  9.2 (round 2)
- Open GAPs:      0
- Clearances:     both speakers reviewed and cleared their paragraphs; one invented detail
                  (*Cormorant*) disclosed in sources.md rather than passed off as sourced
- Published URL:  none — the machine never publishes (RULES.md 9)

## Resume point
`[VOICE: demo-mira · PIECE: the-board-on-the-wall · STEP 6 · HUMAN PASS · author's turn]`
Next action is the author's: read v4 for the sentence-level ear, strip the editorial block, adapt
the two excerpts for the social destination, and publish. After publication, run Step 7
(`engine/4-lessons-loop.md`) to diff the published version against v4 and propose lessons for
`voice/demo-mira/content-lessons.md`.
