#!/usr/bin/env bash
# Canonical entry point for the production stack: pins the compose file and
# both env files so no invocation can accidentally run without them.
#   scripts/ops/compose.sh up -d
#   scripts/ops/compose.sh run --rm migrate
#   scripts/ops/compose.sh logs -f api
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../../docker"

for f in .env.production .env.secrets; do
  if [ ! -f "$f" ]; then
    echo "error: docker/$f is missing — copy docker/$f.example and fill it in" >&2
    exit 1
  fi
done

# Optional overlay (Loki) via ATIP_COMPOSE_EXTRA=docker-compose.loki.yml
extra=()
if [ -n "${ATIP_COMPOSE_EXTRA:-}" ]; then
  extra=(-f "$ATIP_COMPOSE_EXTRA")
fi

exec docker compose \
  -f docker-compose.prod.yml "${extra[@]}" \
  --env-file .env.production --env-file .env.secrets \
  "$@"
