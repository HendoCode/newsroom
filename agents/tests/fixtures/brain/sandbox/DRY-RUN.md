# Dry Run — one full loop on fictitious data

Everything below is INVENTED to show the machine moving end to end. No real accounts, no real
numbers, no real people — same rule as the rest of this repo. Read it top to bottom to feel each
handoff, then run your own with real sources and see where it needs tuning.

The three pieces in `drafts/` are this dry run at three different freeze-frames: one mid-interview,
one mid-council, one finished.

State banner convention (the orchestrator prints this at the top of relevant turns):
`[VOICE: demo-dana · PIECE: northwind-review-queue · STEP 2 · INTERVIEW · persona: customer-advocate · Q2 · your turn]`

════════════════════════════════════════════════════════════════════
STEP 1 — ORACLE  (engine/1-oracle.md — scans 7 days, proposes a ranked list)
════════════════════════════════════════════════════════════════════

Top 3 of 15 spikes (fictitious):

#1  "Confidence-scored extraction cut a client's manual review to near-zero"
    Source: chat thread in #ops-eng + Tuesday's meeting notes
    Maps to: Northwind Logistics (fictional, named, cleared to quote)
    Outcome: manual review dropped from ~40 documents/day to ~5 flagged for humans
    Why #1: strong anecdote + nameable subject + hard before/after metric. Full convergence.
    Convergence: also connects to a stalled case-study outline AND a support ticket asking
                 the same question.

#2  "Why we route tool-calls through a gateway instead of per-agent"
    Source: local architecture notes
    Maps to: none yet
    Outcome: none yet (an orchestration-time claim, unverified)
    Why #2: real technical depth, but no nameable subject and the metric is unconfirmed.

#3  "A client asked for X and it exposed a hole in how we onboard"
    Source: an email thread
    Maps to: a client who has not agreed to be named
    Outcome: none yet
    Why #3: good story, weak on outcome, clearance-sensitive.

→ Author picks #1. Spikes #2-#15 are appended to VAULT.md in entry format. Nothing is lost.
→ Picking #1 scaffolds the piece:
     scripts/new-piece.sh northwind-review-queue demo-dana \
       "Confidence-scored extraction" "Oracle run · Spike #1 (see VAULT.md)"
   piece.md opens with stage=interviewing, voice=demo-dana, Partners: none configured.

════════════════════════════════════════════════════════════════════
STEP 2 — INTERVIEW  (interviewers/ — author talks; ONE question per turn)
════════════════════════════════════════════════════════════════════

Panel selected for this piece (3 of 11, per interviewers/README.md): customer-advocate,
architect, skeptic. No partner is configured, so partner-advocate is never loaded.

[customer-advocate] "Who exactly had this problem? What was their day like before?"
Author (spoken): "It was the ops lead at Northwind — we'd anonymize to 'the ops lead.' Every
morning his team hand-keyed order documents, maybe forty a day, and a wrong field downstream
meant a re-ship. So it was slow AND it was error-prone."

[customer-advocate] "Give me the after in numbers. What changed and by how much?"
Author: "After we put confidence-scored field extraction in front of it, the system auto-cleared
the high-confidence ones and only kicked maybe five a day to a human. So humans went from
touching everything to touching the edge cases."

[architect] "Walk the call path. What decides high-confidence vs. kick-to-human?"
Author: "Each extracted field gets a score. Above a threshold it flows straight through; below,
it's flagged with the low-confidence fields highlighted so the reviewer looks at the field, not
the whole document."

[skeptic] "How do you know the threshold's right? Where would a competitor poke?"
Author: "...honestly the threshold was tuned by eye over the first couple of weeks. I don't have
a clean precision/recall number to point at yet."   ← note this: it becomes a GAP, not a claim.

Done-when checks are met for all three personas, so the panel closes. The transcript is the
evidence pool for everything downstream.

════════════════════════════════════════════════════════════════════
STEP 3 — DRAFT  (engine/2-draft.md — structurer, not inventor)
════════════════════════════════════════════════════════════════════

Draft v1, written from templates/draft-skeleton.html against voice/demo-dana/voice-guide.md
(open on the problem, mechanism before outcome, numbers scoped and dated):

"We worked with the operations lead at a logistics client whose team hand-keyed around forty
order documents a day. A wrong field meant a re-ship. We put confidence-scored field extraction
in front of that process: each field gets a score, high-confidence fields flow straight through,
and only the low-confidence ones — about five a day — reach a human, with the uncertain fields
highlighted. Reviewers now look at a field, not a document."

