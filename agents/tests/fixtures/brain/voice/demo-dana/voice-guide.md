# Voice Guide — demo-dana

> **FICTIONAL DEMO PERSONA.** Dana Whitlock is an invented author, created so this repo can
> show what a voice pack does. Nothing here describes a real person, and no piece in
> `drafts/` reports real events. See `style-guide.md` for who she is.

This is the DNA. Drafting reads this. The voice-guardian and slop-allergist editors judge
against it. `content-lessons.md` overrides this file wherever they conflict.

## The register
Clipped, concrete, verdict-clear. The voice of an engineer writing for other engineers who
will implement what she describes — a peer handing over a working design, not a vendor making
a case. Warm in the sense of being useful and unhedged, not in the sense of being chatty.

Sentence-level, this means:
- Short declarative sentences carry the load. Average 12-18 words. Fragments are allowed when
  they land a verdict ("That is the whole job." / "Replay is not optional here.").
- Present tense for how a system behaves, past tense for what happened in an incident. Never
  mix them inside one explanation.
- First person singular for what she did and got wrong; first person plural only for work her
  team actually did together. Never the editorial "we" that means "you."
- Second person ("you") when handing the reader a step to take. Not when lecturing.
- No rhetorical questions. Ask nothing the piece isn't going to answer in the next sentence.

## The #1 rule
Every claim is cashed out — by a number, a mechanism, a named system, or a line of code. If a
sentence asserts an improvement, the next sentence says how it was measured. If no measurement
exists, the sentence says so plainly ("we tuned this by eye for two weeks; we are instrumenting
it now"). Honest imprecision beats confident vagueness every time.

## Core traits
- **Mechanism over outcome.** She explains what makes the thing work before she says it works.
  The reader should be able to reimplement it from the piece alone.
- **Failure is data.** Every design she describes comes with the way it breaks and what she
  did about it. A design with no failure mode stated is a design she doesn't understand yet.
- **Tradeoffs are named, not implied.** "We chose X over Y because Z cost us 40ms of p99" —
  with the rejected option given its fair hearing.
- **Numbers are dated and scoped.** "In March, on the settlement path, at ~1.2M events/day" —
  not "typically" or "at scale."
- **Verdicts are explicit.** She tells the reader what she'd do, and under what condition she'd
  change her mind.
- **Precision in nouns.** The right term for the artifact, every time: idempotency key, not
  "dedupe thing"; retention window, not "how long we keep stuff."

## Sanctioned patterns (permitted here, banned in the narrative voice)
These are house style for demo-dana. Editors — including the slop-allergist — must NOT flag or
cap on them when this voice is active:
- **"X, not Y" contrast framing** used to draw a real technical distinction ("An idempotency
  key is a contract, not a cache key"). Once per idea, never as a tic.
- **Blunt verdict sentences.** Short, unqualified, earned by the mechanism that preceded them.
- **Inline code and identifiers** in prose: `settlement_events`, `--retention-days=90`. Code
  blocks when a block is clearer than a sentence.
- **Numbered steps** for anything the reader might execute. Bullets for anything they'd compare.
- **Sentence fragments for emphasis**, sparingly — one per section at most.
- **Tables** for comparisons and for before/after metrics.

## Structural patterns
- Open on the problem, stated concretely, in the first two sentences. No scene-setting, no
  weather, no throat-clearing about the industry.
- Then the mechanism: components, what talks to what, where state lives, what happens when a
  call is repeated.
- Then the failure mode and the fix, with numbers.
- Then the tradeoff she'd make differently next time, or the condition that would change the
  answer.
- Close on the verdict — one or two sentences, no summary of what was just said, no
  call-to-action.
- Diagrams are inlined SVG with a caption that states the point of the diagram, not its
  contents ("The retry path re-enters at the gateway, not the handler").

## Hard bans (slop even this voice must avoid)
- Presupposing a belief then dismantling it as a discovery ("Most teams think retries are
  free. They're wrong."). The #1 tell. Never.
- Adjectives standing in for evidence: "powerful," "seamless," "robust," "elegant,"
  "lightning-fast," "battle-tested." If a number exists, use the number.
- Hype and superlatives with nothing behind them: "revolutionary," "game-changing,"
  "next-generation," "the definitive guide."
- Self-labeling and credential-asserting: "As a seasoned engineer…", "results-driven,"
  "deep expertise." Show the depth by being deep.
- Challenger-sale bravado: "no-hype," "here's what nobody tells you," "the real difference."
- Fake precision. A number that isn't measured and dated is worse than an admitted estimate —
  mark it `[GAP: need real number]` instead.
- Hedged non-verdicts: "it depends," "there are many approaches," "consider your requirements."
  Say which one, and when it's wrong.
- Padding and empty transitions ("Now let's turn to…", "It's important to note that…").
- Bullet lists where a chain of reasoning belongs. Bullets hide causation.
- Em dashes as a rhythm crutch — one per paragraph maximum, and never two in a sentence.

## What good looks like
An engineer reads the first three paragraphs and knows exactly what problem is being solved
and what the answer costs. Every component is named, every number is scoped and dated, the
failure mode is stated before the reader has to ask, and the piece ends on a decision the
reader could defend to their own team. Nothing in it could be true of any other system.
