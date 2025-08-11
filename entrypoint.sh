#!/bin/sh
set -e

export PYTHONUNBUFFERED=1

EMBEDDED_SERVICES=${EMBEDDED_SERVICES:-$([ -z "${DATABASE_URL:-}" ] && echo "true" || echo "false")}

POSTGRES_USER=${POSTGRES_USER:-stocks}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-stocks}
POSTGRES_DB=${POSTGRES_DB:-stocks}
PGDATA=${PGDATA:-/var/lib/postgresql/data}

if [ "${EMBEDDED_SERVICES}" = "true" ]; then
  export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:5432/${POSTGRES_DB}}"
  export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
fi

start_postgres() {
  echo "[entrypoint] Starting PostgreSQL"
  
  if ! command -v initdb >/dev/null 2>&1; then
    PGBIN="$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | tail -n1)"
    if [ -n "$PGBIN" ]; then
      export PATH="$PGBIN:$PATH"
    else
      echo "[entrypoint] ERROR: PostgreSQL binaries not found"
      exit 1
    fi
  fi
  
  mkdir -p "$PGDATA"
  chown -R postgres:postgres "$PGDATA"

  if [ ! -s "$PGDATA/PG_VERSION" ]; then
    runuser -u postgres -- initdb -D "$PGDATA" -E UTF8 -U postgres
    echo "listen_addresses = 'localhost'" >> "$PGDATA/postgresql.conf"
    echo "host all all 127.0.0.1/32 md5" >> "$PGDATA/pg_hba.conf"
  fi

  runuser -u postgres -- pg_ctl -D "$PGDATA" -w start

  if ! runuser -u postgres -- psql -U postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='${POSTGRES_USER}'" | grep -q 1; then
    runuser -u postgres -- psql -U postgres -c "CREATE ROLE ${POSTGRES_USER} LOGIN PASSWORD '${POSTGRES_PASSWORD}'"
  fi
  if ! runuser -u postgres -- psql -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${POSTGRES_DB}'" | grep -q 1; then
    runuser -u postgres -- psql -U postgres -c "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER}"
  fi
}

start_redis() {
  echo "[entrypoint] Starting Redis"
  redis-server --save "" --appendonly no --daemonize yes
}

stop_services() {
  echo "[entrypoint] Stopping services..."
  [ ! -z "${UVICORN_PID:-}" ] && kill -TERM $UVICORN_PID 2>/dev/null || true
  
  if [ "${EMBEDDED_SERVICES}" = "true" ]; then
    redis-cli shutdown 2>/dev/null || true
    if [ -s "$PGDATA/PG_VERSION" ]; then
      if ! command -v pg_ctl >/dev/null 2>&1; then
        PGBIN="$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | tail -n1)"
        [ -n "$PGBIN" ] && export PATH="$PGBIN:$PATH"
      fi
      runuser -u postgres -- pg_ctl -D "$PGDATA" -m fast stop || true
    fi
  fi
  
  echo "[entrypoint] Goodbye!"
}

trap stop_services INT TERM

if [ "${EMBEDDED_SERVICES}" = "true" ]; then
  start_postgres
  start_redis
fi

uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log &
UVICORN_PID=$!
sleep 2

if kill -0 $UVICORN_PID 2>/dev/null; then
  echo ""
  echo "╭─────────────────────────────────────────────────────────────╮"
  echo "│                      STOCKS API SERVER                      │"
  echo "├─────────────────────────────────────────────────────────────┤"
  echo "│  Status:  Running successfully                              │"
  echo "│  Port:    http://localhost:8000                             │"
  echo "│  Swagger: http://localhost:8000/docs                        │"
  echo "│                                                             │"
  echo "│    Some Available Endpoints:                                │"
  echo "│  • Health Check:     /health                                │"
  echo "│  • Stock Data:       /stock/{symbol}                        │"
  echo "│                                                             │"
  echo "│  Quick Start:                                               │"
  echo "│  curl http://localhost:8000/health                          │"
  echo "│  curl http://localhost:8000/stock/AAPL                      │"
  echo "│                                                             │"
  echo "│  Press CTRL+C to stop the server                            │"
  echo "╰─────────────────────────────────────────────────────────────╯"
  echo ""
  wait $UVICORN_PID
else
  echo "[entrypoint] ERROR: Failed to start API"
  exit 1
fi
