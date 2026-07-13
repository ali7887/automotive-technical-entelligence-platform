#!/usr/bin/env bash
# Qdrant collection backup via the snapshot API.
#
#   scripts/ops/backup_qdrant.sh
#
# Creates a server-side snapshot (wait=true so it is complete before we
# touch it), copies it out of the container, verifies the copy's size against
# what the API reported, then deletes the server-side snapshot so the qdrant
# disk does not fill up. If the collection does not exist yet (no documents
# embedded), exits 0 with a notice — nothing to back up is not a failure.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
compose="$here/compose.sh"
backup_root="${ATIP_BACKUP_DIR:-/var/backups/atip}"
dir="$backup_root/qdrant"
mkdir -p "$dir"

collection="$(grep -E '^QDRANT_COLLECTION=' "$here/../../docker/.env.production" | head -n1 | cut -d= -f2-)"
collection="${collection:-atip_chunks}"

qcurl() { "$compose" run --rm --quiet-pull ops-curl -sf "$@"; }

if ! qcurl "http://qdrant:6333/collections/$collection" > /dev/null 2>&1; then
  echo "notice: collection '$collection' does not exist yet; nothing to back up"
  exit 0
fi

echo "==> creating snapshot of '$collection'"
resp="$(qcurl -X POST "http://qdrant:6333/collections/$collection/snapshots?wait=true")"
name="$(printf '%s' "$resp" | grep -o '"name"[[:space:]]*:[[:space:]]*"[^"]*"' | head -n1 | sed -e 's/.*:[[:space:]]*"//' -e 's/"$//')"
reported_size="$(printf '%s' "$resp" | grep -o '"size"[[:space:]]*:[[:space:]]*[0-9]*' | head -n1 | grep -o '[0-9]*$')"
if [ -z "$name" ]; then
  echo "error: snapshot API returned no name: $resp" >&2
  exit 1
fi

out="$dir/$name"
echo "==> copying snapshot out -> $out"
"$compose" cp "qdrant:/qdrant/snapshots/$collection/$name" "$out"

echo "==> deleting server-side snapshot"
qcurl -X DELETE "http://qdrant:6333/collections/$collection/snapshots/$name" > /dev/null

size=$(wc -c < "$out")
if [ "$size" -eq 0 ] || { [ -n "$reported_size" ] && [ "$size" -ne "$reported_size" ]; }; then
  rm -f "$out"
  echo "error: snapshot copy size $size != reported $reported_size; backup removed" >&2
  exit 1
fi

echo "ok: $out ($size bytes)"
