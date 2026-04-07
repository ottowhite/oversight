#!/usr/bin/env bash
set -euo pipefail

# Derive a unique project name from the current directory.
# This lets multiple worktrees run side-by-side without container/network conflicts.
PROJECT_NAME="oversight-$(basename "$(pwd)")"

# Find the first available port starting from $1.
find_port() {
  local port=$1
  while ss -tln 2>/dev/null | grep -q ":${port} " \
     || lsof -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; do
    port=$((port + 1))
  done
  echo "$port"
}

BACKEND_PORT=$(find_port 5001)
FRONTEND_PORT=$(find_port 3000)

echo "=== oversight dev ($PROJECT_NAME) ==="
echo "  Backend:  http://localhost:${BACKEND_PORT}"
echo "  Frontend: http://localhost:${FRONTEND_PORT}"
echo ""

export COMPOSE_PROJECT_NAME="$PROJECT_NAME"
export BACKEND_PORT
export FRONTEND_PORT

docker compose -f docker-compose.dev.yml up --build "$@"
