# Masthead (public demo instance)

A **git-native voice, persona, and engine store** for Masthead — the writing system
that turns one author's spoken material into a publishable piece through a disciplined pipeline:
oracle → interview → draft → council → human pass → lessons.

This repository *is* the machine's brain. There is no database and no rendering layer. Personas,
engine steps, voice packs, and the pieces in flight are plain markdown and HTML files in git, and
the files' prose **is** the behavior: an interviewer's `.md` is read verbatim as an LLM system
prompt, so editing a sentence changes what a live interviewer asks and when it decides it is done.
Git history is the memory — every save is a commit.

**This is the public demo instance.** It ships a neutral, entirely fictional demo suite so the
architecture can be read end to end. The production brain that a real author writes from is a
private repository with the same structure and real voice packs; it is never published, and
nothing from it is copied here.

---

## How it is consumed

The brain has two consumers, and every change here must keep both working:

1. **The `Newsroom`** — clones this repo read-write and bind-mounts it into its
   `agents` container at **`/brain`**. It globs the directories (`voice/*`, `interviewers/*`,
   `editors/*`, `drafts/*`) and reads the raw markdown straight into prompts. There is no
   template engine between the file and the model, which is why the writing in these files is
   load-bearing rather than decorative.
2. **A GitAgent-style runtime** — `agent.yaml` (model, tools, limits), `SOUL.md` (the
   orchestrator persona), `RULES.md` (safety), `memory/MEMORY.md` (session pointers),
   `skills/*/SKILL.md` (trigger phrases + instructions), `workflows/*.yaml` (multi-step pipelines
   with `__approval_gate__` steps), and `gitagent.sh` as the launcher.

You can also drive it with no runtime at all: paste `PROJECT-INSTRUCTIONS.md` into an assistant's
custom-instructions field, point it at a clone of this repo, and run the steps by hand. That is
how the machine was built before it was automated.

```
./gitagent.sh                        # provider-key detection, then launches the orchestrator
./scripts/validate-gitagent.sh       # frontmatter, referenced files, launcher behavior
./scripts/verify-public-clean.sh     # the publication gate for a public brain (see below)
./scripts/new-piece.sh <slug> <voice>   # scaffold drafts/<slug>/ the way engine/1-oracle.md describes
```

---

## The pipeline, and where each part lives

| Step | What happens | Files |
|---|---|---|
| 1 · Oracle | Rank raw material into content spikes; archive the rest | `engine/1-oracle.md`, `VAULT.md`, `skills/oracle/`, `skills/vault-ingest/` |
| 2 · Interview | 2-4 personas extract material, one question per turn | `interviewers/`, `skills/interview/` |
| 3 · Draft | Structure the transcript in the active voice; invent nothing | `engine/2-draft.md`, `voice/<voice>/`, `templates/draft-skeleton.html`, `skills/draft/` |
| 4-5 · Council + revision | Editors score N/10, hard caps bind, loop to ≥ 9 | `editors/`, `engine/3-revision-loop.md`, `skills/council/` |
| 6 · Human pass | The author edits and publishes; the machine never does | `engine/feedback-intake.md`, `RULES.md` |
| 7 · Lessons | Diff published vs draft; append approved rules per voice | `engine/4-lessons-loop.md`, `voice/<voice>/content-lessons.md`, `skills/lessons/` |

`PANEL.md` is the narrative version of that table. `sandbox/DRY-RUN.md` walks one full loop on
invented data — every handoff, every score, one capped round — in a few minutes' read.

**The stance that makes it work** (see `SOUL.md`, `PROJECT-INSTRUCTIONS.md`): one voice, one
piece, one step, one turn. The orchestrator names that state at the top of every relevant reply,
stops when it is the author's turn, and never runs ahead of the step it was given. Tangents are
explicitly parked, researched, or switched — never silently followed.

---

## The demo suite

Everything below is fictional. Two invented authors, an invented panel, an invented council, and
three invented pieces at three different stages so a reader can trace the whole machine.

### Two voices — `voice/`
A voice pack is what stops every piece sounding like the model that wrote it. Each pack has three
files: `voice-guide.md` (the DNA and the hard bans), `style-guide.md` (who writes, what, for whom),
and `content-lessons.md` (rules the lessons loop appends; these **override** the guides).

| Pack | Persona | Register | Sanctions | Bans |
|---|---|---|---|---|
| `demo-dana` | Dana Whitlock, staff infrastructure engineer | clipped, mechanism-first, verdict-clear | `X, not Y` technical contrasts, inline code, numbered steps, tables, verdict fragments | hype adjectives, presuppose-and-dismantle, hedged non-verdicts, fake precision |
| `demo-mira` | Mira Calder, narrative nonfiction writer | patient, scene-led, plain-spoken | scene openers, first-person reflection, quoted speech as structure, a repeated image | `X, not Y` contrasts, bullets/tables/code, manufactured profundity, invented or reconstructed detail |

The two packs contradict each other on purpose. That is the point: `editors/voice-guardian.md` is
voice-*relative*, so the same sentence is house style in one pack and a hard finding in the other.

### Eleven interviewers — `interviewers/`
Extraction personas that run before a draft exists. Role-named and generic — a production brain
typically adds celebrity-craft personas for the same slots, which is exactly why a public repo
does not carry them. Each file states its obsessions, its question shapes, and a written
`You are done when` test, which is what makes a panel stoppable instead of endless.

`architect` · `tactician` · `operator` · `customer-advocate` · `domain-specialist` ·
`narrative-prober` · `stakes-prober` · `curious-generalist` · `polish-breaker` · `layperson` ·
`skeptic` — plus `partner-advocate` (optional, see below).

