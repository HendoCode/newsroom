#!/usr/bin/env bash
# Security-scan deploy gate for the CMW AWS POC deploy. See deploy/README.md for the full design.
#
# Runs three Trivy scans — image CVEs, IaC misconfig, and secrets — and exits nonzero if ANY of
# them fail. deploy/deploy.sh treats this script as a hard precondition before `tofu apply`.
#
# FAILS CLOSED: a missing scanner, a scan error, or an unreachable target (e.g. ECR auth failure)
# is treated exactly like a real finding — this script never exits 0 unless every scan genuinely
# ran and came back clean. There is no "scanner was unavailable, so skip it" path.
#
# Threshold (captain-decided, see deploy/README.md): block on CRITICAL only for images/IaC.
# Secrets are the exception — ANY secret finding blocks, regardless of severity.
#
# Usage:
#   deploy/security-gate.sh [image-tag-or-digest]
#
# image-tag-or-digest defaults to "latest" — the tag infra/aws-poc's deploy actually pulls
# (see infra/aws-poc/README.md "Redeploying just an app-code change"). Pass a plain tag (e.g. a
# commit-sha tag like "bc3419e") or a digest ("sha256:...") to scan a specific build instead.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

IMAGE_REF="${1:-latest}"
ECR_REGISTRY="<AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com"
WEB_REPO="${ECR_REGISTRY}/cmw-poc-web"
AGENTS_REPO="${ECR_REGISTRY}/cmw-poc-agents"
IMAGE_IGNOREFILE="${REPO_ROOT}/agents/.trivyignore"
SECRET_CONFIG="${SCRIPT_DIR}/trivy-secret.yaml"
SEVERITY="CRITICAL"

# ---- Preconditions: fail closed if we can't even attempt the scans ----
if ! command -v trivy >/dev/null 2>&1; then
  echo "FAIL: trivy is not installed / not on PATH." >&2
  echo "A missing scanner blocks the gate — this is not a skippable step." >&2
  exit 1
fi
if ! command -v git >/dev/null 2>&1; then
  echo "FAIL: git is not installed / not on PATH (needed to snapshot the tracked tree for the secrets scan)." >&2
  exit 1
fi
if [[ ! -f "$IMAGE_IGNOREFILE" ]]; then
  echo "FAIL: expected ignorefile not found: ${IMAGE_IGNOREFILE}" >&2
  exit 1
fi
if [[ ! -f "$SECRET_CONFIG" ]]; then
  echo "FAIL: expected secret-scanner config not found: ${SECRET_CONFIG}" >&2
  exit 1
fi

# ---- Bookkeeping ----
STEP_NAMES=()
STEP_STATUS=()
STEP_LOGS=()
TMP_LOGS=()
SECRET_SNAPSHOT=""

cleanup() {
  local f
  for f in "${TMP_LOGS[@]}"; do
    rm -f "$f"
  done
  if [[ -n "$SECRET_SNAPSHOT" ]]; then
    rm -rf "$SECRET_SNAPSHOT"
  fi
}
trap cleanup EXIT

# Runs one scan step, capturing its exit code and output without letting a failure abort the
# whole gate — we want every step to run so the summary reports all three categories at once.
run_step() {
  local name="$1"
  shift
  local logfile
  logfile="$(mktemp)"
  TMP_LOGS+=("$logfile")
  echo "==> ${name}"
  if "$@" >"$logfile" 2>&1; then
    STEP_NAMES+=("$name")
    STEP_STATUS+=(0)
    STEP_LOGS+=("$logfile")
  else
    local code=$?
    STEP_NAMES+=("$name")
    STEP_STATUS+=("$code")
    STEP_LOGS+=("$logfile")
  fi
}

image_ref_for() {
  local repo="$1"
  if [[ "$IMAGE_REF" == sha256:* ]]; then
    echo "${repo}@${IMAGE_REF}"
  else
    echo "${repo}:${IMAGE_REF}"
  fi
}

# ---- 1. Images (CVE) — the exact images the deploy pulls, via the ambient AWS credential chain ----
# Trivy authenticates to ECR itself (no docker login needed) as long as the ambient AWS credential
# chain is populated — e.g. `aws configure export-credentials` in the operator's shell first. An
# expired/missing credential or an unreachable registry makes trivy exit nonzero, which this gate
# treats as a FAIL, same as a real vulnerability finding (fail closed).
run_step "image: cmw-poc-web:${IMAGE_REF}" \
  trivy image --severity "$SEVERITY" --exit-code 1 --ignorefile "$IMAGE_IGNOREFILE" --format table \
  "$(image_ref_for "$WEB_REPO")"

