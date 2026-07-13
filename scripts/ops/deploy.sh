#!/usr/bin/env bash
# Build, migrate, roll, verify — one release of the ATIP stack.
#
#   scripts/ops/deploy.sh [git-ref]     # default: HEAD
#
# Steps: build both images tagged with the commit SHA -> pin ATIP_TAG and
# BUILD_SHA in docker/.env.production -> run migrations once -> roll the
# stack -> smoke test through the public URL. Aborts on the first failure;
# rollback = re-run with the previous SHA (images are kept).
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
compose="$repo/scripts/ops/compose.sh"
env_file="$repo/docker/.env.production"

ref="${1:-HEAD}"
sha="$(git -C "$repo" rev-parse "$ref")"
short="${sha:0:12}"

# refuse to deploy uncommitted code: the tag must mean something
if [ "$ref" = "HEAD" ] && [ -n "$(git -C "$repo" status --porcelain --untracked-files=no)" ]; then
  echo "error: working tree has uncommitted changes; commit first or pass an explicit ref" >&2
  exit 1
fi

domain="$(grep -E '^ATIP_DOMAIN=' "$env_file" | head -n1 | cut -d= -f2-)"
if [ -z "$domain" ]; then
  echo "error: ATIP_DOMAIN not set in docker/.env.production" >&2
  exit 1
fi

echo "==> deploying $sha to https://$domain"

echo "==> building atip-api:$short"
docker build -t "atip-api:$short" "$repo/apps/api"

echo "==> building atip-web:$short (NEXT_PUBLIC_API_URL=https://$domain)"
docker build -f "$repo/apps/web/Dockerfile" \
  --build-arg NEXT_PUBLIC_API_URL="https://$domain" \
  -t "atip-web:$short" "$repo"

echo "==> pinning ATIP_TAG/BUILD_SHA in docker/.env.production"
tmp="$(mktemp)"
grep -vE '^(ATIP_TAG|BUILD_SHA)=' "$env_file" > "$tmp"
printf 'ATIP_TAG=%s\nBUILD_SHA=%s\n' "$short" "$sha" >> "$tmp"
mv "$tmp" "$env_file"

echo "==> running migrations (one-shot, before the app rolls)"
"$compose" run --rm migrate

echo "==> rolling the stack"
"$compose" up -d --remove-orphans

echo "==> smoke test"
"$repo/scripts/prod_smoke_test.sh" "https://$domain" "$sha"

echo "==> deployed $sha"
