#!/usr/bin/env sh
set -eu

if [ "${OPEN_CHAT_RELAY_RUN_MIGRATIONS:-true}" = "true" ]; then
  .venv/bin/alembic upgrade head
fi

exec "$@"
