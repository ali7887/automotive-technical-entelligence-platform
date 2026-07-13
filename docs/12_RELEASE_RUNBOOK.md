# Release Runbook

Operational guide for deploying, verifying, and rolling back ATIP —
release semantics that hold on any platform. The concrete single-VPS
deployment (compose stack, reverse proxy/TLS, backups, log shipping) has its
own runbooks: `docs/14_PRODUCTION_DEPLOYMENT.md`,
`docs/15_BACKUP_AND_RECOVERY.md`, `docs/16_OBSERVABILITY.md`.
Configuration reference: `.env.example` (every variable, purpose, and
production requirements); provisioning checklist with sources and secret
levels: `docs/13_PROVISIONING_CHECKLIST.md`. Dev setup: `README.md`.

## Topology assumptions

- **API**: one container from `apps/api/Dockerfile` (uvicorn, port 8000,
  non-root). Single process per container; scale by adding containers.
- **Web**: `apps/web` builds with `next build` (Vercel or any Node host).
  `NEXT_PUBLIC_API_URL` is baked into the bundle **at build time** — changing
  the API URL requires a web rebuild.
- **State**: PostgreSQL 16 + pgvector (system of record), Qdrant (vectors),
  Redis (currently health-check only), and a **persistent volume** mounted at
  `STORAGE_DIR` for uploaded PDFs. Losing the volume orphans documents:
  rows survive, files don't — re-upload is the only recovery.
- The API image sets `ENVIRONMENT=production` and refuses to boot with
  dev-default DB credentials or a relative `STORAGE_DIR`.

## Deploy order

1. **Back up Postgres** (`pg_dump`) before any release containing a migration.
2. **Migrate**, using the same image as the release:
   `docker run --rm --env-file prod.env atip-api alembic upgrade head`
   Migrations run once, before new app containers start — never per-container.
3. **Roll the API**: start new containers, wait for `/health/ready` = 200,
   then retire old ones.
4. **Deploy the web app** (if it changed). API first: the API tolerates old
   web clients (`expected_version` and other Phase 6 fields are optional),
   but a new web build may reference new API fields.
5. **Verify** (next section).

Rolling/partial release: all migrations so far are additive or
default-backfilled, so old and new API code can briefly share a schema.
Check each future migration for this property before assuming it.

## Post-deploy verification

First gate — the standalone smoke script (bash + curl only, no repo checkout
of Python deps needed; CI runs the same script against its E2E server):

```bash
scripts/prod_smoke_test.sh https://api.example.com "$EXPECTED_BUILD_SHA"
```

It verifies `/health/live` (with retries for a just-started container), that
the reported `build_sha` is the release you meant to ship, and `/health/ready`.
Exit codes: 0 healthy (a `degraded` readiness passes **with a warning** — see
Probes & monitoring), 1 unreachable, 2 unhealthy, 3 wrong build deployed.

Deeper: the full release smoke suite against the deployment (LLM-free,
creates and deletes its own workspace):

```bash
cd apps/api
ATIP_E2E_BASE_URL=https://api.example.com uv run pytest tests_e2e -q
```

Manual minimum, in order:
1. `GET /health/live` → 200, expected `version`/`build_sha`.
2. `GET /health/ready` → 200 `"ready"` (a `"degraded"` body names the
   failing optional service).
3. `GET /health` → 200 with `postgres.detail` = `migrated (rev <head>)`.
4. Upload a small text PDF → document reaches `READY`; search finds its text.
5. Upload a corrupt file → 422 `application/problem+json`, code `pdf_corrupted`.
6. Logs are one-line JSON and carry `request_id`.

## Probes & monitoring

| Endpoint | Meaning | Use as |
|---|---|---|
| `/health/live` | process is up; never touches dependencies | liveness probe |
| `/health/ready` | Postgres reachable+migrated required; Redis/Qdrant failures → 200 `"degraded"` | readiness probe |
| `/health` | strict: everything ok or 503 | dashboards, post-deploy checks |

**Healthy but degraded** (`/health/ready` 200 with `"degraded"`): Qdrant or
Redis is down. Search continues keyword-only (`semantic_used: false`),
uploads still ingest (chunks persist unembedded and are picked up on
reprocess). Serve traffic, fix the dependency, don't evict instances.
This is why readiness returns **200** for degraded: an orchestrator that
keyed on the body instead of the status code would drain still-useful
capacity. Alert on `"degraded"` from your monitoring, don't route on it.

### Orchestrator probe configuration

Both probes are cheap GETs on port 8000. Liveness never touches
dependencies, so it can be aggressive without risking restart loops during a
dependency outage; readiness gives Postgres checks a little more time.
The container image also ships its own Docker `HEALTHCHECK` on
`/health/live` (used by plain `docker run` and Compose automatically).

**Kubernetes**

