#!/usr/bin/env bash
# Restore a PostgreSQL backup produced by backup_postgres.sh. DESTRUCTIVE:
# replaces the current database contents with the dump.
#
#   scripts/ops/restore_postgres.sh <dump-file> --yes
#
# Full disaster-recovery order (postgres -> uploads -> qdrant -> validate):
# docs/15_BACKUP_AND_RECOVERY.md
set -euo pipefail

compose="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/compose.sh"

dump="${1:-}"
confirm="${2:-}"
if [ -z "$dump" ] || [ ! -f "$dump" ]; then
  echo "usage: $0 <dump-file> --yes" >&2
  exit 1
fi
if [ "$confirm" != "--yes" ]; then
  echo "refusing: restore REPLACES the live database. Re-run with --yes." >&2
  exit 1
fi
if [ "$(head -c 5 "$dump")" != "PGDMP" ]; then
  echo "error: $dump is not a pg_dump custom-format archive" >&2
  exit 1
fi

echo "==> stopping api (no writes during restore)"
"$compose" stop api

echo "==> restoring $dump"
# --clean --if-exists: drop and recreate objects from the dump.
# Single-threaded on purpose: custom-format restore from stdin cannot use -j.
"$compose" exec -T postgres sh -c \
  'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' \
  < "$dump"

echo "==> bringing the schema to the running release's head"
"$compose" run --rm migrate

echo "==> starting api"
"$compose" start api

echo "restore complete — now run the smoke test (docs/15_BACKUP_AND_RECOVERY.md, step 5)"
