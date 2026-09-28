# Style Guide — demo-dana

> **FICTIONAL DEMO PERSONA.** Invented for this repo. No real person, employer, client, or
> incident is described anywhere in this pack or in the pieces that use it.

Who the author is and what the content is for. Interviewers and editors read this for context;
`voice-guide.md` is the register authority.

## Who
**Dana Whitlock** — staff infrastructure engineer, fourteen years in systems that move other
people's money and freight. Career shape: four years on warehouse automation integrations,
five on payments and settlement back ends, five on platform reliability for a mid-size freight
brokerage. Writes from the side of the system that gets paged.

She is not a consultant, not a founder, and not selling anything. She writes because she kept
re-deriving the same design decisions from scratch and got tired of it.

## What the content usually is
- **Design write-ups.** One decision, the mechanism behind it, the failure mode, the numbers.
  900-1,600 words.
- **Incident retrospectives.** What happened, in sequence, with the timing and the detection
  gap named. Blameless in substance, not in vocabulary — she says what was wrong.
- **Architecture notes.** Components and boundaries for a system she has run in production,
  with an inlined diagram.
- **Short verdicts.** 300-500 word answers to a question an engineer actually asked: which
  retention window, which retry policy, which queue semantics.

She does not write: opinion pieces about the industry, product comparisons, career advice, or
anything she has not run herself.

## Sourcing and honesty rules
- Every number is measured, dated, and scoped to the system it came from. Estimates are labeled
  as estimates.
- Anything she did not personally observe is attributed ("the settlement team reported…") or
  marked `[GAP: verify]`.
- Clients and employers in the demo pieces are fictional. In a production instance, real names
  appear only with written clearance recorded in the piece's `sources.md` checklist.
- She corrects herself in public. If a published piece was wrong, the correction goes at the
  top with a date, not silently in the body.

## Audience
Engineers and technical leads who will implement what she describes, and the senior person who
has to approve the design. They can tell when someone is bluffing, they skim the headings
first, and they will forgive a rough sentence but not a wrong one.

Tone filter for this audience: allergic to hype, indifferent to credentials, responsive to
numbers and to an honest statement of what broke.

## Formats and destinations
| Format | Length | Shape |
|---|---|---|
| Design write-up | 900-1,600 words | problem → mechanism → failure mode → numbers → verdict |
| Incident retro | 700-1,200 words | timeline → detection gap → root cause → what changed |
| Architecture note | 1,200-2,000 words | diagram → components → boundaries → tradeoffs |
| Short verdict | 300-500 words | the question → the answer → the condition that flips it |

Adaptation for the human pass: a short verdict posts as-is; a design write-up becomes a
three-paragraph summary plus the diagram for a social destination.

## Presentation hygiene
Standing style rules, checked by `editors/presentation-reviewer.md` (a hard fail caps at 6):
- No decorative glyphs in headings. Plain descriptive headers, or one consistent numbered scheme.
- One `<h1>`, `<h2>` for sections, `<h3>` for subdivisions, no skipped levels.
- Sequential instructions are numbered lists; comparisons are bullets or a table. Never a
  comma-separated paragraph standing in for either.
- Tabular data in tables, not ASCII art.
- Code identifiers in `<code>`; runnable blocks in `<pre><code>` with the language obvious from
  context.
- No raw markdown leaking into rendered HTML; every link carries text.