### Eleven editors — `editors/`
Judgment personas that run after a draft exists. Each scores 1-10 with a written rubric and splits
findings into **editorial fixes** (the machine rewrites them) and **information gaps** (only the
author can fill them, so they route back to Step 2 as a single question). Three are mandatory on
every piece; `slop-allergist`, `technical-reviewer`, and `presentation-reviewer` carry hard caps
that hold regardless of how good the rest of the draft is.

`slop-allergist` · `voice-guardian` · `presentation-reviewer` (mandatory) · `technical-reviewer` ·
`specificity-auditor` · `structure-editor` · `cold-reader` · `closer` · `durability-reader` ·
`idea-density` · `hook-retention` — plus `partner-brand-steward` (optional, see below).

### Three pieces at three stages — `drafts/`
Read them in this order to watch the machine work.

| Piece | Voice | Stage | What it demonstrates |
|---|---|---|---|
| [`idempotency-is-the-whole-job`](drafts/idempotency-is-the-whole-job/) | demo-dana | **interviewing** | A transcript mid-flight: two personas closed on their `done-when` tests, a third with a pending question, provisional `[GAP]`s recorded, and deliberately **no `draft.html`** — Step 3 does not run ahead of the evidence. |
| [`rehearse-the-rollback`](drafts/rehearse-the-rollback/) | demo-dana | **council** | A draft and a **failed** first round: aggregate 7.2 against a bar of 9, two hard caps in force (a presuppose-and-dismantle opener, a skipped heading level), five fixes applied in place, two gaps routed back to named interviewers, round 2 pending. |
| [`the-board-on-the-wall`](drafts/the-board-on-the-wall/) | demo-mira | **ready-for-human-pass** | A finished piece: 9.2 at round 2, every detail traceable to the transcript, unprovenanced lines cut rather than softened, clearances recorded, and the last step left to the human because the machine never publishes. |

Every piece folder carries the same five artifacts — `piece.md` (status), `transcript.md`
(evidence pool), `sources.md` (provenance + council record + pre-publish checklist), `draft.html`
(the content), `meta.json` (machine-readable status) — plus `assets/`.

### The optional partner seam — `partners/`
One slot in the machine is configurable, and it is **dormant by default**. If a piece names a
partner that has a file in `partners/`, two parameterized personas wake up:
`interviewers/partner-advocate.md` (zealous at Step 2, surfaces what is relevant so the author can
say no) and `editors/partner-brand-steward.md` (never zealous, fact-checks naming, accuracy,
positioning, and brand rules at Step 4). The personas stay stable while the facts change, which is
why the facts live in a file.

With no partner configured — the case for all three demo pieces — the council is
quality-editors-only. `partners/meridian-cloudworks.md` is a **fictional company with invented
products**, included so the seam can be read end to end without naming a real vendor. See
`partners/README.md`.

---

## Honest framing

- **This repo is the companion to the webapp, not a product.** It is the content store the
  webapp mounts at `/brain`; on its own it is a pile of well-written markdown plus two launcher
  scripts. The webapp supplies the runtime, the connectors, and the rendering.
- **The production instance is private, and stays that way.** A working brain holds one real
  author's voice pack, their memory file, their drafts, and their real partner fact files. None
  of that is publishable, and none of it is copied here. What is here — the engine steps, the
  turn-taking discipline, the persona contracts, the council's scoring and hard-cap mechanics,
  the piece-folder schema — is the real machinery, demonstrated on invented material.
- **Nothing in this repo is sourced from the web.** No external citations, no URLs to documents,
  no real companies, products, people, or incidents. The demo pieces cite their own transcripts,
  and where a claim could not be sourced the draft says so with a `[GAP]` instead of inventing a
  number. That is the discipline the machine exists to enforce, applied to its own showcase.
- **The 9/10 bar is deliberately uncomfortable.** It is what forces a second round, and the
  second round is where the good writing comes from. `drafts/rehearse-the-rollback/` shows a
  draft failing it honestly rather than a demo suite full of pieces that cleared it on the first
  pass.

## Layout

```
agent.yaml  SOUL.md  RULES.md  PROJECT-INSTRUCTIONS.md   runtime contract + orchestrator persona
PANEL.md  VAULT.md  README.md                            flow spec + idea archive
engine/            the numbered steps, in prose
interviewers/      Step 2 personas (+ README: the file contract and selection guide)
editors/           Step 4-5 personas (+ README: rubrics, mandatory three, hard caps)
voice/<persona>/   voice-guide · style-guide · content-lessons
drafts/<piece>/    piece.md · transcript.md · sources.md · draft.html · meta.json · assets/
partners/          optional seam, dormant by default (+ README)
skills/            GitAgent skills: trigger phrases and instructions per step
workflows/         multi-step pipelines with approval gates
templates/         the draft shell and its contract
memory/            session pointers (ships as an empty template)
scripts/           new-piece.sh (scaffolding) · validate-gitagent.sh · verify-public-clean.sh
sandbox/           DRY-RUN.md — one full loop on invented data
```

## Verifying a change here

```
./scripts/verify-public-clean.sh   # the publication gate: banned brand string, real names,
                                   # emails, account IDs, private-document links, fictional
                                   # labeling, and the draft.html parser contract
./scripts/validate-gitagent.sh     # frontmatter, referenced files, launcher behavior
```

Both must pass. `verify-public-clean.sh` assembles its search tokens at runtime so the gate
script never contains the strings it hunts — a verifier that spelled them out would fail its own
gate. There is no build and no other test suite; the repo is content. The real check is
behavioral: clone it somewhere disposable, drive one interview turn and one council round, and
confirm the persona did what its file says it does.

See `AGENTS.md` for the maintenance notes an agent session needs, and `RULES.md` for the safety
rules the machine runs under (read before modifying; no publishing; no invented facts).
