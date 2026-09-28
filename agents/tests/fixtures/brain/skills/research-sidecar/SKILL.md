---
name: research-sidecar
description: "Borrowed-time research sidecar using donsetch CLI for quick fact verification."
allowed-tools: read write cli
---

# Research Sidecar Skill

Borrowed-time research sidecar using `donsetch` CLI for rapid, provider-agnostic fact verification during drafting or interviews.

## Triggers
- "/research <q>"
- "dig on that"
- "verify that"
- "check that fact"

## Instructions
1. Announce entry into borrowed-time research and state the return point.
2. Run `donsetch search "<query>" --max-results 5 --json` for quick factual search.
3. Run `donsetch fetch <url> --focus "<query>" --max-chars 2000 --json` for targeted page extraction if needed.
4. Synthesize a concise, sourced factual summary.
5. Explicitly return control to the paused step and turn.
