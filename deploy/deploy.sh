#!/usr/bin/env bash
# Deploy wrapper for the CMW AWS POC (infra/aws-poc) — makes the security gate a hard
# precondition for `tofu apply`. See deploy/README.md for the full design.
#
# There is no documented apply path that skips deploy/security-gate.sh: this script runs the gate
# FIRST and only reaches the apply step if the gate exits 0. It does not run `tofu apply` itself —
# it prints the exact command an operator should run next, so a real apply is always a distinct,
# deliberate, human-run step (infra/aws-poc's own destructive-apply cautions in its README still
# apply in full).
#
# Usage:
#   deploy/deploy.sh [image-tag-or-digest]
#
# image-tag-or-digest is forwarded to deploy/security-gate.sh — defaults to "latest".

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
IMAGE_REF="${1:-latest}"

echo "==> Running the security gate before any apply (deploy/security-gate.sh ${IMAGE_REF})"
echo

if ! "${SCRIPT_DIR}/security-gate.sh" "$IMAGE_REF"; then
  echo >&2
  echo "Security gate FAILED — refusing to proceed to tofu apply. See the gate output above." >&2
  echo "Fix the finding(s), or add a justified, commented ignore-file entry for an accepted" >&2
  echo "risk (agents/.trivyignore for images, infra/aws-poc/.trivyignore for IaC), then re-run" >&2
  echo "deploy/deploy.sh." >&2
  exit 1
fi

echo
echo "Security gate PASSED."
echo
echo "This wrapper does not run the apply itself. From ${REPO_ROOT}/infra/aws-poc, run:"
echo
echo "    cd infra/aws-poc && tofu apply"
echo
echo "See infra/aws-poc/README.md \"Apply sequence\" for the full sequence this fits into"
echo "(ECR bootstrap, image build/push, ACM validation, etc.) — this wrapper only gates the"
echo "apply step itself, and only for the image tag/digest you just scanned (${IMAGE_REF})."
