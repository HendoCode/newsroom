# PANEL.md — How the Content Machine flows

This describes how the pieces fit together so your harness (openclaw or otherwise)
can wire the loop. This file is spec, not code — your agent owns the orchestration.

## The pieces
- `interviewers/*.md` — extraction personas. Run BEFORE any draft exists. Each pulls
  raw material out of you. They are voice-neutral by design; an interviewer should
  sound like themselves, not like you.
- `editors/*.md` — judgment personas. Run AFTER a draft exists. Each scores 1-10 and
  splits feedback into (a) editorial fixes the machine can rewrite and (b) information
  gaps only you can fill.
- `voice/<voice>/` — one pack per person the machine writes for (e.g. `voice/demo-mira/`,
  `voice/demo-dana/`). Exactly one voice is ACTIVE per session, chosen at the start. Each pack:
  - `voice-guide.md` — the DNA. The DRAFTING step reads this. So do the
    voice-guardian and slop-allergist editors.
  - `style-guide.md` — who this person is, what they promote. Context for all personas.
  - `content-lessons.md` — grows over time, per voice. Lessons override the style guide on conflict.

## The flow

1. IDEA
   Pick a topic / content spike.

2. INTERVIEW  (interviewers/)
   Select 2-4 interviewers suited to THIS piece — not all ten every time.
   - Building/architecture piece → architect, ferriss, operator
   - Customer story → customer, walters, barbaro
   - Opinion / brand post → rogan, stern, skeptic, king
   - Piece touching a partner → add interviewers/partner-advocate.md with the
     partner as parameter (it reads partners/<partner>.md). Zealous by design at
     THIS stage — surfaces the partner's relevant offerings so you can say yes/no.
     Honest "no" is fine. See partners/README.md.
   Run them one at a time. One question per turn. You answer out loud (transcribe
   with Whisper Flow or similar). Do NOT let them stack questions.
   The full transcript is the raw material. This is where slop is prevented —
   thin answers here produce thin drafts no editor can save.

3. DRAFT
   Write against the interview transcript as SOURCE and voice/<active-voice>/voice-guide.md
   as INSTRUCTION MANUAL. The transcript supplies substance; the voice guide supplies
   register. The AI structures your words — it does not invent claims.
   Output is drafts/<piece>/draft.html — a self-contained, browser-openable HTML doc.
   Each piece gets its own folder (see "Pieces" below), so several can be in flight at once.

4. COUNCIL  (editors/)
   Run the editors on the draft. For a given piece, 4-6 is usually right, but always
   include slop-allergist and voice-guardian. Each returns:
     Score: N/10
     Editorial fixes (machine rewrites these itself)
     Information gaps (these route BACK to step 2 — pick the interviewer who fits
       the gap and ask just that)
   Note: slop-allergist and technical-reviewer have HARD fails that cap the score
   regardless of other merits. Respect the cap.

5. REVISION LOOP
   Apply editorial fixes. Route information gaps back to a targeted interview.
   Re-run the council. Repeat until aggregate >= 9/10. (Tune the threshold; 9 is
   Alex's bar.)

6. FINAL HUMAN PASS
   You edit and publish. The machine does not publish for you. draft.html is the
   handoff artifact; you adapt it to the destination (blog HTML, LinkedIn/X plain text).

7. LESSONS LOOP
   Diff the AI's last draft against your published version. Extract generalizable
   lessons. With your approval, append to voice/<active-voice>/content-lessons.md. Next draft
   starts smarter.

## Pieces (one folder per content target)
Each piece the machine works on gets its own folder under drafts/, so several can be
in flight at once without colliding:

    drafts/<piece-slug>/
      piece.md        — metadata + status: voice, origin spike, target, council score, stage
      draft.html      — THE output content, self-contained browser-openable HTML (the council edits this)
      transcript.md   — the interview source
      sources.md      — citations, council record, pre-publish checklist
      assets/         — diagrams/images (SVGs are also inlined into draft.html)

The active piece is tracked orchestration state, named in the state banner alongside the
active voice — you work one piece at a time, and each step reads/writes only that folder.
The voice a piece belongs to is recorded in its piece.md (not the path), so a piece can
change hands. See drafts/token-vs-storage/ for a worked example.

## Pruning (your stated plan)
Run the full roster for a while. Track which personas actually surface material or
catch problems the others miss. Delete the dead weight — it's `rm interviewers/x.md`,
nothing else to unwind. The roster is meant to shrink.

## Roster
Interviewers: ferriss, rogan, walters, stern, barbaro, king (Alex's six),
  plus architect, customer, skeptic, operator (role-shaped, tuned to your material).
Editors: perell, puri, housel, slop-allergist (Alex's four),
  plus voice-guardian, technical-reviewer, specificity-auditor, structure-editor,
  cold-reader, closer.

## Engine files (the connective tissue)
- engine/1-oracle.md         — step 1, finds & ranks ideas (two-stage rank), writes to Notion + Vault
- interviewers/*.md          — step 2, extraction
- engine/2-draft.md          — step 3, transcript + voice → drafts/<piece>/draft.html
- engine/3-revision-loop.md  — steps 4-5, council + revise-to-9
- engine/4-lessons-loop.md   — step 7, learn from your edits
- engine/research-sidecar.md — NOT a step; a side-tool invoked from inside any step
                               ("/research", "dig on that", "verify that"), then returns

## State (Notion + repo)
Three things persist in Notion: the daily ranked idea list, drafts in progress, and
content-lessons.md. Unused spikes → the Vault database. Nothing is thrown away.
In the repo, each in-flight piece persists as a drafts/<piece>/ folder (draft.html +
piece.md + transcript.md + sources.md), so work survives between sessions and pieces.

## Start here
Read sandbox/DRY-RUN.md — one full loop on fictitious data, so you can see every
handoff before wiring real sources. Then run it for real and tune the Oracle first;
it's the step most likely to need your taste applied after you see it work.
