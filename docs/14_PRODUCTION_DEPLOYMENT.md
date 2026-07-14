# Production Deployment (single VPS)

Operator runbook for the docker-compose production stack. Companion docs:
secrets and variables `docs/13_PROVISIONING_CHECKLIST.md`; backups
`docs/15_BACKUP_AND_RECOVERY.md`; logs/alerts `docs/16_OBSERVABILITY.md`;
release semantics and rollback rationale `docs/12_RELEASE_RUNBOOK.md`.

## Topology

```
internet ──► caddy :80/:443  (only container with published ports)
              │  TLS termination (Let's Encrypt), security headers,
              │  60MB body cap, HTTP→HTTPS redirect
              ├── /api/* , /health/*  ──► api:8000   (edge + internal networks)
              └── everything else     ──► web:3000   (edge network)

internal network (internal: true — no host ports, no internet egress):
  api ──► postgres:5432   (system of record; pgvector)
  api ──► redis:6379      (ingestion queue + health; still no persistence —
                           in-flight queue entries die with redis, and the api
                           fails such jobs lazily after JOB_STALE_AFTER_SECONDS)
  api ──► qdrant:6333     (vectors; derivable from postgres)
  worker ◄─ redis         (arq consumer: PDF extract/chunk/embed/index;
                           same image + env as api; edge+internal like api)
  vector ─(docker socket)─► all container logs ──► file archive (+ Loki overlay)
```

- Files: `docker/docker-compose.prod.yml`, `docker/caddy/Caddyfile`,
  `docker/observability/vector.toml`. All commands go through
  `scripts/ops/compose.sh` (pins the compose file + both env files).
- One public origin: the web bundle is built with
  `NEXT_PUBLIC_API_URL=https://<ATIP_DOMAIN>`, so browser API calls are
  same-origin — CORS never fires cross-origin, and `CORS_ORIGINS` is set to
  the same value as defense in depth.
- `/docs` and `/openapi.json` are **not** routed to the API: the proxy sends
  them to the web app's 404 (closes the "OpenAPI docs are public" gap).
- uvicorn runs with `--proxy-headers` so the per-IP rate limiter and access
  logs see real client IPs (Caddy sets `X-Forwarded-For`). Safe because the
  api port is never published.
- Authentication is cookie sessions (HttpOnly, Secure, SameSite=Strict).
  There is no public signup: after the first deploy, bootstrap the first
  account once —
  `ATIP_BOOTSTRAP_PASSWORD=… scripts/ops/compose.sh run --rm api
  python -m atip_api.cli create-user --email you@co.com --org "Your Org"
  --role org_admin`.

## 1. Server prerequisites

- Linux VPS (2 vCPU / 4 GB RAM / 40 GB disk is a workable floor; Qdrant and
  Postgres both want memory as the corpus grows).
- Docker Engine 24+ with compose v2 (`docker compose version`).
- A non-root deploy user in the `docker` group; repo cloned at `/opt/atip`.
- `git`, `bash`, `curl` on the host (backup scripts use them).
- Time synced (`timedatectl` → NTP active): TLS and backup timestamps rely on it.

## 2. DNS

- `A` (and `AAAA` if you have v6) record: `atip.example.com → <server IP>`.
- Must resolve publicly **before** first boot — Let's Encrypt validates over
  HTTP-01. Check: `dig +short atip.example.com`.

## 3. Firewall

Allow inbound: `22/tcp` (SSH, ideally source-restricted), `80/tcp` (ACME +
redirect), `443/tcp` + `443/udp` (HTTPS + HTTP/3). Deny everything else.

```bash
ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp
ufw --force enable
```

Postgres/Redis/Qdrant have **no** published ports; nothing to firewall there.
Docker publishes ports by bypassing ufw INPUT rules — another reason no
stateful service may ever get a `ports:` entry.

## 4. Secrets

```bash
cd /opt/atip/docker
cp .env.production.example .env.production   # domain, email, tags, tuning
cp .env.secrets.example .env.secrets         # credentials
chmod 600 .env.secrets
```

Fill both in; `POSTGRES_PASSWORD` must appear identically inside
`DATABASE_URL`. Full variable reference and no-leak verification:
`docs/13_PROVISIONING_CHECKLIST.md`.

## 5. First deployment

```bash
cd /opt/atip
scripts/ops/deploy.sh          # builds images from HEAD, migrates, boots, smokes
```

`deploy.sh` does, in order: build `atip-api:<sha>` + `atip-web:<sha>` →
pin `ATIP_TAG`/`BUILD_SHA` in `.env.production` → `run --rm migrate`
(one-shot, before the app) → `up -d` → `scripts/prod_smoke_test.sh
https://<domain> <sha>`. First boot obtains the TLS certificate; allow ~30s.