```yaml
livenessProbe:
  httpGet: { path: /health/live, port: 8000 }
  initialDelaySeconds: 5
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 3        # ~30s of a dead process before restart
readinessProbe:
  httpGet: { path: /health/ready, port: 8000 }
  initialDelaySeconds: 5
  periodSeconds: 10
  timeoutSeconds: 5          # readiness pings Postgres; allow for it
  failureThreshold: 2        # out of rotation after ~20s not_ready
```

Only 503 `not_ready` (Postgres unreachable or unmigrated) removes the pod
from rotation; `degraded` is HTTP 200 and keeps serving by design.

**Docker Compose** (production-style override; mirrors the image's built-in
HEALTHCHECK, shown explicitly so thresholds are tunable):

```yaml
services:
  api:
    image: atip-api
    healthcheck:
      test: ["CMD", "python", "-c",
             "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=4)"]
      interval: 30s
      timeout: 5s
      start_period: 10s
      retries: 3
```

The runtime image has no curl/wget — use the `python -c` form above.
Compose has no separate readiness concept; gate dependent services with
`depends_on: { api: { condition: service_healthy } }` and treat
`/health/ready` as the load balancer's target instead.

**AWS ECS** (task definition healthcheck + ALB target group):

```json
"healthCheck": {
  "command": ["CMD-SHELL",
    "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=4)\" || exit 1"],
  "interval": 30, "timeout": 5, "retries": 3, "startPeriod": 15
}
```

ALB target group (the readiness side): health check path `/health/ready`,
success codes `200`, interval 10s, healthy/unhealthy threshold 2/2. A
`not_ready` 503 drains the target; `degraded` stays in service.

### Querying the logs

Every line the API process emits — including uvicorn access and startup
lines — is one JSON object with `timestamp`, `level`, `logger`, `message`,
plus `request_id` on request-scoped records and `exc_info` on errors.
`request_id` is the only correlation key (there is no separate trace_id);
clients can supply their own via the `X-Request-ID` header, and every
problem-details body echoes it back.

Given a failing response, take `request_id` from the problem body (or the
`X-Request-ID` response header) and pull everything that request did:

```bash
# All log records for one request (docker; same idea for any log store)
docker logs <api-container> 2>&1 | grep '"request_id": "<id>"'

# Same with jq, readable
docker logs <api-container> 2>&1 | jq -c 'select(.request_id == "<id>")'

# All errors in a window, with tracebacks
docker logs <api-container> 2>&1 | jq -c 'select(.level == "ERROR") | {timestamp, request_id, message, exc_info}'

# Access-log view: every 5xx served
docker logs <api-container> 2>&1 | jq -c 'select(.logger == "uvicorn.access" and (.message | test(" 5[0-9][0-9]$")))'
```

In an aggregator (CloudWatch Logs Insights, Loki, etc.) filter on the same
JSON fields: `request_id = "<id>"` or `level = "ERROR"`.

## Rollback

- **App**: redeploy the previous image; verify `/health/live` shows the old
  version. Safe at any time.
- **Schema**: prefer rolling the app back and leaving the schema — all
  current migrations are backward-compatible with the previous app release.
  `alembic downgrade <rev>` is the last resort and **destroys the data added
  by the downgraded revisions** (e.g. `c5e8a1f92b47` drops the optimistic-lock
  `version` column; earlier ones drop whole tables). Never downgrade below
  the revision the running app expects.
- **Env vars**: restore the previous values alongside the previous image;
  new vars are ignored by old code (`extra="ignore"`). A changed
  `NEXT_PUBLIC_API_URL` requires a web rebuild, not just a config flip.
- **In-flight work**: document processing runs in-process
  (`BackgroundTasks`), so a container stop can strand a document in
  `PROCESSING` with its job `RUNNING`. Recovery: re-upload the file (uploads
  are not deduplicated; delete the stuck row if it bothers anyone). Nothing
  corrupts — chunk IDs are deterministic (UUIDv5) and re-extraction archives
  reviewed evidence instead of deleting it.
- **Caches/artifacts**: uploaded PDFs in `STORAGE_DIR` and Qdrant vectors
  are version-independent; no invalidation needed on rollback.

## Known limitations (accepted for this release)

- **No authentication/RBAC** — explicitly out of MVP scope. Deploy behind
  your own access control (VPN, proxy auth, private network).
- **Rate limiting is per-process, in-memory.** With N containers the
  effective limit is N×configured. The limiter is interface-isolated for a
  Redis swap when horizontal scale matters.
- **Background processing is in-process**, not a worker queue; see
  rollback notes for the restart consequence.
- **OpenAPI docs (`/docs`, `/openapi.json`) are public** by FastAPI default.
  Acceptable while the API sits behind access control; revisit if exposed.
- **Scanned/image-only PDFs are rejected** (422 `empty_text_layer`); OCR is
  a non-goal.
- **Redis is currently unused at runtime** (health check only); an outage
  shows as degraded health but affects nothing else.
