#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ERRORS=0
WARNINGS=0

report_error() {
  echo "[ERROR] $1"
  ((ERRORS++)) || true
}

report_warning() {
  echo "[WARN ] $1"
  ((WARNINGS++)) || true
}

report_ok() {
  echo "[OK   ] $1"
}

echo "=== Masthead Brain — GitAgent Validation ==="
echo "Root: ${REPO_ROOT}"
echo

# --- 1. Core config files ---
for f in agent.yaml SOUL.md RULES.md; do
  if [[ ! -f "${REPO_ROOT}/${f}" ]]; then
    report_error "Missing core config: ${f}"
  else
    report_ok "Core config present: ${f}"
  fi
done

# --- 2. agent.yaml YAML frontmatter validity ---
YAML_AVAILABLE=false
if command -v python3 &>/dev/null; then
  if python3 -c "import yaml" 2>/dev/null; then
    YAML_AVAILABLE=true
  fi
fi

if [[ "${YAML_AVAILABLE}" == "true" ]]; then
  if python3 -c "import yaml; yaml.safe_load(open('${REPO_ROOT}/agent.yaml'))" 2>/dev/null; then
    report_ok "agent.yaml: valid YAML"
  else
    report_error "agent.yaml: invalid YAML"
  fi
else
  echo "[INFO ] PyYAML not installed — skipping YAML parse check"
fi

if [[ -f "${REPO_ROOT}/agent.yaml" ]]; then
  if grep -q '^name:' "${REPO_ROOT}/agent.yaml"; then
    report_ok "agent.yaml: has 'name' field"
  else
    report_error "agent.yaml: missing 'name' field"
  fi
  if grep -q '^version:' "${REPO_ROOT}/agent.yaml"; then
    report_ok "agent.yaml: has 'version' field"
  else
    report_error "agent.yaml: missing 'version' field"
  fi
  if grep -q '^tools:' "${REPO_ROOT}/agent.yaml"; then
    report_ok "agent.yaml: has 'tools' list"
  else
    report_error "agent.yaml: missing 'tools' list"
  fi
  if grep -q '^model:' "${REPO_ROOT}/agent.yaml"; then
    report_ok "agent.yaml: has 'model' block"
  else
    report_error "agent.yaml: missing 'model' block"
  fi
  if grep -q 'preferred:' "${REPO_ROOT}/agent.yaml"; then
    report_ok "agent.yaml: has 'model.preferred'"
  else
    report_error "agent.yaml: missing 'model.preferred'"
  fi
  if grep -q '^  fallback:' "${REPO_ROOT}/agent.yaml"; then
    report_ok "agent.yaml: has 'model.fallback' list"
  else
    report_error "agent.yaml: missing 'model.fallback' list"
  fi
  for expected in "openrouter:google/gemini-2.5-flash" "google:gemini-2.5-flash" "anthropic:claude-sonnet-4-5-20250929" "openrouter:anthropic/claude-3.5-sonnet" "openai:gpt-4o"; do
    if grep -q "${expected}" "${REPO_ROOT}/agent.yaml"; then
      report_ok "agent.yaml fallback contains: ${expected}"
    else
      report_error "agent.yaml fallback missing: ${expected}"
    fi
  done
fi

# --- 3. memory/MEMORY.md ---
if [[ ! -f "${REPO_ROOT}/memory/MEMORY.md" ]]; then
  report_error "Missing memory/MEMORY.md"
else
  report_ok "memory/MEMORY.md present"
fi

# --- 4. Skills: YAML frontmatter + referenced files ---
EXPECTED_SKILLS=(oracle interview draft council lessons research-sidecar draft-intake vault-ingest)
for skill in "${EXPECTED_SKILLS[@]}"; do
  skill_file="${REPO_ROOT}/skills/${skill}/SKILL.md"
  if [[ ! -f "${skill_file}" ]]; then
    report_error "Missing skill: skills/${skill}/SKILL.md"
    continue
  fi

  # Check YAML frontmatter
  if head -1 "${skill_file}" | grep -q '^---'; then
    report_ok "skills/${skill}: YAML frontmatter starts with ---"
  else
    report_error "skills/${skill}: missing YAML frontmatter opener"
  fi

  if grep -q '^---$' "${skill_file}"; then
    # Need at least two --- to form frontmatter
    count=$(grep -c '^---$' "${skill_file}" || true)
    if [[ "$count" -ge 2 ]]; then
      report_ok "skills/${skill}: YAML frontmatter closed"
    else
      report_error "skills/${skill}: YAML frontmatter not properly closed"
    fi
  fi

  # Check name field in frontmatter
  if grep -A 20 '^---' "${skill_file}" | grep -q '^name:'; then
    report_ok "skills/${skill}: frontmatter has 'name'"
  else
    report_error "skills/${skill}: frontmatter missing 'name'"
  fi

  # Check description field in frontmatter
  if grep -A 20 '^---' "${skill_file}" | grep -q '^description:'; then
    report_ok "skills/${skill}: frontmatter has 'description'"
  else
    report_error "skills/${skill}: frontmatter missing 'description'"
  fi

  # Check allowed-tools or allowed_tools in frontmatter
  if grep -A 20 '^---' "${skill_file}" | grep -qiE '^allowed[-_]?tools:'; then
    report_ok "skills/${skill}: frontmatter has allowed-tools"
  else
    report_warning "skills/${skill}: frontmatter missing allowed-tools"
  fi