Editorial block (after </article>, never published):
  [GAP: no precision/recall figure for the threshold — skeptic flagged it, route to skeptic]
  [NOTE: client named as "a logistics client" pending clearance — confirm before human pass]

════════════════════════════════════════════════════════════════════
STEP 4 — COUNCIL  (editors/ — 5 selected; hard caps respected)
════════════════════════════════════════════════════════════════════

Mandatory: slop-allergist, voice-guardian, presentation-reviewer.
By fit:     specificity-auditor, technical-reviewer.
Not loaded: partner-brand-steward (no partner configured for this piece).

voice-guardian:      8/10  — register right for demo-dana: clipped, mechanism-first, no hype.
                             "Reviewers now look at a field, not a document" is a sanctioned
                             contrast, not a tic.
specificity-auditor: 7/10  — specifics: 5 (40 docs/day, ~5 flagged, field-level scores, re-ship
                             consequence, named role). Missing the threshold's accuracy number.
                             Recoverable → interview.
technical-reviewer:  8/10  — call path is correct; per-field scoring and human routing are
                             described precisely enough to reimplement.
presentation-reviewer: 9/10 — clean hierarchy, one h1, table for the before/after. No hard fails.
slop-allergist:      6/10  — HARD CAP. Draft v1 opened "Most teams think automation means
                             removing humans. They're wrong." → presuppose-and-dismantle, the
                             #1 tell. Capped at 6 until it's cut.

Aggregate: 7.6 → below 9. The loop triggers; the cap is respected even though four editors
were happy.

════════════════════════════════════════════════════════════════════
STEP 5 — REVISION LOOP  (engine/3-revision-loop.md)
════════════════════════════════════════════════════════════════════

Editorial fixes (the machine applies these to draft.html in place):
  - CUT the "most teams think… they're wrong" opener. Replace it with the concrete scene: the
    ops lead, forty documents, the re-ship. (clears the slop cap)
  - Scope the numbers: "about five a day" → "five a day on average across the first six weeks
    of March." (specificity-auditor)

Information gap (routes BACK to Step 2 → skeptic, one question only):
  Q: "Do you have ANY defensible accuracy figure, even rough? Or should the piece say plainly
      that the threshold was hand-tuned early on?"
  Author (spoken): "Be honest — say it was tuned by hand over the first two weeks and we're
  instrumenting real precision/recall now. That's truer and it's fine."

The GAP closes as an honest caveat, not a number. Draft v2 re-scored:

slop-allergist 9 · voice-guardian 9 · specificity-auditor 9 · technical-reviewer 9 ·
presentation-reviewer 9 → aggregate 9.0. Clears the bar.

Note what happened: the honest caveat scored HIGHER than a vague confident claim would have.
That is the voice guide working, not the editors being generous.

Round record (both rounds, every score, every fix) is written to
drafts/northwind-review-queue/sources.md. piece.md moves to stage=ready-for-human-pass with
open GAPs: 1 (the clearance).

════════════════════════════════════════════════════════════════════
STEP 6 — HUMAN PASS  (the author edits and publishes; the machine never does)
════════════════════════════════════════════════════════════════════

Before sharing with anyone outside the team, engine/feedback-intake.md's two-versions guardrail
applies: piece.md still lists an open clearance, so no external share until it closes. Internal
reviewers see the editorial block; external ones never do.

The author changes one thing before posting: swaps "confidence-scored extraction" for
"confidence-scored field extraction" throughout — precision matters to her readers.

Outside input that arrives during this pass (a colleague's note, the client's correction) goes
into feedback.md, gets classified — editorial fix / information gap / clearance / out-of-scope —
and is routed back to Step 4 or Step 2. Nothing is applied straight from a comment thread.

════════════════════════════════════════════════════════════════════
STEP 7 — LESSONS LOOP  (engine/4-lessons-loop.md — propose, then gate)
════════════════════════════════════════════════════════════════════

Diff found: the author added "field" to "extraction" every time it appeared.
Proposed lesson: "Say 'field extraction,' not just 'extraction' — the reader is technical and
the precision signals you know the difference."
Gate: "Add this to voice/demo-dana/content-lessons.md?" → author: yes → appended and committed.

The lesson is per-voice: demo-dana's edits teach demo-dana's file, never demo-mira's.
Next draft starts knowing this. The machine got smarter by one rule.
