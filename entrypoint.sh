#!/bin/sh
set -e

export PYTHONUNBUFFERED=1

if [ -z "${DATABASE_URL:-}" ]; then
  EMBEDDED_SERVICES=true
else
  EMBEDDED_SERVICES=${EMBEDDED_SERVICES:-false}
fi

POSTGRES_USER=${POSTGRES_USER:-stocks}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-stocks}
POSTGRES_DB=${POSTGRES_DB:-stocks}
PGDATA=${PGDATA:-/var/lib/postgresql/data}

if [ "${EMBEDDED_SERVICES}" = "true" ]; then
  [ -z "${DATABASE_URL:-}" ] && export DATABASE_URL="postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:5432/${POSTGRES_DB}"
  [ -z "${REDIS_URL:-}" ] && export REDIS_URL="redis://127.0.0.1:6379/0"
fi

find_pg_bin() {
  if command -v initdb >/dev/null 2>&1; then
    PGBIN="$(dirname "$(command -v initdb)")"
  elif command -v pg_config >/dev/null 2>&1; then
    PGBIN="$(pg_config --bindir)"
  else
    PGBIN="$(ls -d /usr/lib/postgresql/*/bin 2>/dev/null | sort -V | tail -n1 || true)"
  fi
  if [ -z "${PGBIN:-}" ] || [ ! -x "$PGBIN/initdb" ]; then
    echo "[entrypoint] ERROR: PostgreSQL binaries not found (initdb missing)."
    echo "[entrypoint] Ensure 'postgresql' is installed in the image or adjust PATH."
    exit 1
  fi
  export PATH="$PGBIN:$PATH"
  PG_INITDB="$PGBIN/initdb"
  PG_CTL="$PGBIN/pg_ctl"
  PSQL="$PGBIN/psql"
  PG_ISREADY="$PGBIN/pg_isready"
  echo "[entrypoint] Using PostgreSQL bin at $PGBIN"
}

start_postgres() {
  echo "[entrypoint] Starting PostgreSQL"
  mkdir -p "$PGDATA"
  chown -R postgres:postgres "$PGDATA"

  find_pg_bin

  if [ ! -s "$PGDATA/PG_VERSION" ]; then
    echo "[entrypoint] Initializing data dir at $PGDATA"
    runuser -u postgres -- sh -c "\"$PG_INITDB\" -D '$PGDATA' -E UTF8 -U postgres"
    echo "listen_addresses = 'localhost'" >> "$PGDATA/postgresql.conf"
    echo "host all all 127.0.0.1/32 md5" >> "$PGDATA/pg_hba.conf"
  fi

  runuser -u postgres -- sh -c "\"$PG_CTL\" -D '$PGDATA' -o '-p 5432 -c listen_addresses=localhost' -w start"

  if ! runuser -u postgres -- sh -c "\"$PSQL\" -U postgres -tAc 'SELECT 1 FROM pg_roles WHERE rolname='\''${POSTGRES_USER}'\'''" | grep -q 1; then
    runuser -u postgres -- sh -c "\"$PSQL\" -U postgres -c 'CREATE ROLE ${POSTGRES_USER} LOGIN PASSWORD '\''${POSTGRES_PASSWORD}'\'''"
  fi

  if ! runuser -u postgres -- sh -c "\"$PSQL\" -U postgres -tAc 'SELECT 1 FROM pg_database WHERE datname='\''${POSTGRES_DB}'\'''" | grep -q 1; then
    runuser -u postgres -- sh -c "\"$PSQL\" -U postgres -c 'CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER}'"
  fi

  for i in 1 2 3 4 5 6 7 8 9 10; do
    if runuser -u postgres -- sh -c "\"$PG_ISREADY\" -q"; then
      break
    fi
    sleep 1
  done
}

start_redis() {
  echo "[entrypoint] Starting Redis"
  redis-server --save "" --appendonly no --daemonize yes
  for i in 1 2 3 4 5; do
    if nc -z 127.0.0.1 6379 >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
}

stop_services() {
  echo "[entrypoint] Stopping services"
  if nc -z 127.0.0.1 6379 >/dev/null 2>&1; then
    redis-cli shutdown || true
  fi
  if [ -s "$PGDATA/PG_VERSION" ]; then
    find_pg_bin || true
    runuser -u postgres -- sh -c "\"$PG_CTL\" -D '$PGDATA' -m fast stop" || true
  fi
}

trap stop_services INT TERM

if [ "${EMBEDDED_SERVICES}" = "true" ]; then
  start_postgres
  start_redis
else
  echo "[entrypoint] Using external services"
fi

echo "[entrypoint] Starting API"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
