# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: build, test, release, architecture, and sharp-edge notes that should travel with the code.

- Add durable project-specific notes here as they are discovered through real work.

## Sharp edges

- **A missing `drafts/<slug>/transcript.md` used to leak a raw `FileNotFoundError` straight
  through as a job's failure message, from three separate call sites, and it looked
  unrecoverable but wasn't** (`cmw-incorporate-missing-transcript` fixed incorporate;
  `cmw-unguarded-transcript-reads` fixed draft/council after that PR's own "not reachable in
  practice" judgment on those two turned out wrong — Hendo hit the draft one live within the same
  day, pressing "enough input" on a piece with no transcript). `app/review/rewrite.py`'s
  `rewrite_revision`, `app/orchestration/draft_step.py`'s `DraftStep.run`, and
  `app/orchestration/council_step.py`'s `CouncilStep.run` all read the transcript via
  `PromptAssembler.transcript_block` unguarded (unlike `sources_block`, already wrapped in
  `except OSError: pass` since sources.md is genuinely optional) — a piece that skipped the
  interview stage (e.g. seeded directly into `review`/`council` with hand-written draft prose, as
  both a live deployed piece and Hendo's local repro were) has no transcript.md, and the read
  raised the bare `"[Errno 2] No such file or directory: ..."` straight through as the job's
  error message. All three now raise a `PermanentStepError` naming the piece/file and telling a
  human what to do, in one consistent wording (`draft_step._require_transcript`, shared by
  `council_step.py`; `rewrite.py` keeps its own copy since it lives in a different package). The
  transcript is genuinely required in all three — unlike sources.md, it's what each step traces
  new/drafted content back to, so silently proceeding without it was never the right fix; for
  draft specifically it's more fundamental still, since a draft has no source material *at all*
  without one. **Recoverability differs by step, and it's worth knowing which**: incorporate's
  failure flags back to `review` (round preserved) and needs a human to explicitly call
  `route_to_interview` before a real interview can run; draft's failure (`_failure_stage`,
  `app/orchestration/machine.py`) always flags back to `interviewing` automatically, and
  council's does too whenever it's a first-pass council (no review round yet — the only way this
  defect is actually reachable, since a real draft→council chain can no longer produce a
  transcript-less piece once draft has this guard) — so for draft/council, pressing "enough
  input" again after a real interview *is* the entire recovery path, no manual re-routing step
  needed. In every case `retryable=False` is correct (retrying the identical job changes nothing)
  and no piece is ever wedged.

- **Fixed (`cmw-phantom-edits-from-doc-roundtrip`): a review Doc "not touched in any way" was
  reporting phantom inline edits — one per heading, plus one on external rounds — because Google's
  own HTML-to-Docs conversion adds markup our diff read as reviewer action.** Two distinct,
  pre-existing artefacts, both confirmed live (real `createDocFromHTML` mint + real `text/html`
  export, real edits via the live Docs API, throwaway Docs deleted after): (1) every `<h1>`-`<h6>`
  comes back with its *entire* text wrapped in a `font-weight:700` span Google adds unconditionally
  — `app/review/structure.py`'s `Block.emphasis` now suppresses `bold` for a heading only when it
  covers 100% of that heading's text (Google's own shape); a partial bold, or any italic/underline
  at any coverage, is never touched — the anti-over-normalization proof this ticket most cared
  about. (2) the external-round DRAFT banner is authored as a non-block `<div>` (never extracted as
  a `Block` on our own reconstructed side) but Drive's conversion turns it into a real `<p>` on
  export — `app/review/collect.py`'s `gather_raw_items` now drops any block matching
  `app.review.mint.DRAFT_BANNER_TEXT` from both sides before diffing (`diff_edits` itself, used
  directly by its own tests, stays purely mechanical — the filtering happens one layer up, in
  `gather_raw_items`, via the new `diff_blocks(original_blocks, current_blocks)` split out of
  `diff_edits`). Regression fixtures in `agents/tests/fixtures/review/` are REAL captured Docs
  exports (not hand-written HTML) — see `agents/tests/test_review_google_docs_roundtrip.py`'s
  module docstring for how they were produced. **Any future change to `app/review/structure.py` or
  `app/review/mint.py`'s banner/editorial handling should be verified the same way — round-trip a
  real throwaway Doc — before trusting a green test suite**, since all three known defects in this
  exact area (this one, the editorial-diff asymmetry, and the original heading/emphasis structural
  intake work) were invisible to hand-written fixtures and only surfaced against a real export.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
