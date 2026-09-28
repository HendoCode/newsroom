#!/usr/bin/env bash
# new-piece.sh — scaffold a piece folder the way engine/1-oracle.md describes.
#
#   scripts/new-piece.sh <slug> <voice> ["title"] ["origin"]
#
# Creates drafts/<slug>/ with piece.md, an empty transcript.md, an empty sources.md,
# meta.json, and assets/. It does NOT create draft.html: an empty draft looks like progress
# and isn't. The skeleton is copied in at Step 3, once a transcript exists to draft from
# (templates/draft-skeleton.html).
#
# Safe to re-run: existing files are never overwritten.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat >&2 <<EOF
usage: $(basename "$0") <slug> <voice> ["title"] ["origin"]

  slug    piece folder name under drafts/ — kebab-case, from the spike headline
  voice   a pack under voice/ (this repo ships demo-dana and demo-mira)
  title   optional working title (default: the slug, humanized)
  origin  optional provenance line (default: "VAULT.md — spike not yet recorded")

example:
  scripts/new-piece.sh rehearse-the-rollback demo-dana \\
    "Rehearse the rollback" "Oracle run 2026-09-14 · Spike #2 (see VAULT.md)"
EOF
  exit 2
}

[[ $# -ge 2 ]] || usage
SLUG="$1"
VOICE="$2"
TITLE="${3:-$(echo "$SLUG" | tr '-' ' ')}"
ORIGIN="${4:-VAULT.md — spike not yet recorded}"

[[ "$SLUG" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || {
  echo "ERROR: slug must be kebab-case lowercase (got: ${SLUG})" >&2; exit 1; }
[[ -d "${REPO_ROOT}/voice/${VOICE}" ]] || {
  echo "ERROR: no voice pack at voice/${VOICE}/ — create the pack first." >&2; exit 1; }

PIECE_DIR="${REPO_ROOT}/drafts/${SLUG}"
mkdir -p "${PIECE_DIR}/assets"
[[ -e "${PIECE_DIR}/assets/.gitkeep" ]] || : > "${PIECE_DIR}/assets/.gitkeep"

write_if_absent() {
  local path="$1"; shift
  if [[ -e "$path" ]]; then
    echo "keep    ${path#"${REPO_ROOT}/"}"
  else
    cat > "$path"
    echo "created ${path#"${REPO_ROOT}/"}"
  fi
}

write_if_absent "${PIECE_DIR}/piece.md" <<EOF
# Piece: ${SLUG}

Metadata + status for this content target. One of these folders per piece;
many can be in flight at once, each at its own stage, for its own voice.
The active piece is named in the orchestrator's state banner.

## Metadata
- Slug:        ${SLUG}
- Voice:       ${VOICE}
- Title:       ${TITLE}
- Origin:      ${ORIGIN}
- Target:      (unset — blog post / social / newsletter / reference doc)
- Partners:    none configured (see partners/README.md; the council runs quality-editors-only)

## Files in this folder
- draft.html      — THE output content (self-contained, browser-openable). The council edits this.
- transcript.md   — interview transcript (SOURCE; every claim traces here or to sources.md)
- sources.md      — research citations, council record, pre-publish checklist, handoff notes
- feedback.md     — outside-reviewer inbox, created when the human pass starts
- assets/         — diagrams and images (SVGs are also inlined into draft.html)
- meta.json       — this status, machine-readable

## Status
- Stage:          interviewing   (interviewing → drafting → council → ready-for-human-pass → published)
- Council score:  none yet
- Open GAPs:      0
- Published URL:  none yet
EOF

write_if_absent "${PIECE_DIR}/transcript.md" <<EOF
# Interview Transcript — ${SLUG}

Source material for this piece. The draft traces back to this file: every claim, number,
story, and example must appear here or be cited in sources.md.

Roster run: (unset — pick 2-4 from interviewers/; see interviewers/README.md)

---

## (persona)

**Q1 — (the question, verbatim as asked)**
(the answer, verbatim as spoken — do not clean it up; the drafting step shapes it)
EOF

write_if_absent "${PIECE_DIR}/sources.md" <<EOF
# Sources & Handoff — ${SLUG}

Everything the draft rests on, with citations, plus the council record and the pre-publish
checklist. Written so the author can edit the draft directly without losing provenance.

## Research citations (every figure in the draft traces here)
- (none yet — mark unverifiable claims [GAP: need source] rather than asserting them)

## Council record
- Round 1: (not run)

## Pre-publish checklist
1. (open GAPs from the draft's editorial block land here)
2. Clearances: every named person, client, and figure confirmed for publication.
3. Diagrams: any inlined SVG redrawn from a current source.

## After you publish
Come back and run Step 7 (Lessons): the machine diffs the published version against the
draft, proposes generalizable lessons, and on an explicit yes appends them to
voice/${VOICE}/content-lessons.md.
EOF

write_if_absent "${PIECE_DIR}/meta.json" <<EOF
{
  "slug": "${SLUG}",
  "title": "${TITLE}",
  "voice": "${VOICE}",
  "origin": "${ORIGIN}",
  "target": null,
  "target_formats": [],
  "partners": [],
  "stage": "interviewing",
  "council_score": null,
  "open_gaps": 0
}
EOF

echo
echo "Piece scaffolded: drafts/${SLUG}/ (voice: ${VOICE})"
echo "Next: run the interview (skills/interview) and fill transcript.md — one question per turn."
