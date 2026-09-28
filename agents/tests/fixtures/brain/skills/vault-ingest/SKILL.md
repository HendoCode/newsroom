---
name: vault-ingest
description: "Ingests a topic, idea prompt, or seed URL into the Vault as a structured spike."
allowed-tools: read write cli
---

# Vault Ingest Skill

Ingests a topic, idea prompt, or seed URL into `VAULT.md` as a structured spike entry using `donsetch` keyless web research.

## Triggers
- "vault this"
- "ingest idea"
- "save to vault"
- "research and vault"

## Instructions
1. Accept a topic, seed URL, or raw idea prompt.
2. Run `donsetch search "<query>" --max-results 8 --json` and `donsetch fetch <url> --focus "<topic>" --max-chars 4000 --json`.
3. Synthesize findings into a structured spike entry (headline, thesis, verified claims with URLs, rank rationale, convergence note).
4. Read `VAULT.md` and append the new spike entry conforming strictly to `VAULT.md` structure.
