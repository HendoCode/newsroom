# Engine Step 4-5 — Council + Revision Loop

You run the editors over a draft and drive it to publishable quality. The draft is
drafts/<piece>/draft.html; editors read and rewrite that HTML in place. The council
record and pre-publish checklist live in drafts/<piece>/sources.md, and you keep
drafts/<piece>/piece.md current (stage, aggregate score, open GAPs) as the loop runs.

## The loop
1. Select the editors for THIS piece. Always include: slop-allergist, voice-guardian, presentation-reviewer. Then 2-4 more by fit:
     - technical piece → technical-reviewer, specificity-auditor
     - customer story → specificity-auditor, cold-reader, closer
     - opinion / essay / argument piece → durability-reader, idea-density, hook-retention, closer
     - piece heavy on one technical domain → run technical-reviewer AND specificity-auditor
       together; route any fact you cannot verify back to the interview rather than
       asserting it.
     - OPTIONAL, only if a partner is configured (piece.md names one and
       partners/<partner>.md exists) → add editors/partner-brand-steward.md WITH THAT
       PARTNER as parameter. It reads partners/<partner>.md and fact-checks partner content
       already in the draft (naming, accuracy, positioning, brand rules, staleness). It does
       NOT push more products in. If two partners appear, run it once per partner.
       With no partner configured — the default in this repo — the council is
       quality-editors-only and this bullet never fires. See partners/README.md.
   4-6 editors is usually right (the partner steward counts as one). Not all every time.
 
2. Each editor returns:
     Score: N/10
     Editorial fixes (the machine can rewrite these itself)
     Information gaps (only the author can fill — these route BACK to the interview)

3. Respect HARD caps. slop-allergist, technical-reviewer, and presentation-reviewer can cap the score
   regardless of other merit. A single unflagged slop tell caps at 6. A technical
   error is not optional to fix. A decorative section marker, raw markdown leak, or broken
   heading hierarchy caps at 6.

4. Compute the aggregate. If < 9/10:
     a. Apply all editorial fixes directly to draft.html (edit the HTML, don't rebuild it).
     b. Collect the information gaps. For each, pick the interviewer who fits
        (a missing metric → customer-advocate or specificity; a fuzzy architecture →
        architect; an unearned claim → skeptic) and ask JUST that question.
        Author answers out loud → transcribe → feed back into the draft.
     c. Re-run the council on the revised draft.
   Repeat until aggregate >= 9/10.

5. Hand the >=9 draft to the author for the final human pass. Set piece.md
   stage=ready-for-human-pass and record the aggregate score.

## Guardrail
The loop rewrites and re-scores. It does NOT publish. Publishing is the human's.
