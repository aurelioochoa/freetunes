#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-both}"
# Level forwarded to uvicorn (--log-level) and read by backend/app/logging_setup.py.
LOG_LEVEL="${FREETUNES_LOG_LEVEL:-info}"

# Color follows the terminal (same rule as the Makefile): NO_COLOR wins,
# FORCE_COLOR overrides, otherwise only when stdout is a TTY so log files
# stay clean. Exported when on so backend/vite colors survive the prefix
# pipes below (a pipe is not a TTY, so the children would disable color).
USE_COLOR=0
if [ -z "${NO_COLOR:-}" ]; then
  if [ -n "${FORCE_COLOR:-}" ] || [ -t 1 ]; then USE_COLOR=1; fi
fi
if [ "$USE_COLOR" = 1 ]; then
  export FORCE_COLOR=1
  C_BACKEND="$(printf '\033[36m')"   # cyan: backend daemon
  C_FRONTEND="$(printf '\033[35m')"  # magenta: vite UI
  C_DEV="$(printf '\033[1m')"        # bold: runner banner
  C_DIM="$(printf '\033[2m')"
  C_OFF="$(printf '\033[0m')"
else
  C_BACKEND=""; C_FRONTEND=""; C_DEV=""; C_DIM=""; C_OFF=""
fi

# Tag every line so backend/frontend output no longer interleaves silently:
#   [backend 12:34:56] INFO: ...
#   [frontend 12:34:56] VITE ready in 300 ms
prefix() {
  local tag="$1" color="$2"
  while IFS= read -r line; do
    printf '[%s%s%s %s%s%s] %s\n' \
      "$color" "$tag" "$C_OFF" "$C_DIM" "$(date +%H:%M:%S)" "$C_OFF" "$line"
  done
}

# Ctrl-C (or one side dying) must not orphan the other daemon.
cleanup() {
  kill "$(jobs -p)" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

run_backend() {
  cd "$ROOT/backend"
  if [ ! -d .venv ]; then python3 -m venv .venv; fi
  .venv/bin/pip install -q -r requirements.txt
  # --timeout-graceful-shutdown: a live MJPEG stream must never be able
  # to hold a reload hostage (uvicorn otherwise waits for it forever).
  FREETUNES_MOCK=${FREETUNES_MOCK:-0} .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --log-level "$LOG_LEVEL" --timeout-graceful-shutdown 5 2>&1 | prefix "backend" "$C_BACKEND"
}

run_frontend() {
  cd "$ROOT/frontend"
  if [ ! -d node_modules ]; then pnpm install; fi
  pnpm dev 2>&1 | prefix "frontend" "$C_FRONTEND"
}

case "$MODE" in
  backend) run_backend ;;
  frontend) run_frontend ;;
  *)
    printf '%s[dev %s]%s backend=http://127.0.0.1:8000 ui=http://127.0.0.1:5173 mock=${FREETUNES_MOCK:-0} log=%s\n' "$C_DEV" "$(date +%H:%M:%S)" "$C_OFF" "$LOG_LEVEL"
    run_backend & run_frontend & wait ;;
esac
