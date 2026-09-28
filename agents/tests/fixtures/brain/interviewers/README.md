# Interviewers — the extraction panel (Step 2)

These personas run BEFORE a draft exists. Each one pulls raw material out of the author;
none of them writes. They are voice-neutral by design — an interviewer sounds like
itself, never like the active voice pack.

## The contract every file here follows
Each persona file is read verbatim as an LLM system-prompt block (there is no rendering
layer; the prose IS the behavior) and carries the same four sections:

1. A one-line statement of what this interviewer is for and when to pick it.
2. `## Your obsessions` — what it refuses to let slide.
3. `## How you ask` — the question shapes, in quotes, so the register is unambiguous.
4. `## You are done when` — the completion test. This is what makes a panel stoppable:
   the orchestrator can say "architect is done, moving to skeptic" because a written
   condition was met, not because the model felt like moving on.

## Selection (2-4 per piece, not the whole roster)
- Building / architecture piece → `architect`, `tactician`, `operator`
- Customer or field story → `customer-advocate`, `stakes-prober`, `narrative-prober`
- Opinion / brand post → `curious-generalist`, `polish-breaker`, `skeptic`, `layperson`
- Piece naming a configured partner → add `partner-advocate` with that partner as
  parameter (it reads `partners/<partner>.md`). Optional and dormant unless a partner
  is configured — see `partners/README.md`.

Run them one at a time. ONE question per turn, then wait. Never stack questions.

## The discipline that makes this work
Thin answers here produce thin drafts no editor can save. The panel is where slop is
prevented, so an interviewer's job is to refuse a vague answer and ask again — not to
be agreeable. `## You are done when` is a floor, not a ceiling.

## Pruning
Run the full roster for a while, then delete the personas that never surface material the
others miss. Removing one is `rm interviewers/<name>.md`; nothing else needs unwinding.
