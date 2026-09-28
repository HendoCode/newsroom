# Project agent memory

This file is the project's committed home for project-intrinsic agent knowledge: architecture,
contracts, verification, and sharp-edge notes that should travel with the content.

## Session bootstrap: content-work sessions load the orchestrator stance

When a session in this repo is opened to run the content workflow (oracle, interview, draft,
council, human pass, lessons), bootstrap it: read `PROJECT-INSTRUCTIONS.md` and `SOUL.md` and
operate as the Masthead orchestrator they define — disciplined turn-taking, one voice /
one piece / one step / one turn, reorient commands honored. The maintenance notes below do not
replace that stance; maintenance-only sessions can skip the bootstrap.

## What this repo is

- Pure markdown/HTML content. No build, no dependencies, no test suite beyond
  `scripts/validate-gitagent.sh`.
- The **public demo instance** of the brain consumed by `Newsroom`, which clones it
  read-write and bind-mounts it into its `agents` container at `/brain`. `README.md` is the
  authoritative overview; `PANEL.md` is the flow spec.
- Everything in it is fictional by policy: two invented author voices (`voice/demo-dana`,
  `voice/demo-mira`), role-named personas, invented subjects (Harborline Freight, Kestrel Bay
  Ferry Authority, Meridian Cloudworks), and three demo pieces at three pipeline stages.

## Dual-consumer architecture

Every change must preserve both consumers.

1. **Newsroom** — globs and reads raw files directly as system-prompt blocks:
   `interviewers/*.md`, `editors/*.md`, `voice/<slug>/*.md`, `drafts/<piece>/*`, `engine/*.md`,
   `partners/*.md`. There is NO rendering layer; a file's prose *is* the behavior. Editing a
   persona's wording changes what a live interviewer asks and when it decides it is done. Never
   rename or restructure these paths without treating it as an API change.
2. **GitAgent-style runtime** — `agent.yaml` (model/tools/limits), `SOUL.md` (orchestrator
   persona), `RULES.md` (safety), `memory/MEMORY.md` (session pointers), `skills/*/SKILL.md`
   (frontmatter + triggers + instructions), `workflows/*.yaml` (steps with `__approval_gate__`),
   `gitagent.sh` (launcher with provider-key detection and model fallback).

## Contracts that are easy to break silently

- **Directory and filename shapes.** `voice/<slug>/{voice-guide,style-guide,content-lessons}.md`;
  `drafts/<piece>/{piece.md,transcript.md,sources.md,draft.html,meta.json,assets/}`;
  `engine/{1-oracle,2-draft,3-revision-loop,4-lessons-loop,feedback-intake,research-sidecar}.md`;
  `skills/<name>/SKILL.md`; `partners/<slug>.md`. Scaffold with `scripts/new-piece.sh` rather
  than hand-creating folders.
- **The literal string `<section class="editorial">`** in `draft.html` is a parser contract: the
  revision loop, the external-share strip in `engine/feedback-intake.md`, and the human pass all
  key off that exact tag-and-class. Never paraphrase it, never move it inside `<article>`, never
  publish it.
- **Skill frontmatter** (`name`, `description`, `allowed-tools`) and the editor `## Output`
  shape starting with `Score: N/10` are parsed. Keep the sections when rewriting a persona:
  `## You judge` / `## You flag` (or `## Your obsessions` / `## How you ask` for interviewers)
  / `## Output` (`## You are done when` on the interview side).
- **The `done-when` test is what makes a panel stoppable.** An interviewer file without one makes
  the orchestrator guess when to move on, which is the drift failure mode the whole stance exists
  to prevent.
- **The 9/10 council bar and the hard caps** (`slop-allergist`, `technical-reviewer`,
  `presentation-reviewer`) are the mechanism, not decoration. A demo piece that clears 9 on the
  first round teaches a reader nothing; keep at least one piece visibly failing and looping.

## Demo-boundary rules (non-negotiable here)

- The de-branding gate must hold: `./scripts/verify-public-clean.sh` returns **zero** matches for
  the banned brand string across the whole tree, always. That script assembles its search tokens
  at runtime so the gate never contains the literal it hunts — keep it that way.
- No real person names, emails, account IDs, or links to private documents anywhere in content.
  Fictional subjects only, and each demo artifact says so near the top.
- Nothing from a private production brain lands here: no personal voice packs, no `memory/`
  contents, no real drafts, no real partner fact files. `memory/MEMORY.md` ships as an empty
  template on purpose.
- No external citations. Demo pieces cite their own `transcript.md` and `sources.md`; where a
  claim cannot be sourced it stays a `[GAP: ...]` rather than becoming a plausible number.
- The partner seam stays dormant by default: no piece in `drafts/` configures a partner, and
  `partners/` holds one clearly fictional file.

## Deliberate absences

- No CI workflow and no remote: this instance is local-only, so a GitHub Actions file would be
  dead weight. `scripts/validate-gitagent.sh` is the verification entry point and runs offline.
- No brand tokens, logos, or render-time branding injection. `templates/` holds a neutral draft
  shell only; a production instance may add its own branded render template.
- No celebrity-craft personas. A production brain carries named-host and named-essayist personas
  in the same slots; a public repo carries role-named equivalents.

## Verification before calling work done

```
./scripts/verify-public-clean.sh     # banned brand string, real names, emails, account IDs,
                                     # private-document links, fictional labeling, parser contract
./scripts/validate-gitagent.sh       # frontmatter, referenced files, launcher behavior
bash -n gitagent.sh scripts/*.sh     # shell syntax
```

The behavioral check is the real one: clone this repo somewhere disposable (no `origin`, so
nothing can auto-push), drive one interview turn and one council round, and confirm each persona
did what its file says it does. Read `sandbox/DRY-RUN.md` first to know what correct looks like.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
