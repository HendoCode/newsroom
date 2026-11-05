# PANEL.md — How Masthead flows

This describes how the pieces fit together so your harness can wire the loop. This file is
spec, not code — your agent owns the orchestration. Read it once end to end, then run
`sandbox/DRY-RUN.md` to watch one full loop move on invented data.

## The pieces
- `engine/*.md` — the numbered steps. The machine's behavior, in prose.
- `interviewers/*.md` — extraction personas. Run BEFORE any draft exists. Each pulls raw
  material out of the author. They are voice-neutral by design; an interviewer should sound
  like itself, not like the author.
- `editors/*.md` — judgment personas. Run AFTER a draft exists. Each scores 1-10 and splits
  feedback into (a) editorial fixes the machine can rewrite and (b) information gaps only the
  author can fill.
- `voice/<voice>/` — one pack per persona the machine writes for (here: `voice/demo-dana/`,
  `voice/demo-mira/`). Exactly one voice is ACTIVE per session, chosen at the start. Each pack:
  - `voice-guide.md` — the DNA. The DRAFTING step reads this. So do the voice-guardian and
    slop-allergist editors.
  - `style-guide.md` — who this persona is, what they write, who reads it. Context for all
    personas.
  - `content-lessons.md` — grows over time, per voice. Lessons override the style guide on
    conflict.
- `partners/` — the ONE optional slot. Dormant unless a partner is configured; see
  `partners/README.md`.
- `VAULT.md` — the idea archive. Spikes not taken forward, with their convergence scoring.
- `drafts/<piece>/` — one folder per content target, at whatever stage it reached.
- `memory/MEMORY.md` — session pointers: active voice, active piece, current step.

## The flow

1. IDEA — `engine/1-oracle.md`
   Rank raw material into content spikes (two-stage: find the material, then score it up by
   convergence). The author picks one; the rest go to `VAULT.md`. Picking a spike scaffolds
   `drafts/<slug>/` (`scripts/new-piece.sh <slug> <voice>`).

2. INTERVIEW — `interviewers/`
   Select 2-4 interviewers suited to THIS piece — not the whole roster every time.
   - Building/architecture piece → architect, tactician, operator
   - Customer or field story → customer-advocate, stakes-prober, narrative-prober
   - Opinion / essay → curious-generalist, polish-breaker, skeptic, layperson
   - One deep technical domain → domain-specialist
   - Piece naming a configured partner → add partner-advocate with that partner as parameter
     (optional; dormant otherwise)
   Run them one at a time. ONE question per turn, then wait. Never let them stack questions.
   The full transcript (`drafts/<piece>/transcript.md`) is the raw material. This is where
   slop is prevented — thin answers here produce thin drafts no editor can save.

3. DRAFT — `engine/2-draft.md`
   Write against the transcript as SOURCE and `voice/<active-voice>/voice-guide.md` as
   INSTRUCTION MANUAL. The transcript supplies substance; the voice guide supplies register.
   The machine structures the author's words — it does not invent claims. Missing facts become
   `[GAP: ...]` markers in the non-published editorial block, never improvised prose.
   Output is `drafts/<piece>/draft.html`, a self-contained browser-openable HTML doc
   (`templates/draft-skeleton.html` is the starting shell).

4. COUNCIL — `editors/`, `engine/3-revision-loop.md`
   Run 4-6 editors, always including slop-allergist, voice-guardian, and
   presentation-reviewer. Each returns:
     Score: N/10
     Editorial fixes (machine rewrites these itself)
     Information gaps (route BACK to step 2 — pick the interviewer who fits, ask just that)
   slop-allergist, technical-reviewer, and presentation-reviewer carry HARD caps that hold
   regardless of other merit. Respect the cap.

5. REVISION LOOP
   Apply editorial fixes in place. Route information gaps to a targeted interview. Re-run the
   council. Repeat until aggregate >= 9/10. (Tune the threshold; 9 is a deliberately high bar
   — it is what forces the second round.)

