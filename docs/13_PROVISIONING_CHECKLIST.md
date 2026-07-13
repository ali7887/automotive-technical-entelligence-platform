# Production Provisioning Checklist

Every environment variable the platform reads, where its value comes from,
and how to verify a production environment **without printing any values**.
Authoritative definitions: `.env.example` (annotated) and
`apps/api/src/atip_api/config.py` (typed schema — the code is the contract).

There is no separate worker process: document processing runs in-process in
the API (FastAPI `BackgroundTasks`), so "Backend" below covers it. The web
app reads exactly one variable, at **build time**.

Security levels: **Secret** = credential, store in the platform's secret
manager, never in plain config or logs. **Sensitive** = not a credential by
itself but may embed one or reveal internal topology (URLs with passwords,
internal hostnames). **Public** = safe in plain config and build logs.

## Variable checklist

| Variable | Required for | Source | Security level |
|---|---|---|---|
| `ENVIRONMENT` | Backend | Literal `production` (enables fail-fast startup checks) | Public |
| `BUILD_SHA` | Backend | Deploy pipeline — git commit SHA (`github.sha` in CI) | Public |
| `DATABASE_URL` | Backend | Managed PostgreSQL 16 + pgvector (async DSN incl. credentials). Dev-default `atip:atip@` is **rejected at boot** | Secret |
| `REDIS_URL` | Backend | Managed Redis / container endpoint (health check only today) | Sensitive |
| `QDRANT_URL` | Backend | Qdrant instance or Qdrant Cloud endpoint | Sensitive |
| `QDRANT_COLLECTION` | Backend | Chosen name, default `atip_chunks` | Public |
| `OPENAI_API_KEY` | Backend (optional) | OpenAI dashboard (or compatible provider). Unset = keyword-only search, no answer generation — degrades, doesn't fail | Secret |
| `OPENAI_BASE_URL` | Backend (optional) | Provider docs; empty for OpenAI itself | Public |
| `EMBEDDING_MODEL` | Backend | Provider model catalog | Public |
| `EMBEDDING_DIM` | Backend | Must match `EMBEDDING_MODEL` **and** the existing Qdrant collection dimension | Public |
| `LLM_MODEL` | Backend | Provider model catalog | Public |
| `OPENAI_TIMEOUT_SECONDS` | Backend (tuning) | Default 60 | Public |
| `QDRANT_TIMEOUT_SECONDS` | Backend (tuning) | Default 10 | Public |
| `RRF_K` | Backend (tuning) | Default 60 (hybrid-retrieval fusion constant) | Public |
| `STORAGE_DIR` | Backend | **Absolute** path on a **persistent volume** (relative is rejected at boot). Container default: `/data/uploads` | Public |
| `MAX_UPLOAD_MB` | Backend (tuning) | Default 50 | Public |
| `MAX_PDF_PAGES` | Backend (tuning) | Default 2000 | Public |
| `CORS_ORIGINS` | Backend | Comma-separated deployed web origin(s), e.g. `https://atip.example.com`. Loopback origins in production log a warning | Public |
| `LOG_LEVEL` | Backend | Default `INFO` | Public |
| `LOG_JSON` | Backend | Keep `true` in production (one JSON object per line, `request_id` correlation) | Public |
| `RATE_LIMIT_ENABLED` | Backend | Keep `true` | Public |
| `RATE_LIMIT_ASK_PER_MINUTE` | Backend (tuning) | Default 30 — per process; multiply by container count | Public |
| `RATE_LIMIT_EXTRACT_PER_MINUTE` | Backend (tuning) | Default 10 — per process; multiply by container count | Public |
| `NEXT_PUBLIC_API_URL` | Web (**build time**) | Public HTTPS URL of the deployed API. Baked into the bundle — changing it requires a web rebuild | Public |

## Verifying an environment without leaking values

### 1. Schema + safety validation (authoritative)

Run the API's own typed config schema and production fail-fast checks inside
the release image, against the exact env the containers will get:

```bash
docker run --rm --env-file prod.env atip-api \
  python -c "from atip_api.config import Settings; s = Settings(); s.validate_for_release(); print('config OK - environment:', s.environment)"
```

- Exit 0 + `config OK` — every variable parses, numeric limits are in range,
  and no unsafe production default is present.
- Non-zero — the error names the offending **variable**, never its value
  (`OPENAI_API_KEY` is a `SecretStr`; the dev-credential check prints a fixed
  message). Fix and re-run.

This is the same check the container performs at startup, so anything it
accepts will boot.

### 2. Presence check (any shell, no image needed)

Quick pass over the variables that production must explicitly set:

```bash
for v in ENVIRONMENT DATABASE_URL REDIS_URL QDRANT_URL STORAGE_DIR CORS_ORIGINS; do
  if [ -n "$(printenv "$v")" ]; then echo "ok    $v is set"; else echo "MISSING $v"; fi
done
```

Prints only names and set/missing — safe to run in CI logs. For the web
build environment, check `NEXT_PUBLIC_API_URL` the same way.

### 3. Post-boot verification

After deploy, run the smoke script (checks liveness, readiness, and that the
running `build_sha` is the release you meant to ship):

```bash
scripts/prod_smoke_test.sh https://api.example.com "$EXPECTED_BUILD_SHA"
```

Full procedure: `docs/12_RELEASE_RUNBOOK.md`.