run_step "image: cmw-poc-agents:${IMAGE_REF}" \
  trivy image --severity "$SEVERITY" --exit-code 1 --ignorefile "$IMAGE_IGNOREFILE" --format table \
  "$(image_ref_for "$AGENTS_REPO")"

# ---- 2. IaC (misconfig) — every TF dir in the tracked tree, not just infra/aws-poc ----
# Discovered from tracked *.tf files rather than hardcoded, so a future new TF dir is covered
# without a gate-script edit. --ignorefile is passed explicitly per-dir (trivy config's default
# .trivyignore auto-discovery is relative to CWD, not the scanned target dir) and only when that
# dir actually has one, since trivy fatals on a --ignorefile path that doesn't exist.
mapfile -t TF_DIRS < <(git -C "$REPO_ROOT" ls-files '*.tf' | xargs -n1 dirname | sort -u)
if [[ ${#TF_DIRS[@]} -eq 0 ]]; then
  echo "FAIL: no .tf files found under the tracked tree — expected at least infra/aws-poc." >&2
  STEP_NAMES+=("iac: (no TF dirs found)")
  STEP_STATUS+=(1)
  STEP_LOGS+=("/dev/null")
else
  for dir in "${TF_DIRS[@]}"; do
    ignore_args=()
    if [[ -f "${REPO_ROOT}/${dir}/.trivyignore" ]]; then
      ignore_args=(--ignorefile "${REPO_ROOT}/${dir}/.trivyignore")
    fi
    run_step "iac: ${dir}" \
      trivy config --severity "$SEVERITY" --exit-code 1 --format table "${ignore_args[@]}" "${REPO_ROOT}/${dir}"
  done
fi

# ---- 3. Secrets — the TRACKED tree only, any severity ----
# `git archive` snapshots exactly what's committed into a throwaway temp dir. Scanning the working
# tree directly would also sweep in gitignored build output (web/.next, node_modules, etc.) —
# noisy and slow, and not what actually ships. A git-archive failure is fatal to the whole gate
# (fail closed): without it we cannot honestly claim to have scanned the tracked tree.
SECRET_SNAPSHOT="$(mktemp -d)"
if ! git -C "$REPO_ROOT" archive HEAD | tar -x -C "$SECRET_SNAPSHOT" 2>/tmp/security-gate-archive-err.$$; then
  echo "FAIL: git archive of the tracked tree failed — cannot run the secrets scan." >&2
  cat /tmp/security-gate-archive-err.$$ >&2 2>/dev/null || true
  rm -f /tmp/security-gate-archive-err.$$
  STEP_NAMES+=("secrets: tracked tree")
  STEP_STATUS+=(1)
  STEP_LOGS+=("/dev/null")
else
  rm -f /tmp/security-gate-archive-err.$$
  # No --severity filter: secrets block on ANY severity, per captain-decided scope.
  run_step "secrets: tracked tree" \
    trivy fs --scanners secret --exit-code 1 --secret-config "$SECRET_CONFIG" --format table "$SECRET_SNAPSHOT"
fi

# ---- Summary ----
echo
echo "================ Security gate summary (severity: ${SEVERITY}-only, secrets: any) ================"
overall=0
for i in "${!STEP_NAMES[@]}"; do
  name="${STEP_NAMES[$i]}"
  status="${STEP_STATUS[$i]}"
  logfile="${STEP_LOGS[$i]}"
  if [[ "$status" -eq 0 ]]; then
    printf "PASS  %s\n" "$name"
  else
    printf "FAIL  %s  (exit %s)\n" "$name" "$status"
    overall=1
    if [[ -f "$logfile" ]]; then
      echo "  ---- ${name} output ----"
      sed 's/^/  /' "$logfile"
      echo "  ---- end ${name} output ----"
    fi
  fi
done
echo "======================================================================================"

if [[ "$overall" -eq 0 ]]; then
  echo "RESULT: PASS — no unignored CRITICAL findings (images/IaC) or secret findings (any severity)."
  exit 0
else
  echo "RESULT: FAIL — deploy blocked. Fix the finding(s) above, or add a justified, commented" >&2
  echo "ignore entry (agents/.trivyignore for images, infra/aws-poc/.trivyignore for IaC) for an" >&2
  echo "accepted risk, then re-run." >&2
  exit 1
fi
