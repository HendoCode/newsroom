# Editors — the council (Steps 4-5)

These personas run AFTER a draft exists. Each one scores the draft 1-10 on its own axis and
splits its findings into two buckets, which is what makes the revision loop mechanical
instead of vibes:

- **Editorial fixes** — the machine can rewrite these itself (wording, structure, tone).
- **Information gaps** — only the author can fill these. They route BACK to Step 2, to the
  interviewer who fits the gap, and are asked as a single question.

Read `engine/3-revision-loop.md` for the loop and the aggregation rule. Read `PANEL.md` for
where the council sits in the whole machine.

## The default council (quality-only)
Mandatory on every piece — never skipped:

| Editor | Axis | Hard cap? |
|---|---|---|
| `slop-allergist` | AI tells and inauthentic moves | yes — one unflagged tell caps at 6 |
| `voice-guardian` | fidelity to the active voice pack | no |
| `presentation-reviewer` | formatting and document hygiene | yes — one hard fail caps at 6 |

Then 2-4 more by fit (4-6 total is usually right):

| Piece type | Add |
|---|---|
| Technical / architecture | `technical-reviewer`, `specificity-auditor` |
| Customer or field story | `specificity-auditor`, `cold-reader`, `closer` |
| Opinion / essay / argument | `durability-reader`, `idea-density`, `hook-retention`, `closer` |
| Anything a stranger will land on from a link | `cold-reader` |
| Anything whose skeleton might be wrong | `structure-editor` |

`technical-reviewer` also carries a hard cap: a technical error is not optional to fix.

## Optional: the partner seam (dormant unless configured)
`partner-brand-steward` joins the council ONLY when a partner is configured for the piece —
`partners/<partner>.md` exists and the author named it. It fact-checks and brand-checks
partner content already in the draft; it never pushes product in. With no partner
configured, this repo's council is quality-editors-only. That is the default path.
See `partners/README.md`.

## Scoring discipline
- A score is always accompanied by the reason for the number. No bare digits.
- Hard caps are respected even when every other editor loved the draft. The cap is the
  point: it is how a single unearned claim or a broken heading hierarchy keeps a piece
  below the bar.
- The loop applies editorial fixes directly to `drafts/<piece>/draft.html` (edit the HTML,
  don't rebuild it), routes information gaps back to the interview, then re-runs the council.
  Aggregate >= 9/10 clears the piece to the human pass. The council never publishes.
- Each round's record — every editor's score and the fixes applied — is written to
  `drafts/<piece>/sources.md`, so a reader can trace how a draft got to its final number.
  `drafts/rehearse-the-rollback/` is a worked example of a round that failed and looped.

## The file contract
Every editor file here is read verbatim as an LLM system-prompt block: there is no rendering
layer, so the prose IS the behavior. Each file carries `## You judge` (the rubric),
`## You flag` (the findings it must not miss), and `## Output` (the exact response shape,
starting with `Score: N/10`). Keep those three sections when you edit one; the loop parses
the output shape and the author reads the rubric.

## Pruning
Add an editor when a real draft ships a defect nobody caught; delete one when it has nothing
to say that another already says. Removing one is `rm editors/<name>.md` — the loop selects
by filename, so nothing else needs unwinding. Mandatory three aside, the roster is meant to
stay small enough that selection by fit is a real choice.
