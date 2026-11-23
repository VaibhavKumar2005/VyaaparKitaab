#!/usr/bin/env bash
# Boots the live stack, runs the HTTP end-to-end check against it, then tears everything down.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
bash "$ROOT/scripts/run_live_stack.sh" &
STACK=$!
"$ROOT/.venv/bin/python" "$ROOT/scripts/e2e_live_check.py"
rc=$?
kill $(jobs -p) 2>/dev/null
pkill -f "uvicorn app.main:app" 2>/dev/null
pkill -f "vite" 2>/dev/null
pg_ctl -D /tmp/vk_pgdata stop >/dev/null 2>&1
exit $rc
