#!/usr/bin/env bash
set -euo pipefail

# Start/Restart Oversight: Flask backend + Next.js frontend (dev)
# - Exports NEXT_PUBLIC_BACKEND_URL for the frontend
# - Restarts any existing instances
# - Streams logs to ./logs/

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$BASE_DIR/logs"
mkdir -p "$LOG_DIR"

export NEXT_PUBLIC_BACKEND_URL="http://localhost:5001"
export FLASK_PORT="5001"

kill_matching() {
  local pattern="$1"
  if pgrep -f "$pattern" >/dev/null 2>&1; then
    echo "Killing processes matching: $pattern"
    # Try graceful stop
    pkill -TERM -f "$pattern" || true
    sleep 1
    # Force kill if still alive
    pkill -KILL -f "$pattern" || true
  fi
}

start_flask() {
  echo "Starting Flask backend on port $FLASK_PORT..."
  (
    cd "$BASE_DIR"
    # Run in background; write PID file and log output
    nohup python "$BASE_DIR/flask_app.py" \
      >"$LOG_DIR/flask_app.log" 2>&1 &
    echo $! > "$LOG_DIR/flask_app.pid"
  )
}

start_next_dev() {
  echo "Starting Next.js dev server (frontend) on port 3000..."
  (
    cd "$BASE_DIR/frontend"
    # Ensure deps are installed (optional fast check)
    if [ ! -d node_modules ]; then
      echo "Installing frontend dependencies..."
      npm install
    fi
    # Run in background; write PID file and log output
    nohup npm run dev \
      >"$LOG_DIR/next_dev.log" 2>&1 &
    echo $! > "$LOG_DIR/next_dev.pid"
  )
}

main() {
  echo "Exported NEXT_PUBLIC_BACKEND_URL=$NEXT_PUBLIC_BACKEND_URL"

  # Kill any existing Flask/Next dev processes
  kill_matching "flask_app.py"
  kill_matching "next dev"
  # Also catch next binary directly if launched via node_modules
  kill_matching "node .*next.*dev"

  # Start fresh instances
  start_flask
  start_next_dev

  echo "Logs: $LOG_DIR"
  echo "Flask:   http://localhost:$FLASK_PORT  (logs: $LOG_DIR/flask_app.log)"
  echo "Next.js: http://localhost:3000        (logs: $LOG_DIR/next_dev.log)"
}

main "$@"
