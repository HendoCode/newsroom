# Engine Step 7 — The Lessons Loop

(Step 6 is the human pass + publish. This runs after the author publishes.)

You make the machine smarter after every piece.

## Process
1. Take two versions: the machine's final draft (drafts/<piece>/draft.html, post-council,
   pre-human) and the author's actually-published version.
2. Diff them. For each meaningful change the author made:
     - What did they change?
     - Why, most likely? (a word choice, a cut, a reordering, a softened claim)
     - Is there a GENERALIZABLE rule, or was it one-off? Only keep the generalizable.
3. Phrase each keeper as a short rule, the way the seed lessons are phrased.

## Approval gate (required)
Present the candidate lessons to the author: "Add these to content-lessons.md?"
Only on an explicit yes do you append them to the voice pack's lessons file.
Lessons override the style guide when they conflict, so they carry weight — don't
add anything the author didn't confirm.

## Output
- The proposed lessons (each: what changed / the rule).
- On approval: append to voice/<active-voice>/content-lessons.md and commit it.
  Lessons are per-voice — one voice's edits teach that voice's file, never another's.
