# Dry Run — one full loop on fictitious data

Everything below is INVENTED to show the machine moving end-to-end. No real accounts,
no real numbers. Read it top to bottom to feel each handoff. Then run your own with
real sources and see where it needs tuning.

════════════════════════════════════════════════════════════════════
STEP 1 — ORACLE  (scans 7 days, proposes ranked list to Notion)
════════════════════════════════════════════════════════════════════

Top 3 of 15 spikes (fictitious):

#1  "Confidence-scored extraction cut a partner's manual review to near-zero"
    Source: Slack #partner-eng thread + Tuesday meeting notes
    Customer/partner: Northwind Logistics (named)
    Outcome: manual review dropped from ~40 docs/day to ~5 flagged for humans
    Why #1: strong anecdote + named partner + hard before/after metric. Full convergence.
    Convergence: also connects to the draft case-study template AND a stalled pipeline entry.

#2  "Why we route tool-calls through a gateway instead of per-agent"
    Source: local architecture notes
    Customer/partner: none yet
    Outcome: none yet (has an orchestration-time claim but unverified)
    Why #2: strong technical depth, but no customer hook and the metric is unconfirmed.

#3  "A partner asked for X and it revealed a gap in how we onboard"
    Source: Gmail thread
    Customer/partner: partner named but sensitive
    Outcome: none yet
    Why #3: good story, weak on outcome, promotion-sensitive.

→ Author picks #1. Spikes #2–#15 auto-saved to the Vault. Nothing lost.

════════════════════════════════════════════════════════════════════
STEP 2 — INTERVIEW  (author talks, transcribed; one Q per turn)
════════════════════════════════════════════════════════════════════

[customer.md] "Who exactly had this problem? What was their day like before?"
Author (spoken): "It was the ops lead at Northwind — call him the ops lead, we'd
anonymize. Every morning his team hand-keyed order docs, maybe forty a day, and a
wrong field downstream meant a re-ship. So it was slow AND it was error-prone."

[customer.md] "Give me the after in numbers. What changed and by how much?"
Author: "After we put confidence-scored extraction in front of it, the system
auto-cleared the high-confidence ones and only kicked maybe five a day to a human.
So humans went from touching everything to touching the edge cases."

[architect.md] "Walk the call path. What decides high-confidence vs. kick-to-human?"
Author: "Each extracted field gets a score. Above a threshold it flows straight
through; below, it's flagged with the low-confidence fields highlighted so the
reviewer looks at the field, not the whole doc."

[skeptic.md] "How do you know the threshold's right? Where would a competitor poke?"
Author: "...honestly the threshold was tuned by eye over the first couple weeks.
I don't have a clean precision/recall number to point at yet."   ← note this

════════════════════════════════════════════════════════════════════
STEP 3 — DRAFT  (transcript + voice files; structurer not inventor)
════════════════════════════════════════════════════════════════════

Draft v1 (excerpt):
"We worked with the operations lead at a logistics partner whose team hand-keyed
around forty order documents a day. A wrong field meant a re-ship. We put
confidence-scored extraction in front of the process: each field gets a score,
high-confidence fields flow straight through, and only the low-confidence ones —
about five a day — reach a human, with the uncertain fields highlighted. Reviewers
now look at a field, not a document."
[GAP: no precision/recall figure for the threshold — skeptic flagged it]

════════════════════════════════════════════════════════════════════
STEP 4 — COUNCIL  (editors score; hard caps respected)
════════════════════════════════════════════════════════════════════

voice-guardian:      8/10  — register is right, first-person plural, evidence-led. Good.
specificity-auditor: 7/10  — specifics:5 (40 docs, 5 flagged, named role). Missing the
                             threshold's actual accuracy number. Recoverable → interview.
slop-allergist:      6/10  — HARD CAP. Draft v1 originally opened "Most teams think
                             automation means removing humans. They're wrong." →
                             presuppose-then-dismantle tell. Capped at 6 until cut.
technical-reviewer:  8/10  — call path is correct and precise. Fine.
closer:              6/10  — ends on "Reviewers now look at a field, not a document" —
                             fine line but the piece just stops. Dribbles.

Aggregate: 7.0 → below 9. Loop triggers.

════════════════════════════════════════════════════════════════════
STEP 5 — REVISION LOOP
════════════════════════════════════════════════════════════════════

Editorial fixes (machine does these itself):
  - CUT the "most teams think... they're wrong" opener. Replace with the concrete
    scene: the ops lead, forty docs, the re-ship. (clears slop-allergist cap)
  - Give the piece a real landing, not a stop. (closer)

Information gap (routes BACK to interview → skeptic/customer):
  Q: "Do you have ANY defensible accuracy figure, even rough? Or should the piece
      be honest that the threshold was hand-tuned early on?"
  Author (spoken): "Be honest — say it was tuned by hand over the first two weeks
      and we're instrumenting real precision/recall now. That's truer and it's fine."

Draft v2 re-scored → aggregate 9.2. Passes. Note the honest caveat scored HIGHER
than a vague confident claim would have — that's the voice guide working.

════════════════════════════════════════════════════════════════════
STEP 6 — HUMAN PASS  (author edits, publishes)
════════════════════════════════════════════════════════════════════

Author changes one thing before posting: swaps "confidence-scored extraction" for
"confidence-scored field extraction" throughout — precision matters to his readers.

════════════════════════════════════════════════════════════════════
STEP 7 — LESSONS LOOP  (diff final vs. published; propose; gate)
════════════════════════════════════════════════════════════════════

Diff found: author added "field" to "extraction" every time.
Proposed lesson: "Say 'field extraction,' not just 'extraction' — the reader is
technical and the precision signals you know the difference."
Gate: "Add this to content-lessons.md?"  → author: yes → appended to Notion.

Next draft starts knowing this. The machine got smarter by one rule.