6. FINAL HUMAN PASS — `engine/feedback-intake.md` for outside reviewers
   The author edits and publishes. The machine does not publish. `draft.html` is the handoff
   artifact; the author adapts it to the destination (blog HTML, a social post, a newsletter).
   Edit input from colleagues or the subject funnels into `drafts/<piece>/feedback.md` and gets
   classified and routed — never acted on straight from a comment thread.

7. LESSONS LOOP — `engine/4-lessons-loop.md`
   Diff the machine's last draft against the published version. Extract generalizable rules.
   With the author's explicit approval, append to `voice/<active-voice>/content-lessons.md`.
   Next draft starts smarter.

## Pieces (one folder per content target)
Each piece gets its own folder under `drafts/`, so several can be in flight at once without
colliding:

    drafts/<piece-slug>/
      piece.md        — metadata + status: voice, origin spike, target, council score, stage
      draft.html      — THE output content, self-contained (the council edits this in place)
      transcript.md   — the interview source
      sources.md      — citations, council record, pre-publish checklist, handoff notes
      feedback.md     — outside-reviewer inbox (only once the human pass starts)
      assets/         — diagrams/images (SVGs are also inlined into draft.html)
      meta.json       — the same status, machine-readable

The active piece is orchestration state, named in the state banner alongside the active voice;
you work one piece at a time and each step reads/writes only that folder. The voice a piece
belongs to is recorded in its `piece.md` (not the path), so a piece can change hands.

This repo ships three demo pieces at three stages so the whole chain is traceable:

| Folder | Voice | Stage | Shows |
|---|---|---|---|
| `drafts/idempotency-is-the-whole-job/` | demo-dana | interviewing | a transcript mid-flight, panel not finished, no draft yet |
| `drafts/rehearse-the-rollback/` | demo-dana | council | a draft, a failed first round, hard cap applied, gaps routed back |
| `drafts/the-board-on-the-wall/` | demo-mira | ready-for-human-pass | a polished final, aggregate >= 9, clean checklist |

## Roster (demo suite)
Interviewers (11): architect, tactician, operator, customer-advocate, domain-specialist,
  narrative-prober, stakes-prober, curious-generalist, polish-breaker, layperson, skeptic —
  plus partner-advocate (optional, parameterized).
Editors (11): slop-allergist, voice-guardian, presentation-reviewer (mandatory),
  technical-reviewer, specificity-auditor, structure-editor, cold-reader, closer,
  durability-reader, idea-density, hook-retention — plus partner-brand-steward (optional,
  parameterized).

Every persona here is role-named and generic. A production instance typically adds
celebrity-craft personas (a named narrative host, a named essayist) for the same slots;
they are deliberately absent from a public repo.

## Pruning
Run the full roster for a while. Track which personas actually surface material or catch
problems the others miss. Delete the dead weight — it's `rm interviewers/x.md`, nothing else
to unwind. The roster is meant to shrink.

## Engine files (the connective tissue)
- engine/1-oracle.md         — step 1, finds & ranks ideas (two-stage rank), archives to VAULT.md
- interviewers/*.md          — step 2, extraction
- engine/2-draft.md          — step 3, transcript + voice → drafts/<piece>/draft.html
- engine/3-revision-loop.md  — steps 4-5, council + revise-to-9
- engine/feedback-intake.md  — side-tool for step 6, outside-reviewer input
- engine/4-lessons-loop.md   — step 7, learn from the author's edits
- engine/research-sidecar.md — NOT a step; a side-tool invoked from inside any step
                               ("/research", "dig on that", "verify that"), then returns

## State (all of it in git)
Nothing lives outside the repo. Each in-flight piece persists as a `drafts/<piece>/` folder,
the idea archive is `VAULT.md`, the per-voice rules are `voice/<voice>/content-lessons.md`,
and session pointers are `memory/MEMORY.md`. Work survives between sessions because the
filesystem is the state machine — every memory save is a commit, so the history IS the memory.

## Start here
Read `sandbox/DRY-RUN.md` — one full loop on fictitious data, so you can see every handoff
before wiring real sources. Then run it for real and tune the Oracle first; it's the step most
likely to need your taste applied after you see it work.
