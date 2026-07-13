#!/bin/sh
# Backend container entrypoint: bring the database schema up to date, then run
# whatever command was passed (uvicorn in dev/prod). Runs on every start; if the
# schema is already current, `alembic upgrade head` is a no-op.
set -e

echo "[entrypoint] applying database migrations (alembic upgrade head)..."

# The db service is gated by depends_on: service_healthy, but retry briefly in
# case the connection isn't accepting queries the instant the healthcheck flips.
attempt=1
max_attempts=10
until alembic upgrade head; do
  if [ "$attempt" -ge "$max_attempts" ]; then
    echo "[entrypoint] migrations failed after ${max_attempts} attempts; aborting." >&2
    exit 1
  fi
  echo "[entrypoint] migration attempt ${attempt} failed; retrying in 2s..."
  attempt=$((attempt + 1))
  sleep 2
done

echo "[entrypoint] migrations applied; starting backend."
exec "$@"
