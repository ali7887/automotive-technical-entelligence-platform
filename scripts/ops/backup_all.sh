#!/usr/bin/env bash
# Full backup run + retention. Intended for cron; also fine manually.
#
#   scripts/ops/backup_all.sh
#
# Retention: last 7 runs per store ("daily"), plus — on Sundays — the newest
# artifact is copied into <store>/weekly/, where the last 4 are kept.
# Any individual backup failure makes this script exit non-zero (so cron
# mails/alerts fire), but the remaining stores are still attempted.
#
# Cron example (as the deploy user, docker access required):
#   15 3 * * * cd /opt/atip && ./scripts/ops/backup_all.sh >> /var/log/atip-backup.log 2>&1
set -uo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
backup_root="${ATIP_BACKUP_DIR:-/var/backups/atip}"

failed=()
for store in postgres uploads qdrant; do
  if ! "$here/backup_${store}.sh"; then
    failed+=("$store")
  fi
done

prune() { # $1 = dir, $2 = keep-count
  [ -d "$1" ] || return 0
  ls -1t "$1" | grep -v '^weekly$' | tail -n +"$(( $2 + 1 ))" | while read -r f; do
    echo "prune: $1/$f"
    rm -f -- "$1/$f"
  done
}

for store in postgres uploads qdrant; do
  dir="$backup_root/$store"
  [ -d "$dir" ] || continue
  # Sunday: promote the newest artifact to the weekly tier
  if [ "$(date -u +%u)" = "7" ]; then
    newest="$(ls -1t "$dir" | grep -v '^weekly$' | head -n1 || true)"
    if [ -n "$newest" ]; then
      mkdir -p "$dir/weekly"
      cp -f -- "$dir/$newest" "$dir/weekly/$newest"
      echo "weekly: $dir/weekly/$newest"
    fi
  fi
  prune "$dir" 7
  prune "$dir/weekly" 4
done

if [ "${#failed[@]}" -gt 0 ]; then
  echo "BACKUP FAILED for: ${failed[*]}" >&2
  exit 1
fi
echo "backup run complete: $backup_root"
