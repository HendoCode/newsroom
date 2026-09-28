# Templates — starting shells, not branding

`templates/` holds the neutral shells a step starts from. Nothing here injects a brand: this
repo renders no logos and carries no brand tokens. A production instance may add a branded
render shell of its own; the demo suite deliberately does not, so every artifact here is
readable as plain content.

## `draft-skeleton.html`
The starting shell for `drafts/<piece>/draft.html` (Step 3). It exists so the council is not
reviewing three different documents' typography while trying to review one argument.

Contract it must keep (see `engine/2-draft.md` for why each rule exists):
- Self-contained and browser-openable: one file, no external fetches, no build step. CSS lives
  in a single `<style>` block; diagrams are inlined `<svg>`, not linked assets.
- Semantic markup only — `<article>`, `<h1>`–`<h3>`, `<p>`, `<figure>`, `<table>`. Exactly one
  `<h1>`, no skipped heading levels. `editors/presentation-reviewer.md` caps a draft at 6 for
  breaking that.
- System font stacks, no webfont imports. The artifact must read identically offline.
- An `<section class="editorial" aria-label="Editorial annotations, not for publication">`
  block at the end, after `</article>`, holding every `[GAP: ...]` and `[NOTE: ...]`. That
  literal tag-and-class string is a parser contract: the revision loop, the external-share
  strip in `engine/feedback-intake.md`, and the human pass all key off it. Never paraphrase it,
  never move it inside the article, and never publish it.
- No placeholder copy. If a fact is missing, it is a `[GAP: ...]` in the editorial block — not
  lorem ipsum and not an invented number.

## How a piece uses it
`scripts/new-piece.sh <slug> <voice>` scaffolds `drafts/<slug>/` with `piece.md`, an empty
`transcript.md`, an empty `sources.md`, and `meta.json`. The skeleton is copied in at Step 3,
once a transcript exists to draft from — not before, so an empty `draft.html` never looks like
progress.