Manual equivalent, if you need the steps separately:

```bash
scripts/ops/compose.sh run --rm migrate     # migrations, controlled, once
scripts/ops/compose.sh up -d                # boot / roll everything
scripts/ops/compose.sh ps                   # all Up, api (healthy)
```

## 6. Migrations (every release with schema changes)

Handled by `deploy.sh` automatically. Rules (from `docs/12_RELEASE_RUNBOOK.md`):
back up Postgres first (`scripts/ops/backup_postgres.sh`), migrations run
**once** via the `migrate` one-shot service — never per-container, never at
app startup. `/health/ready` holds the API out of "ready" until the schema
is at head.

## 7. Validation checklist (after every deploy)

```bash
# 1. Smoke: liveness, readiness, build identity (exit 0 required)
scripts/prod_smoke_test.sh https://atip.example.com "$(git rev-parse HEAD)"

# 2. Strict health incl. migration revision
curl -s https://atip.example.com/health | grep -o '"detail":"migrated[^"]*"'

# 3. Frontend up and calling the API (browser: create a workspace, upload a PDF)
curl -sI https://atip.example.com/ | head -n1        # HTTP/2 200

# 4. SSE streams through the proxy (event frames appear immediately)
curl -kN "https://atip.example.com/api/workspaces/<id>/chat?question=test" --max-time 15

# 5. Security headers present
curl -sI https://atip.example.com/ | grep -iE 'strict-transport|x-content-type|referrer-policy|x-frame'

# 6. Nothing stateful is public
docker ps --format '{{.Names}}\t{{.Ports}}'   # only caddy shows 0.0.0.0 bindings
```

## 8. Logs

```bash
scripts/ops/compose.sh logs -f api            # live tail (one JSON object/line)
scripts/ops/compose.sh logs --since 1h caddy  # proxy/ACME events
```

Shipped copies (per-service NDJSON, per-day) live on the `atip_logs` volume;
querying by `request_id`, error sweeps, Loki: `docs/16_OBSERVABILITY.md`.

## 9. Backups

Nightly cron + retention: `docs/15_BACKUP_AND_RECOVERY.md`. Verify one
manually after first deploy: `scripts/ops/backup_all.sh` (exit 0, three
artifacts listed).

## 10. Rolling restart / rollback

```bash
# Rolling restart (config change in .env.production, same images)
scripts/ops/compose.sh up -d

# Restart one service
scripts/ops/compose.sh restart api

# Emergency rollback to a previous release (images are kept per-SHA)
scripts/ops/deploy.sh <previous-git-sha>
# deploy.sh re-builds if the image is missing, re-runs migrate (no-op if
# schema unchanged), rolls, and smoke-tests. Schema rollback caveats:
# docs/12_RELEASE_RUNBOOK.md (prefer rolling app back, leaving schema).
```

## 11. Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| Browser: connection refused / no TLS | DNS not pointing here, or 80/443 blocked | `dig +short <domain>`; check firewall; `compose.sh logs caddy` for ACME errors |
| Caddy log: ACME challenge failed | Port 80 unreachable from internet, or DNS lag | Open 80/tcp, wait for DNS, `compose.sh restart caddy` |
| 502 from proxy | api/web container down or still starting | `compose.sh ps`, `compose.sh logs api` |
| Smoke exit 2, `/health/ready` 503 `not_ready` | Postgres down or schema not at head | `compose.sh logs postgres`; `compose.sh run --rm migrate` |
| Smoke exit 0 with `degraded` warning | Qdrant or Redis down; keyword search continues | Fix the dependency; do **not** restart api (by design it keeps serving) |
| Smoke exit 3 | Running container isn't the SHA you deployed | `ATIP_TAG`/`BUILD_SHA` drift in `.env.production`; re-run `deploy.sh` |
| API boots then exits: "Refusing to start with unsafe production configuration" | Dev DB credentials or relative `STORAGE_DIR` in env | Fix `.env.secrets`/`.env.production`; see boot error text (it names the variable) |
| Uploads fail with generic 413 (not problem+json) | Body larger than Caddy's 60MB backstop | Expected for pathological bodies; raise `request_body max_size` only together with `MAX_UPLOAD_MB` |
| Plain-text lines in api logs | `LOG_JSON` unset/false | Set `LOG_JSON=true`, `compose.sh up -d` |
| Rate limit hits shared across users | uvicorn not seeing forwarded IPs | Ensure the api service `command` still has `--proxy-headers` (compose file) |
