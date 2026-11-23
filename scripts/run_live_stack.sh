#!/usr/bin/env bash
# Starts a throwaway PostgreSQL + FastAPI + Vite stack for live end-to-end testing.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PGDATA=/tmp/vk_pgdata
export DATABASE_URL=postgresql://postgres@127.0.0.1:55432/vyaapardb
export ENV=development

rm -f /tmp/.s.PGSQL.55432* "$PGDATA/postmaster.pid"
postgres -D "$PGDATA" -p 55432 -h 127.0.0.1 -k /tmp >/tmp/vk_live_pg.log 2>&1 &
for _ in $(seq 1 30); do pg_isready -h 127.0.0.1 -p 55432 >/dev/null 2>&1 && break; sleep 0.5; done

(cd "$ROOT/backend" && ../.venv/bin/alembic upgrade head >/tmp/vk_live_alembic.log 2>&1)
(cd "$ROOT/backend" && ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 >/tmp/vk_live_api.log 2>&1) &
(cd "$ROOT/frontend" && npm run dev -- --host 127.0.0.1 >/tmp/vk_live_vite.log 2>&1) &
wait
