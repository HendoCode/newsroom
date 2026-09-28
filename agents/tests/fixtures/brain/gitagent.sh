#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Masthead Brain — GitAgent Launcher ==="
echo "Repo: ${SCRIPT_DIR}"
echo

# --- Verify gitagent binary ---
if ! command -v gitagent &>/dev/null; then
  echo "ERROR: gitagent binary not found in PATH."
  echo "Install with: npm install -g @open-gitagent/gitagent"
  exit 1
fi

# --- Verify core config files ---
for f in agent.yaml SOUL.md RULES.md; do
  if [[ ! -f "${SCRIPT_DIR}/${f}" ]]; then
    echo "ERROR: Missing core config file: ${f}"
    exit 1
  fi
done

# --- Verify memory directory ---
if [[ ! -d "${SCRIPT_DIR}/memory" ]]; then
  mkdir -p "${SCRIPT_DIR}/memory"
fi
if [[ ! -f "${SCRIPT_DIR}/memory/MEMORY.md" ]]; then
  cat > "${SCRIPT_DIR}/memory/MEMORY.md" <<'EOF'
# Masthead Memory

## Session Context

### Active Voice
- voice: (unset)
- set_at: (unset)

### Active Piece
- piece: (unset)
- path: (unset)
- stage: (unset)

### Current Step
- step: (unset)
- turn: (unset)
- persona: (unset)
EOF
fi

# --- Verify backward-compat content directories ---
for d in interviewers editors voice drafts engine partners; do
  if [[ ! -d "${SCRIPT_DIR}/${d}" ]]; then
    : # No-op if missing, don't warn by default
  fi
done

# --- Verify skills & workflows (silent checks) ---
# No output needed for these counts.
# SKILL_COUNT=$(find "${SCRIPT_DIR}/skills" -name 'SKILL.md' 2>/dev/null | wc -l | tr -d ' ')
# WORKFLOW_COUNT=$(find "${SCRIPT_DIR}/workflows" -name '*.yaml' 2>/dev/null | wc -l | tr -d ' ')

echo "Configuration checks passed."

echo
echo "=== Launching GitAgent workspace ==="
echo "Directory: ${SCRIPT_DIR}"
echo
cd "${SCRIPT_DIR}"

# --- Transparent CLI forwarding & provider auto-detection ---
# If GITAGENT_MODEL is set and no --model is in args, prepend it
if [[ -n "${GITAGENT_MODEL:-}" ]]; then
  model_in_args=false
  for arg in "$@"; do
    case "$arg" in
      --model|--model=*) model_in_args=true; break ;;
    esac
  done
  if [[ "$model_in_args" == "false" ]]; then
    set -- --model "${GITAGENT_MODEL}" "$@"
  fi
fi

# Determine if an explicit model is now present (args or GITAGENT_MODEL)
has_explicit_model=false
for arg in "$@"; do
  case "$arg" in
    --model|--model=*)
      has_explicit_model=true
      break
      ;;
    --help|-h)
      # Help flags bypass the provider gate so users can inspect options
      exec gitagent --dir "${SCRIPT_DIR}" "$@"
      ;;
  esac
done

if [[ "$has_explicit_model" == "false" ]]; then
  if [[ -n "${OPENROUTER_API_KEY:-}" ]] || [[ -n "${GEMINI_API_KEY:-}" ]] || [[ -n "${ANTHROPIC_API_KEY:-}" ]] || [[ -n "${OPENAI_API_KEY:-}" ]] || [[ -n "${GROQ_API_KEY:-}" ]] || [[ -n "${DEEPSEEK_API_KEY:-}" ]] || [[ -n "${MISTRAL_API_KEY:-}" ]]; then
    any_key_found=true
  else
    any_key_found=false
  fi

  if [[ "$any_key_found" == "false" ]]; then
    cat <<'BANNER' >&2

================================================================================
  NO PROVIDER API KEY DETECTED
================================================================================
  GitAgent needs a language-model API key to power the turn-taking
  orchestrator, persona interviewers, drafters, and council editors.

  Supported providers and example exports:
    export OPENROUTER_API_KEY="sk-or-..."
      # Recommended: cost-effective Gemini 2.5 Flash / Pro and
      # Claude via OpenRouter
    export GEMINI_API_KEY="..."
    export ANTHROPIC_API_KEY="sk-ant-..."
    export OPENAI_API_KEY="sk-..."
    export GROQ_API_KEY="gsk_..."
    export DEEPSEEK_API_KEY="sk-..."
    export MISTRAL_API_KEY="..."

  You can also pass a model explicitly:
    ./gitagent.sh --model <provider:model-id>
    or set GITAGENT_MODEL=<provider:model-id>
================================================================================

BANNER
    exit 1
  fi

  # Resolve default model based on detected keys (priority order)
  if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
    DEFAULT_MODEL="openrouter:google/gemini-2.5-flash"
  elif [[ -n "${GEMINI_API_KEY:-}" ]]; then
    DEFAULT_MODEL="google:gemini-2.5-flash"
  elif [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
    DEFAULT_MODEL="anthropic:claude-sonnet-4-5-20250929"
  elif [[ -n "${OPENAI_API_KEY:-}" ]]; then
    DEFAULT_MODEL="openai:gpt-4o"
  fi

  if [[ -n "${DEFAULT_MODEL:-}" ]]; then
    echo "Auto-detected provider; using default model: ${DEFAULT_MODEL}"
    set -- --model "${DEFAULT_MODEL}" "$@"
  else
    cat <<'BANNER' >&2

================================================================================
  PROVIDER KEY DETECTED, BUT NO DEFAULT MODEL AVAILABLE
================================================================================
  GitAgent found an API key for GROQ_API_KEY, DEEPSEEK_API_KEY, or
  MISTRAL_API_KEY, but these providers do not yet have a default model
  mapping, so a model cannot be auto-resolved.

  Pass a model explicitly:
    ./gitagent.sh --model <provider:model-id>
    or set GITAGENT_MODEL=<provider:model-id>
================================================================================

BANNER
    exit 1
  fi
fi

exec gitagent --dir "${SCRIPT_DIR}" "$@"