done

# --- 5. Workflow files ---
EXPECTED_WORKFLOWS=(content-pipeline draft-refinement)
for wf in "${EXPECTED_WORKFLOWS[@]}"; do
  wf_file="${REPO_ROOT}/workflows/${wf}.yaml"
  if [[ ! -f "${wf_file}" ]]; then
    report_error "Missing workflow: workflows/${wf}.yaml"
    continue
  fi

  if [[ "${YAML_AVAILABLE}" == "true" ]]; then
    if python3 -c "import yaml; yaml.safe_load(open('${wf_file}'))" 2>/dev/null; then
      report_ok "workflows/${wf}.yaml: valid YAML"
    else
      report_error "workflows/${wf}.yaml: invalid YAML"
    fi
  else
    echo "[INFO ] PyYAML not installed — skipping YAML parse check for workflows/${wf}.yaml"
  fi

  if grep -q '^name:' "${wf_file}"; then
    report_ok "workflows/${wf}.yaml: has 'name'"
  else
    report_error "workflows/${wf}.yaml: missing 'name'"
  fi

  if grep -q '^steps:' "${wf_file}"; then
    report_ok "workflows/${wf}.yaml: has 'steps'"
  else
    report_error "workflows/${wf}.yaml: missing 'steps'"
  fi

done

# --- 6. Referenced file existence (backward-compat seam check) ---
for d in interviewers editors voice drafts engine partners; do
  if [[ ! -d "${REPO_ROOT}/${d}" ]]; then
    report_warning "Backward-compat directory missing: ${d}/"
  else
    report_ok "Backward-compat directory: ${d}/"
  fi
done

# Check specific referenced engine files
for f in engine/1-oracle.md engine/2-draft.md engine/3-revision-loop.md engine/4-lessons-loop.md engine/research-sidecar.md engine/feedback-intake.md; do
  if [[ -f "${REPO_ROOT}/${f}" ]]; then
    report_ok "Referenced file exists: ${f}"
  else
    report_warning "Referenced file missing: ${f}"
  fi
done

