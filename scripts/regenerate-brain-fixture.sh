#!/usr/bin/env bash
# Regenerate the checked-in Git test fixture (agents/tests/fixtures/brain/) from the pinned
# Masthead (content-machine-brain repo) ref recorded in agents/brain.lock — see agents/app/git/README.md for the
# full pin/bump story.
#
# Usage:
#   scripts/regenerate-brain-fixture.sh          # regenerate from brain.lock's pinned ref
#   scripts/regenerate-brain-fixture.sh <ref>     # preview a fixture for a ref you're about to
#                                                  # bump the pin to (review before editing the lock)
#
# Clones agents/brain.lock's `repo` at the requested ref into a throwaway temp dir (network
# required), then replaces agents/tests/fixtures/brain/ with that ref's tracked files (no `.git`)
# plus a small generated source stamp. The fixture is a frozen SNAPSHOT, not a live clone — the Git
# test suite copies it into its own throwaway repo per test (see agents/tests/conftest.py's
# `brain_repo` fixture); it never talks to the real remote.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="${ROOT}/agents/brain.lock"
FIXTURE_DIR="${ROOT}/agents/tests/fixtures/brain"

REPO_URL="$(python3 -c "import json; print(json.load(open('${LOCK_FILE}'))['repo'])")"
REF="${1:-$(python3 -c "import json; print(json.load(open('${LOCK_FILE}'))['ref'])")}"

TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT

echo "▶ cloning ${REPO_URL} @ ${REF} ..."
git init -q "${TMP}"
git -C "${TMP}" fetch -q --depth 1 "${REPO_URL}" "${REF}"
git -C "${TMP}" checkout -q FETCH_HEAD

rm -rf "${FIXTURE_DIR}"
mkdir -p "${FIXTURE_DIR}"
# rsync, not cp -R: cleanly excludes .git so the fixture stays a plain snapshot, no nested repo.
rsync -a --exclude='.git' "${TMP}/" "${FIXTURE_DIR}/"

CMW_BRAIN_FIXTURE_DIR="${FIXTURE_DIR}" CMW_BRAIN_FIXTURE_REPO="${REPO_URL}" CMW_BRAIN_FIXTURE_REF="${REF}" python3 - <<'PY'
import json
import os
from pathlib import Path

target = Path(os.environ["CMW_BRAIN_FIXTURE_DIR"]) / ".fixture-source.json"
target.write_text(
    json.dumps(
        {
            "repo": os.environ["CMW_BRAIN_FIXTURE_REPO"],
            "ref": os.environ["CMW_BRAIN_FIXTURE_REF"],
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
PY

echo "▶ regenerated ${FIXTURE_DIR} from ${REPO_URL}@${REF}"
echo "  review the diff, then run the agents/ suite (pytest) before committing:"
echo "    git -C '${ROOT}' status -- agents/tests/fixtures/brain"
echo "    (cd '${ROOT}/agents' && pytest)"
