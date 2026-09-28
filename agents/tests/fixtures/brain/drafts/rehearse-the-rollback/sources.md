# Sources & Handoff — rehearse-the-rollback

Everything the draft rests on, with citations, plus the council record and the pre-publish
checklist. Written so the author can edit the draft directly without losing provenance.

> **Demo piece — FICTIONAL.** Harborline Freight, its systems, and every figure cited below are
> invented props of this demo. There are no real artifacts, reports, or URLs behind them, and
> none should be added — this repo ships no external citations. That is also the piece's
> honest weakness, and the council scored it that way.

## Research citations (every figure in the draft traces here)

| Figure in draft.html | Where it came from | Status |
|---|---|---|
| 2h 40m rollback, ~6 min of settlement events lost | transcript.md · skeptic Q1 (author's recollection) | `[GAP]` no incident artifact attached |
| 11 minutes, no data loss | transcript.md · skeptic Q1 | `[GAP]` same incident record would cover it |
| eleven drills in fourteen months | transcript.md · skeptic Q1, Q3 | `[GAP]` drill log not attached |
| 45 min × 3 people, monthly | transcript.md · operator Q3, skeptic Q3 | consistent across two personas; acceptable |
| ~27 person-hours a year per path | derived: 45 min × 3 × 12 | arithmetic, shown in the draft's table |
| flag service timeout 400ms vs 50ms budget | transcript.md · skeptic Q3 (drill log quote) | `[GAP]` quote not produced verbatim |
| backfill checkpoint not resumable | transcript.md · architect Q3, skeptic Q3 | corroborated by two personas; acceptable |
| ~40M rows backfilled | transcript.md · architect Q3 | acceptable as scale, not a measured figure |
| four-minute decision time | transcript.md · architect Q4 | author's estimate; labeled as such in the draft |

No sidecar research was run for this piece. If the author wants an outside figure for
expand-contract migration practice, `engine/research-sidecar.md` is the tool: it announces its
return point, returns a short sourced answer into this file, and hands back to the council.

## Council record

### Round 1 — 2026-09-18 · editors selected: 5
Mandatory: `slop-allergist`, `voice-guardian`, `presentation-reviewer`.
By fit (technical piece): `technical-reviewer`, `specificity-auditor`.
Not loaded: `partner-brand-steward` — no partner is configured for this piece, so the council ran
quality-editors-only. That is the default path in this repo (see `partners/README.md`).

| Editor | Score | Finding |
|---|---|---|
| slop-allergist | **6/10 — HARD CAP** | v1 opened: "Every team writes a rollback plan. Almost nobody rehearses it, and that's what nobody tells you." Presuppose-and-dismantle plus challenger-sale bravado. Two hard fails in one sentence; capped at 6 regardless of merit. |
| voice-guardian | 8/10 | Register is right for demo-dana: mechanism before outcome, numbered steps, explicit verdict, no hedging. Two drifts: "at 2am" is scene-setting this voice doesn't use, and one paragraph ran 71 words (guide says 12-18 word sentences carry the load). |
| technical-reviewer | 9/10 | Expand-contract is described correctly and the resumable-backfill failure mode is real. Confirms the flag/image disagreement point — that is the part most write-ups miss. No technical errors. |
| specificity-auditor | 7/10 | Specifics: 9 (durations, headcount, row count, 400ms vs 50ms, 27 person-hours). Vague assertions: 4 ("several tools will sell you", "some of ours are still dual-writing", "resources most services do not get", "the current guess"). Two of the four are recoverable from the transcript. |
| presentation-reviewer | **6/10 — HARD CAP** | v1 jumped `<h2>` → `<h4>` for the backfill subsection (skipped level, breaks scanning) and used `§` as a lead marker in two headings. Both are hard fails. |

**Round 1 aggregate: 7.2 / 10** — below the 9 bar. Two hard caps in force; both are respected
even though technical-reviewer was satisfied. The loop triggers.

### Editorial fixes applied to draft.html (machine did these itself)
1. Replaced the v1 opener with the incident and its cost, then the mechanism — no belief
   asserted and dismantled, no "what nobody tells you." *(clears the slop-allergist cap)*
2. `<h4>` backfill subsection → `<h3>`; removed both `§` markers; headings are plain and
   descriptive throughout. *(clears the presentation-reviewer cap)*
3. Cut "at 2am" and split the 71-word paragraph into three. *(voice-guardian)*
4. Scoped the derived number: "~27 person-hours a year per path" now shows its arithmetic in the
   table's note column. *(specificity-auditor)*
5. Moved "where this does not generalize" above the verdict so the honest limitation is not
   buried after the recommendation. *(structure — voice-guardian + specificity-auditor)*

### Information gaps routed back to Step 2 (one question each)
1. → `skeptic`: "Can you produce the incident timeline for the 2h40m rollback, or should the
   draft say plainly that the figure is from memory?"
2. → `operator`: "Can you produce the drill log entries verbatim, or should the draft carry only
   the two findings you can?"

Both answers land in `transcript.md`, then in the draft, then in the table above. Neither gap is
papered over with a plausible number — that is the whole discipline.

### Round 2 — PENDING
The capped findings are fixed in v2 and the two gaps are still open, so round 2 has not been
run. Expected movement: slop-allergist and presentation-reviewer clear their caps;
specificity-auditor stays capped by the two open GAPs until the artifacts land or the claims are
downgraded to labeled memory. **Do not hand this piece to the human pass before round 2 clears
an aggregate of 9.**

## Pre-publish checklist
1. `[GAP]` Attach the incident artifact or relabel 2h40m / 6 minutes as memory.
2. `[GAP]` Attach the drill log or reduce the findings list to what the author can produce.
3. `[GAP]` Decide whether "several tools will sell you" names a tool or gets cut — an unnamed
   market claim is the kind of sentence the specificity-auditor exists to catch.
4. Clearance: fictional demo subject, nothing to clear. In production this line names every
   person quoted (the engineer who called the drill theater is quoted indirectly — confirm they
   are comfortable being identifiable to their own team).
5. Diagram: `assets/rollback-duration.svg` is the source for the inlined figure; redraw both
   together if the durations change.
6. Presentation check before handoff: one `<h1>`, no skipped levels, table for the cost data, no
   decorative glyphs, no raw markdown leaking into rendered HTML.

## After you publish
Come back and run Step 7 (Lessons): the machine diffs the published version against this draft,
proposes generalizable lessons, and on an explicit yes appends them to
`voice/demo-dana/content-lessons.md`.