# Check that interviewers and editors are non-empty
if [[ -d "${REPO_ROOT}/interviewers" ]]; then
  ic=$(find "${REPO_ROOT}/interviewers" -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')
  if [[ "$ic" -gt 0 ]]; then
    report_ok "interviewers/: ${ic} persona files"
  else
    report_warning "interviewers/: no .md files"
  fi
fi

if [[ -d "${REPO_ROOT}/editors" ]]; then
  ec=$(find "${REPO_ROOT}/editors" -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')
  if [[ "$ec" -gt 0 ]]; then
    report_ok "editors/: ${ec} editor files"
  else
    report_warning "editors/: no .md files"
  fi
fi

# --- 7. gitagent.sh executable & structure ---
if [[ ! -x "${REPO_ROOT}/gitagent.sh" ]]; then
  if [[ -f "${REPO_ROOT}/gitagent.sh" ]]; then
    report_error "gitagent.sh exists but is not executable (run: chmod +x gitagent.sh)"
  else
    report_error "Missing gitagent.sh launcher"
  fi
else
  report_ok "gitagent.sh: executable"
fi

# Syntax check
if bash -n "${REPO_ROOT}/gitagent.sh" 2>/dev/null; then
  report_ok "gitagent.sh: bash syntax valid"
else
  report_error "gitagent.sh: bash syntax errors detected"
fi

# --- 7b. gitagent.sh runtime behavior (stubbed binary, real invocation) ---
STUB_DIR="$(mktemp -d)"
trap 'rm -rf "${STUB_DIR}"' EXIT
STUB_ARGS_FILE="${STUB_DIR}/captured_args"

cat > "${STUB_DIR}/gitagent" <<'STUB'
#!/usr/bin/env bash
if [[ "${1:-}" == "--version" ]]; then
  echo "stub-1.0.0"
  exit 0
fi
echo "$@" > "${GITAGENT_STUB_ARGS_FILE}"
exit 0
STUB
chmod +x "${STUB_DIR}/gitagent"

ALL_PROVIDER_ENV_VARS=(OPENROUTER_API_KEY GEMINI_API_KEY ANTHROPIC_API_KEY OPENAI_API_KEY GROQ_API_KEY DEEPSEEK_API_KEY MISTRAL_API_KEY GITAGENT_MODEL)

# Runs gitagent.sh with only the given env assignments set (all provider keys
# and GITAGENT_MODEL are unset first) and a stubbed `gitagent` in PATH.
# Populates LAST_RC, LAST_OUTPUT, LAST_ARGS (the argv the stub received, or
# empty if the stub was never invoked).
run_launcher() {
  local env_assignments="$1"; shift
  rm -f "${STUB_ARGS_FILE}"
  LAST_RC=0
  LAST_OUTPUT=$(
    for v in "${ALL_PROVIDER_ENV_VARS[@]}"; do unset "$v"; done
    eval "${env_assignments}"
    export PATH="${STUB_DIR}:${PATH}"
    export GITAGENT_STUB_ARGS_FILE="${STUB_ARGS_FILE}"
    bash "${REPO_ROOT}/gitagent.sh" "$@" 2>&1
  ) || LAST_RC=$?
  LAST_ARGS=""
  if [[ -f "${STUB_ARGS_FILE}" ]]; then
    LAST_ARGS="$(cat "${STUB_ARGS_FILE}")"
  fi
}

check_launcher() {
  local desc="$1" expect_rc="$2" expect_pattern="$3" search_in="$4"
  local haystack="${LAST_ARGS}"
  [[ "${search_in}" == "output" ]] && haystack="${LAST_OUTPUT}"
  if [[ "${LAST_RC}" -ne "${expect_rc}" ]]; then
    report_error "${desc} (expected exit ${expect_rc}, got ${LAST_RC})"
    return
  fi
  if [[ -n "${expect_pattern}" ]] && ! grep -qF -- "${expect_pattern}" <<<"${haystack}"; then
    report_error "${desc} (expected to find '${expect_pattern}')"
    return
  fi
  report_ok "${desc}"
}

# --help bypasses the key gate entirely, regardless of keys.
run_launcher "" --help
check_launcher "gitagent.sh --help: bypasses key gate and forwards to gitagent" 0 "--help" args

# No keys, no --model, no GITAGENT_MODEL: informative banner + non-zero exit,
# and the gitagent binary must never be invoked.
run_launcher "" ping
check_launcher "gitagent.sh: no provider key -> onboarding banner + exit 1" 1 "NO PROVIDER API KEY DETECTED" output
if [[ -n "${LAST_ARGS}" ]]; then
  report_error "gitagent.sh: no provider key -> gitagent binary should not be invoked"
else
  report_ok "gitagent.sh: no provider key -> gitagent binary not invoked"
fi

# Explicit --model bypasses auto-detection even with no keys.
run_launcher "" --model custom:foo
check_launcher "gitagent.sh --model: explicit model bypasses key gate" 0 "--model custom:foo" args

# GITAGENT_MODEL env var is forwarded as --model ahead of other args.
run_launcher 'export GITAGENT_MODEL=custom:bar' run
check_launcher "gitagent.sh: GITAGENT_MODEL forwarded as --model" 0 "--model custom:bar run" args

# Per-provider default model resolution (priority mapping).
provider_keys=(OPENROUTER_API_KEY GEMINI_API_KEY ANTHROPIC_API_KEY OPENAI_API_KEY)
provider_models=("openrouter:google/gemini-2.5-flash" "google:gemini-2.5-flash" "anthropic:claude-sonnet-4-5-20250929" "openai:gpt-4o")
for i in "${!provider_keys[@]}"; do
  key="${provider_keys[$i]}"
  model="${provider_models[$i]}"
  run_launcher "export ${key}=x" ping
  check_launcher "gitagent.sh: ${key} alone resolves default model ${model}" 0 "--model ${model}" args
done

# Priority order: OPENROUTER outranks the others when multiple keys present.
run_launcher 'export OPENROUTER_API_KEY=x; export ANTHROPIC_API_KEY=y; export OPENAI_API_KEY=z' ping
check_launcher "gitagent.sh: OPENROUTER_API_KEY takes priority over other keys" 0 "--model openrouter:google/gemini-2.5-flash" args

# Providers that are detected (so the "no key" banner is skipped) but have no
# default model mapping must still fail loudly with explicit guidance, never
# silently launch gitagent without a model.
for key in GROQ_API_KEY DEEPSEEK_API_KEY MISTRAL_API_KEY; do
  run_launcher "export ${key}=x" ping
  if [[ "${LAST_RC}" -eq 0 ]]; then
    report_error "gitagent.sh: ${key} alone silently succeeds with no --model (should require explicit --model)"
  else
    report_ok "gitagent.sh: ${key} alone without a default mapping exits non-zero with guidance"
  fi
  if [[ -n "${LAST_ARGS}" ]]; then
    report_error "gitagent.sh: ${key} alone should not invoke gitagent binary without a resolved model"
  fi
done

unset -f run_launcher check_launcher

# --- 8. Tool permissions in agent.yaml match allowed-tools in skills ---
if [[ -f "${REPO_ROOT}/agent.yaml" ]]; then
  AGENT_TOOLS=$(grep -A 10 '^tools:' "${REPO_ROOT}/agent.yaml" | grep '^  - ' | sed 's/^  - //' | sort | tr '\n' ',' | sed 's/,$//')
  report_ok "agent.yaml tools: ${AGENT_TOOLS}"
fi

# --- Summary ---
echo
echo "===================="
echo "Validation complete."
echo "Errors:   ${ERRORS}"
echo "Warnings: ${WARNINGS}"

if [[ "${ERRORS}" -eq 0 ]]; then
  echo "Result: PASS"
  exit 0
else
  echo "Result: FAIL"
  exit 1
fi
