#!/usr/bin/env bash
# verify-public-clean.sh — the publication gate for this repo.
#
# This brain is a PUBLIC artifact. Two rules are absolute, and both are checkable:
#   1. The banned brand string appears nowhere in the tree (the de-branding ruling).
#   2. No real person names, emails, account IDs, or links to private documents.
#
# WHY THE TOKENS BELOW ARE ASSEMBLED AT RUNTIME: the gate is "zero literal matches anywhere in
# the tree", so a verification script that spelled the tokens out would fail its own gate and
# would itself be the leak. `tok st ephen` yields the name without ever containing it. Do not
# "simplify" these into literals — if you add a token to a list, split it the same way.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

tok() { local out="" part; for part in "$@"; do out+="$part"; done; printf '%s' "$out"; }
join_pipe() { local IFS='|'; printf '%s' "$*"; }

BANNED_BRAND="$(tok ly zr)"
FAILURES=0

section() { printf '\n=== %s ===\n' "$1"; }
fail() { printf '[FAIL ] %s\n' "$1"; FAILURES=$((FAILURES + 1)); }
pass() { printf '[OK   ] %s\n' "$1"; }
show() { sed 's/^/        /' <<<"$1"; }

# ---------------------------------------------------------------- 1. banned brand string
section "1. Banned brand string (case-insensitive, whole tree)"
hits=$(grep -riI "$BANNED_BRAND" . --exclude-dir=.git || true)
if [[ -n "$hits" ]]; then
  show "$hits"
  fail "found $(wc -l <<<"$hits") occurrence(s) of the banned brand string"
else
  pass "0 occurrences of the banned brand string"
fi

# ---------------------------------------------------------------- 2. real person / private brand names
section "2. Real person names and private-brand names"
NAME_PATTERN=$(join_pipe \
  "$(tok st ephen)" \
  "$(tok hen do)" \
  "$(tok a lex)" \
  "$(tok kun) $(tok chen)" \
  "$(tok bar baro)" \
  "$(tok fer riss)" \
  "$(tok ro gan)" \
  "$(tok howard) $(tok stern)" \
  "$(tok barbara) $(tok walters)" \
  "$(tok hou sel)" \
  "$(tok per ell)" \
  "$(tok shaan) $(tok puri)" \
  "$(tok larry) $(tok king)" \
  "$(tok accen ture)" \
  "$(tok crown) $(tok castle)" \
  "$(tok dairy land)" \
  "$(tok open claw)" \
  "$(tok whisper) $(tok flow)")
hits=$(grep -rinEI "$NAME_PATTERN" . --exclude-dir=.git || true)
if [[ -n "$hits" ]]; then
  show "$hits"
  fail "possible real person / private brand name(s) above"
else
  pass "no real person names or private-brand names"
fi

# ---------------------------------------------------------------- 3. emails & account IDs
section "3. Email addresses and account identifiers"
hits=$(grep -rinEI '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' . --exclude-dir=.git || true)
if [[ -n "$hits" ]]; then
  show "$hits"
  fail "email address(es) above"
else
  pass "no email addresses"
fi

hits=$(grep -rinEI '\b[0-9]{12}\b|account[ -]?id[:=]|subscription[ -]?id[:=]|tenant[ -]?id[:=]' . --exclude-dir=.git || true)
if [[ -n "$hits" ]]; then
  show "$hits"
  fail "possible account identifier(s) above"
else
  pass "no account/subscription/tenant identifiers"
fi

# ---------------------------------------------------------------- 4. private-document links
section "4. Links to private documents and unexpected external URLs"
DOC_PATTERN=$(join_pipe \
  "$(tok docs)\.$(tok google)" \
  "$(tok drive)\.$(tok google)" \
  "$(tok google)usercontent" \
  "$(tok /docu ment/d/)" \
  "$(tok notion)\.so" \
  "$(tok slack)\.com/archives" \
  "\.sharepoint\.com" \
  "$(tok dropbox)\.com" \
  "$(tok atlassian)\.net")
hits=$(grep -rinEI "$DOC_PATTERN" . --exclude-dir=.git || true)
if [[ -n "$hits" ]]; then
  show "$hits"
  fail "private document link(s) above"
else
  pass "no private document links"
fi

# Any remaining URL must be a namespace/standards URI, not a source citation or a document.
hits=$(grep -rInoE 'https?://[^ )"'"'"'>]+' . --exclude-dir=.git | grep -v 'www\.w3\.org' || true)
if [[ -n "$hits" ]]; then
  show "$hits"
  fail "unexpected external URL(s) above (demo pieces cite no external sources)"
else
  pass "no external URLs (only SVG/XML namespaces)"
fi

# ---------------------------------------------------------------- 5. fictional-subject labeling
section "5. Demo artifacts are labeled fictional"
for f in voice/demo-dana/voice-guide.md voice/demo-mira/voice-guide.md \
         drafts/idempotency-is-the-whole-job/piece.md drafts/rehearse-the-rollback/piece.md \
         drafts/the-board-on-the-wall/piece.md partners/meridian-cloudworks.md VAULT.md \
         sandbox/DRY-RUN.md; do
  if [[ ! -f "$f" ]]; then
    fail "missing expected demo artifact: $f"
  elif grep -qiE 'fictional|invented|does not exist' "$f"; then
    pass "$f is labeled fictional"
  else
    fail "$f is not labeled fictional"
  fi
done

# ---------------------------------------------------------------- 6. parser contract
section "6. draft.html parser contract (editorial annotation block)"
for f in drafts/*/draft.html; do
  [[ -e "$f" ]] || continue
  if grep -qF '<section class="editorial"' "$f"; then
    pass "$f carries the editorial block"
  else
    fail "$f is missing the literal editorial-block section tag"
  fi
done

# ---------------------------------------------------------------- summary
printf '\n====================\n'
if [[ "$FAILURES" -eq 0 ]]; then
  echo "Public-cleanliness gate: PASS (0 failures)"
  exit 0
fi
echo "Public-cleanliness gate: FAIL (${FAILURES} failure(s))"
exit 1
