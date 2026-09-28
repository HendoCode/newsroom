#!/usr/bin/env bash
# Launch a PARALLEL ISOLATED instance of the full stack (docs/design.md §6).
#
# Each instance gets its own compose project name (isolated container/network/image
# namespaces), its own host ports (derived from a base), and its own ephemeral tmpfs mongo —
# so multiple worktrees/agents run concurrently with zero collisions. `web` is HTTPS-only
# (docker-compose.override.yml's `edge` service — docs/local-dev.md "Local HTTPS"); the web port
# below is the HTTPS port for that instance, e.g. `https://localhost:3100`, not a plain-HTTP
# port. This script passes both compose files explicitly (below) since an explicit `-f` disables
# Compose's automatic override-file discovery — a bare `docker compose up` gets the same effect
# by relying on that discovery instead.
#
# Usage:
#   scripts/instance.sh <instance-name> [base-port] [-- <docker compose args>]
#
# Examples:
#   scripts/instance.sh alice                 # up (foreground), project cmw-alice, ports 3100-3102
#   scripts/instance.sh bob 3200 -- --build -d # up --build -d, project cmw-bob, ports 3200-3202
#   scripts/instance.sh bob 3200 -- down -v    # tear that instance down
#   scripts/instance.sh bob 3200 -- ps         # inspect it
#
# Bare compose flags (starting with '-') are treated as args to `up`; a leading subcommand
# (down/ps/logs/…) is used as-is. The plain `docker compose up` (no script) uses project
# "newsroom" on https 443 / agents 8000 / mongo 27017.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <instance-name> [base-port] [-- <extra docker compose args>]" >&2
  exit 2
fi

INSTANCE="$1"; shift
BASE_PORT="3100"
if [[ $# -gt 0 && "$1" != "--" ]]; then
  BASE_PORT="$1"; shift
fi
if [[ $# -gt 0 && "$1" == "--" ]]; then
  shift
fi

# Derive a non-colliding port triple from the base.
export COMPOSE_PROJECT_NAME="cmw-${INSTANCE}"
export WEB_PORT="${BASE_PORT}"
export AGENTS_PORT="$((BASE_PORT + 1))"
export MONGO_PORT="$((BASE_PORT + 2))"
# docker-compose.override.yml's own AUTH_URL default (https://localhost, no port) only matches
# WEB_PORT's own default (443) — an isolated instance's WEB_PORT is never 443, so it must get its
# own matching AUTH_URL here instead of relying on that default (see the AUTH_URL comments on
# `web` in both compose files for why a mismatch here is a real, previously-hit bug, not a
# nitpick).
# This instance's Google sign-in still won't work unless this exact origin is separately
# registered on the OAuth client (docs/local-dev.md) — only the identity-declaration fallback is
# guaranteed to work on a non-default instance.
export AUTH_URL="https://localhost:${WEB_PORT}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "▶ instance '${INSTANCE}' → project=${COMPOSE_PROJECT_NAME}  web=https://localhost:${WEB_PORT}  agents=${AGENTS_PORT}  mongo=${MONGO_PORT}"

# Default subcommand is `up`; bare flags (e.g. --build -d) are appended to `up`; an explicit
# subcommand (down/ps/logs/…) is passed through unchanged.
if [[ $# -eq 0 ]]; then
  set -- up
elif [[ "$1" == -* ]]; then
  set -- up "$@"
fi

exec docker compose -f "${SCRIPT_DIR}/docker-compose.yml" -f "${SCRIPT_DIR}/docker-compose.override.yml" "$@"
