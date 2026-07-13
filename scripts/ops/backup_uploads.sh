#!/usr/bin/env bash
# Backup of STORAGE_DIR (uploaded PDFs) — the only copy of the source files.
# Postgres rows reference these paths; losing them orphans documents.
#
#   scripts/ops/backup_uploads.sh
set -euo pipefail

compose="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/compose.sh"
backup_root="${ATIP_BACKUP_DIR:-/var/backups/atip}"
dir="$backup_root/uploads"
mkdir -p "$dir"

stamp="$(date -u +%Y%m%d_%H%M%SZ)"
out="$dir/uploads_${stamp}.tar.gz"

echo "==> archiving /data/uploads -> $out"
# single sh -c string: identical on linux and immune to MSYS path mangling
if ! "$compose" exec -T api sh -c 'tar -czf - -C /data uploads' > "$out"; then
  rm -f "$out"
  echo "error: archive step failed; partial backup removed" >&2
  exit 1
fi

# integrity: the archive must be readable end-to-end on the host
# (relative path: GNU tar misreads absolute paths containing ':' as remote hosts)
if ! entries=$(cd "$dir" && tar -tzf "${out##*/}" | wc -l); then
  rm -f "$out"
  echo "error: archive unreadable; backup removed" >&2
  exit 1
fi
size=$(wc -c < "$out")
echo "ok: $out ($size bytes, $entries entries)"
