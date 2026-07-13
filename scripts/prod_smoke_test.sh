#!/usr/bin/env bash
# ATIP post-deploy smoke test. Verifies a live deployment is healthy and
# running the expected build. Needs only bash + curl (no jq, no Python).
#
# Usage:
#   scripts/prod_smoke_test.sh <BASE_URL> [EXPECTED_BUILD_SHA]
#
#   BASE_URL             e.g. https://api.example.com or http://127.0.0.1:8000
#   EXPECTED_BUILD_SHA   optional; also read from $EXPECTED_BUILD_SHA. When
#                        set, the build_sha reported by /health/live must match.
#
# Checks (in order):
#   1. GET /health/live   -> 200, status "ok"; prints version/environment/build_sha
#   2. build_sha == EXPECTED_BUILD_SHA (only if an expected SHA was given)
#   3. GET /health/ready  -> 200; "ready" passes, "degraded" passes with a
#      warning (serve traffic, fix the optional dependency — see
#      docs/12_RELEASE_RUNBOOK.md), 503 "not_ready" fails.
#
# Exit codes: 0 healthy (possibly degraded), 1 usage error or API unreachable,
#             2 unhealthy (not ready / bad liveness), 3 build_sha mismatch.
#
# /health/live is retried (LIVE_ATTEMPTS x LIVE_RETRY_DELAY seconds, default
# 5 x 2s) so the script can run immediately after container start.

set -u

BASE_URL="${1:-}"
EXPECTED_SHA="${2:-${EXPECTED_BUILD_SHA:-}}"
LIVE_ATTEMPTS="${LIVE_ATTEMPTS:-5}"
LIVE_RETRY_DELAY="${LIVE_RETRY_DELAY:-2}"

if [ -z "$BASE_URL" ]; then
    echo "usage: $0 <BASE_URL> [EXPECTED_BUILD_SHA]" >&2
    exit 1
fi
BASE_URL="${BASE_URL%/}"

fail() { echo "[FAIL] $1" >&2; exit "$2"; }
ok()   { echo "[ ok ] $1"; }
warn() { echo "[WARN] $1"; }

# Extract a top-level string (or null) value from compact or pretty JSON.
json_field() { # json_field <json> <key>
    printf '%s' "$1" \
        | grep -o "\"$2\"[[:space:]]*:[[:space:]]*\(null\|\"[^\"]*\"\)" \
        | head -n 1 \
        | sed -e 's/^[^:]*:[[:space:]]*//' -e 's/^"//' -e 's/"$//'
}

# --- 1. Liveness -------------------------------------------------------------
live_body=""
live_code="000"
attempt=1
while [ "$attempt" -le "$LIVE_ATTEMPTS" ]; do
    live_body="$(curl -sS -m 10 -w '\n%{http_code}' "$BASE_URL/health/live" 2>/dev/null)" && {
        live_code="${live_body##*$'\n'}"
        live_body="${live_body%$'\n'*}"
        [ "$live_code" = "200" ] && break
    }
    [ "$attempt" -lt "$LIVE_ATTEMPTS" ] && sleep "$LIVE_RETRY_DELAY"
    attempt=$((attempt + 1))
done

if [ "$live_code" = "000" ]; then
    fail "API unreachable at $BASE_URL after $LIVE_ATTEMPTS attempts" 1
fi
[ "$live_code" = "200" ] || fail "/health/live returned HTTP $live_code" 2

live_status="$(json_field "$live_body" status)"
version="$(json_field "$live_body" version)"
environment="$(json_field "$live_body" environment)"
build_sha="$(json_field "$live_body" build_sha)"
[ "$live_status" = "ok" ] || fail "/health/live status is '$live_status', expected 'ok'" 2
ok "/health/live 200 — version=$version environment=$environment build_sha=$build_sha"

# --- 2. Build identity --------------------------------------------------------
if [ -n "$EXPECTED_SHA" ]; then
    if [ "$build_sha" = "$EXPECTED_SHA" ]; then
        ok "build_sha matches expected deployment ($EXPECTED_SHA)"
    else
        fail "build_sha mismatch: running '$build_sha', expected '$EXPECTED_SHA' — wrong image deployed?" 3
    fi
else
    warn "no EXPECTED_BUILD_SHA given — skipping build identity check"
fi

# --- 3. Readiness -------------------------------------------------------------
ready_body="$(curl -sS -m 10 -w '\n%{http_code}' "$BASE_URL/health/ready" 2>/dev/null)" \
    || fail "/health/ready unreachable" 1
ready_code="${ready_body##*$'\n'}"
ready_body="${ready_body%$'\n'*}"
ready_status="$(json_field "$ready_body" status)"

case "$ready_code:$ready_status" in
    200:ready)
        ok "/health/ready 200 — ready" ;;
    200:degraded)
        warn "/health/ready 200 — DEGRADED (an optional dependency is down): $ready_body"
        warn "search may be keyword-only; serve traffic and fix the dependency (runbook: Probes & monitoring)" ;;
    *)
        fail "/health/ready HTTP $ready_code status '$ready_status': $ready_body" 2 ;;
esac

echo "[PASS] $BASE_URL is healthy"
