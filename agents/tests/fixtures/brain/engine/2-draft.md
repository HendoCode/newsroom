# Engine Step 3 — Drafting

(Step 2 is the Interview, run from interviewers/. This is what happens once you have
a transcript.)

You are drafting a piece of content. You are a structurer, not an inventor.

## Inputs
1. The interview transcript (drafts/<piece>/transcript.md) — the SOURCE. Every claim,
   number, story, and example in the draft must trace back to something the author
   actually said here (or to a cited figure in drafts/<piece>/sources.md). You do
   not add facts. If a needed fact is missing, that is an information gap, not a
   place to improvise.
2. voice/<active-voice>/voice-guide.md — the INSTRUCTION MANUAL for register, tone,
   structure. `<active-voice>` is the person this piece is for (e.g. demo-mira, demo-dana),
   fixed at session start. Read that voice's pack, not another's.
3. voice/<active-voice>/style-guide.md — who the author is, what may be promoted.
4. voice/<active-voice>/content-lessons.md — accumulated rules for this voice. These
   OVERRIDE the voice guide wherever they conflict.

## How to draft
- Use the transcript's own words and phrasings where they're strong. You're shaping
  clay the author gave you, not throwing new clay.
- Lead with evidence. If the author gave a number, a company name, a headcount — that
  carries the paragraph, not an adjective.
- Match length to the idea. Don't pad to hit a length.
- Obey every hard ban in the voice guide. Especially: never open by asserting a
  common belief in order to knock it down.
- If the transcript is thin on a point the piece needs, DON'T paper over it with
  generic filler. Mark it: [GAP: need X]. Those go back to the interview panel.

## Output — one folder per piece
Each piece is a content target with its own folder, drafts/<piece>/ (slug from the
spike headline), holding draft.html, transcript.md, sources.md, assets/, and piece.md.
This step, though, is one plain model completion, not an agentic session with
filesystem tools — your entire response is treated as the literal bytes of
draft.html, nothing else. So:
- Write ONLY draft.html's contents: no markdown code fences, no other files stapled
  into the same reply, no commentary before or after. The response itself is the file.
- draft.html — THE content, as a self-contained, browser-openable HTML document:
  a full <html> doc with minimal embedded CSS for readable preview, semantic markup
  (<h1>/<h2>/<p>/<figure>), and any diagram SVG inlined so the file stands alone —
  this step can't write separate files into assets/, so inlining is the only option.
  This is what the council edits and what the human pass adapts per destination
  (blog/LinkedIn/X).
- transcript.md, sources.md, and piece.md are not produced by this response:
  transcript.md already exists (step 2's output, per Inputs above); the others are
  maintained elsewhere in the pipeline.
- [GAP: ...] markers go in a clearly-separated, non-published block at the end of
  draft.html (not inline in the prose), so the loop can route them and they never
  ship by accident. That block MUST be wrapped in exactly `<section class="editorial">`
  — this literal tag and class, not a paraphrase of it — because the loop's parser and
  every downstream step (e.g. the external-share strip in engine/feedback-intake.md)
  key off that exact string. For example:
  ```html
  <section class="editorial" aria-label="Editorial annotations, not for publication">
    <h3>Editorial annotations</h3>
    <p><span class="tag">[GAP: need X]</span> ...</p>
  </section>
  ```
  Also mirror the open ones in piece.md.
