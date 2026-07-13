# Release Runbook

Operational guide for deploying, verifying, and rolling back ATIP.
Configuration reference: `.env.example` (every variable, purpose, and
production requirements). Dev setup: `README.md`.

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

Fastest: run the release smoke suite against the deployment (LLM-free,
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

Triage: logs are one JSON object per line with `level`, `logger`,
`request_id`, `exc_info`. Given a failing response, grep its `request_id`
(from the problem body or `X-Request-ID` header) across API logs.

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
