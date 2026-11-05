# Sources & Handoff — idempotency-is-the-whole-job

Everything the draft will rest on, with citations, plus the council record and the pre-publish
checklist. Written so the author can edit the draft directly without losing provenance.

> **Demo piece — FICTIONAL.** The "internal artifacts" cited below are invented props of this
> demo. There are no real systems, reports, or URLs behind them, and none should be added: this
> repo ships no external citations. A production piece fills this section with real, dated,
> retrievable sources.

## Research citations (every figure in the draft must trace here)
Status: **thin on purpose.** This piece is at Step 2, and one of the things a reader should see
is what an un-sourced piece looks like before the loop forces it to be sourced.

| Claim in the transcript | Source | Verified? |
|---|---|---|
| 214 duplicate carrier payments over ~9 hours, February | author's recollection (Q1) | no — `[GAP]` needs the reconciliation export |
| ~1.2M events/day on the settlement path | author's recollection (Q1) | no — `[GAP]` needs a dated throughput figure |
| 0 duplicate settlements across 6 weeks | weekly reconciliation reports | partially — reports named, not attached |
| +4ms p99 on the claim insert | author's measurement (Q4) | no — scope is the insert only, stated as a lower bound |
| 7-year retrievability requirement for carrier payments | carrier agreements + accounting policy | asserted in interview, not cited |
| ~38M rows at a 90-day retention window | not yet established | no — depends on skeptic Q3 |

## Sidecar research log
- none run yet. When the retention/cost question needs an outside figure, `engine/research-sidecar.md`
  is invoked mid-step ("/research <q>"), announces its return point, and hands back to
  skeptic Q3. Research findings land in this file, never straight into the draft.

## Council record
- Round 1: **not run.** The council does not score a piece that has no `draft.html`.

## Pre-publish checklist
1. `[GAP]` Close skeptic Q3 — retention window, row count, storage cost, what was ruled out.
2. `[GAP]` Attach the February incident artifact (on-call record or reconciliation export) or
   downgrade the claim to what the author can defend from memory, labeled as memory.
3. `[GAP]` Attach or date the six-week reconciliation reports; if they can't be attached, scope
   the claim to the weeks the author personally reviewed.
4. Clearance: the subject is fictional in this demo, so nothing to clear. In production this
   line names every person and client quoted and records their sign-off date.
5. Diagram: draw the retry path (producer mints key → gateway → claim insert → work → stored
   response) and inline it as SVG. The point of the diagram is that the retry re-enters at the
   gateway, not the handler — caption it that way.
6. Presentation check before handoff: one `<h1>`, no skipped levels, tables for the before/after
   numbers, no decorative glyphs in headings.

## After you publish
Come back and run Step 7 (Lessons): the machine diffs the published version against the draft,
proposes generalizable lessons, and on an explicit yes appends them to
`voice/demo-dana/content-lessons.md`.
