#!/usr/bin/env bash
# Restore a Qdrant collection snapshot produced by backup_qdrant.sh.
# Replaces the collection contents (priority=snapshot); creates the
# collection if it does not exist.
#
#   scripts/ops/restore_qdrant.sh <snapshot-file> --yes
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
compose="$here/compose.sh"

snap="${1:-}"
confirm="${2:-}"
if [ -z "$snap" ] || [ ! -f "$snap" ]; then
  echo "usage: $0 <snapshot-file> --yes" >&2
  exit 1
fi
if [ "$confirm" != "--yes" ]; then
  echo "refusing: restore REPLACES the collection. Re-run with --yes." >&2
  exit 1
fi

collection="$(grep -E '^QDRANT_COLLECTION=' "$here/../../docker/.env.production" | head -n1 | cut -d= -f2-)"
collection="${collection:-atip_chunks}"

name="$(basename "$snap")"
case "$(uname -s)" in
  MINGW*|MSYS*) abs="$(cygpath -m "$snap")" ;;  # docker needs C:/… not /c/…
  *) abs="$(cd "$(dirname "$snap")" && pwd)/$name" ;;
esac

echo "==> uploading $name into collection '$collection'"
# -F sets the multipart Content-Type (with boundary) itself — never add
# an explicit Content-Type header here, it would drop the boundary.
"$compose" run --rm -v "$abs:/snapshots/$name:ro" ops-curl -sf \
  -X POST "http://qdrant:6333/collections/$collection/snapshots/upload?priority=snapshot" \
  -F "snapshot=@/snapshots/$name"
echo

echo "==> verifying collection"
"$compose" run --rm ops-curl -sf "http://qdrant:6333/collections/$collection" \
  | grep -o '"points_count"[^,}]*' || true
echo
echo "restore complete — vectors older than the postgres restore point are"
echo "reconciled by document reprocessing (chunk IDs are deterministic)."
