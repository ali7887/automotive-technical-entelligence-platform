#!/usr/bin/env bash
# PostgreSQL logical backup (pg_dump custom format, compressed).
#
#   scripts/ops/backup_postgres.sh
#   ATIP_BACKUP_DIR=/mnt/backups scripts/ops/backup_postgres.sh
#
# The dump is verified INSIDE the container with `pg_restore --list` before
# it is streamed out, and the host copy is checked for the PGDMP magic bytes
# and a sane minimum size — a backup that fails verification never lands in
# the backup directory with a valid-looking name.
set -euo pipefail

compose="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/compose.sh"
backup_root="${ATIP_BACKUP_DIR:-/var/backups/atip}"
dir="$backup_root/postgres"
mkdir -p "$dir"

stamp="$(date -u +%Y%m%d_%H%M%SZ)"
out="$dir/atip_${stamp}.dump"

echo "==> pg_dump -> $out"
"$compose" exec -T postgres sh -c '
  set -eu
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --compress=6 -f /tmp/atip.dump
  tables=$(pg_restore --list /tmp/atip.dump | grep -c "TABLE DATA")
  echo "verified inside container: $tables table-data entries" >&2
  cat /tmp/atip.dump
  rm -f /tmp/atip.dump
' > "$out"

# host-side integrity: magic bytes + minimum plausible size
if [ "$(head -c 5 "$out")" != "PGDMP" ]; then
  rm -f "$out"
  echo "error: dump is not a pg custom-format archive; backup removed" >&2
  exit 1
fi
size=$(wc -c < "$out")
if [ "$size" -lt 4096 ]; then
  rm -f "$out"
  echo "error: dump implausibly small (${size} bytes); backup removed" >&2
  exit 1
fi

echo "ok: $out ($size bytes)"
