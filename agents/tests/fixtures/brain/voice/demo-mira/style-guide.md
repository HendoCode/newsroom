# Style Guide — demo-mira

> **FICTIONAL DEMO PERSONA.** Invented for this repo. No real person, place, employer, or event
> is described anywhere in this pack or in the pieces that use it.

Who the author is and what the content is for. Interviewers and editors read this for context;
`voice-guide.md` is the register authority.

## Who
**Mira Calder** — narrative nonfiction writer. Ten years inside municipal transit operations,
the last four as a duty superintendent's clerk and then a scheduler, before she started writing
full time about the work she used to do. She is not an engineer and does not write as one; she
writes about the place where a system meets the people who keep it running.

Her standing subjects: tacit knowledge, handovers, cutover weeks, the objects a workplace keeps
long after their official purpose ends, and what an operation loses when it becomes legible.

## What the content usually is
- **Field-notes essays.** 1,400-2,200 words. One place, one turn, one thing understood late.
- **Cutover stories.** What the eleven days felt like when the new system was correct and the
  old one was legible.
- **Object pieces.** 800-1,200 words built around a single artifact — a board, a logbook, a
  brass rail, a laminated card — and the judgment it encoded.
- **Profile-adjacent pieces.** A person and their work, told with their consent and their
  review of the quotes.

She does not write: product reviews, how-to guides, industry commentary, or anything sourced
only from documents. If nobody will talk to her, there is no piece.

## Sourcing and consent rules (harder than most voices, on purpose)
- Every scene is one she witnessed or one a named person described to her on the record.
  Attribution lives in `sources.md`, not in the piece.
- Quotes are verbatim or they are marked `[GAP: confirm quote]`. No composites, no
  reconstruction, no "the kind of thing he would have said."
- Anyone quoted in a piece about a failure has seen the relevant paragraph before publication,
  and their clearance is recorded in the piece's `sources.md` checklist. Silence is not consent.
- Anonymity is offered freely and granted without argument; an anonymized person keeps their
  specific detail ("the scheduler on the 06:40"), because vagueness is what makes anonymity
  read as invention.
- Numbers that come from a system are checked against a record. Numbers that come from memory
  are labeled as memory ("about forty a day, she says").

## Audience
General readers who like nonfiction about work, plus the people who do this work and will know
immediately if it's fake. The second group is the real test: they read for the details nobody
outside would think to include.

Tone filter for this audience: allergic to sentimentality, indifferent to credentials, alert to
any sentence that uses a person as an illustration.

## Formats and destinations
| Format | Length | Shape |
|---|---|---|
| Field-notes essay | 1,400-2,200 words | scene → person → turn → what it cost → quiet verdict |
| Cutover story | 1,600-2,400 words | before → the week → the eleven days → the object that stayed |
| Object piece | 800-1,200 words | the object → its conventions → who could move it → what replaced it |
| Reported note | 400-700 words | one moment, one quote, one observation |

Adaptation for the human pass: an essay becomes two excerpts for a social destination — the
opening scene and the closing line — with the through-line stated in one sentence between them.
Never a bullet summary; it would break the voice.

## Presentation hygiene
Standing style rules, checked by `editors/presentation-reviewer.md` (a hard fail caps at 6):
- No decorative glyphs in headings; this voice uses few headings at all, and they are plain.
- One `<h1>`, `<h2>` for the rare section break, no skipped levels, no numbered sections.
- No bullets, no numbered lists, no tables, no inline code. Paragraphs only.
- Block quotes only for a person's speech, and only when the sentence earns its own paragraph.
- No raw markdown leaking into rendered HTML; scene breaks are a plain `<hr>`, never `* * *`.
