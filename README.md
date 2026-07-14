# ATIP — Automotive Technical Intelligence Platform

A verified AI workspace for automotive compliance and engineering documents.
Upload regulatory/standard PDFs, get clause-aware chunking with full provenance,
hybrid retrieval, and **verified answers with clause/page citations** that can be
checked directly against the source PDF. ATIP is deliberately not a generic
chatbot: if an answer is not supported by retrieved text, it says so.

## Key capabilities

- **Clause-aware ingestion** — PDFs are chunked with structural lineage
  (clause IDs, page ranges) preserved as citation provenance; metadata is never
  dropped or guessed.
- **Hybrid retrieval** — keyword + semantic vector search fused with Reciprocal
  Rank Fusion (RRF); optional cross-encoder reranking over an HTTP endpoint
  (Cohere/Jina/TEI-compatible) with silent fallback to the RRF ordering.
- **Verified answers** — every generated answer is validated against the
  retrieved chunks and labeled `verified` / `partial` / `unsupported` /
  `not_found`; fully unsupported answers are withheld rather than shown.
- **Evidence you can inspect** — inline citation markers open the exact page
  and quote in a PDF viewer; an evidence-map panel and review queue support
  auditing answers and citations.
- **Async ingestion pipeline** — uploads are queued to an arq worker with live
  progress stages (`queued → extracting → vectorizing → ready`); search is
  gated until a document is ready.
- **Authentication & tenancy** — cookie-session auth (HttpOnly, SameSite=Strict,
  Secure in production), organizations as tenancy boundary, per-workspace RBAC.
  No public signup; the first account is bootstrapped via CLI.
- **Graceful degradation** — without an `OPENAI_API_KEY`, documents remain
  keyword-searchable and generation is disabled (the API degrades, it does not
  fail); if Redis is unavailable, uploads fall back to in-process processing.

## Architecture

```
Next.js (App Router) ──► FastAPI (async)
                            ├── PostgreSQL + pgvector   system of record
                            ├── Qdrant                  vector index (derivable)
                            ├── Redis                   ingestion queue
                            └── arq worker              PDF extract/chunk/embed/index
```

In production the whole stack runs as a single docker-compose deployment behind
Caddy (TLS via Let's Encrypt); only the proxy publishes ports, stateful services
live on an internal no-egress network, and a Vector sidecar ships structured
JSON logs (with `request_id` correlation across API and worker) to a file
archive or Loki. See `docs/14_PRODUCTION_DEPLOYMENT.md`.

## Tech stack

- **Frontend:** Next.js (App Router), TypeScript, Tailwind, shadcn/ui,
  TanStack Query, Zustand
- **Backend:** FastAPI (async), SQLAlchemy 2.x, Alembic, PostgreSQL (pgvector),
  Qdrant, Redis, arq
- **AI:** OpenAI-compatible client (embeddings + generation), hybrid retrieval
  with RRF, optional HTTP reranker
- **Type safety end to end:** Pydantic on the API, zod + a generated typed
  client on the web; the OpenAPI schema is the source of truth.

## Repository structure

```
apps/
  api/     # FastAPI backend (uv, Alembic migrations, arq worker, CLI)
  web/     # Next.js frontend
docker/    # dev compose stack + production stack (Caddy, Vector, Loki overlay)
docs/      # roadmap, data model, runbooks (deployment, backup, observability)
prompts/   # prompt templates used by the RAG pipeline
scripts/   # prod_smoke_test.sh + scripts/ops (deploy, backup, restore)
```

## Quickstart (dev)

```bash
# 1. Services (Postgres on 5433, Redis on 6380, Qdrant on 6335 — defaults avoid local port clashes)
docker compose -f docker/docker-compose.yml up -d

# 2. API (defaults in code match the compose ports; use .env to override)
cd apps/api
uv sync
uv run alembic upgrade head
uv run fastapi dev src/atip_api/main.py

# 3. Web (new terminal, repo root)
pnpm install
cp apps/web/.env.example apps/web/.env.local
pnpm dev
```

- Web: http://localhost:3000
- API: http://127.0.0.1:8000 (OpenAPI at `/docs`)
- Health: http://127.0.0.1:8000/health — verifies Postgres (migrated), Redis, and the Qdrant collection E2E
  (`/health/live` and `/health/ready` are the orchestrator probes — see docs/12_RELEASE_RUNBOOK.md)

### Configuration

All variables are documented in `.env.example` (safe development defaults in
code; production requirements marked). Notable groups: AI provider
(`OPENAI_API_KEY` optional), reranking (`RERANK_*`, off by default), async
queue (`QUEUE_ENABLED`, off in dev), sessions (`SESSION_TTL_HOURS`,
`RATE_LIMIT_LOGIN_PER_MINUTE`), uploads (`STORAGE_DIR`, `MAX_UPLOAD_MB`).

### First user (no public signup)

```bash
ATIP_BOOTSTRAP_PASSWORD='<strong password>' uv run python -m atip_api.cli create-user \
  --email you@company.com --org "Your Org" --role org_admin
```

## Commands

- `pnpm dev | lint | typecheck` (workspace-wide); `pnpm --filter web build` — production web build
- `pnpm --filter web gen:api` — regenerate the typed API client from the running API's OpenAPI schema
- `uv run pytest` / `uv run ruff check .` / `uv run pyright` / `uv run alembic upgrade head` (in `apps/api`)
- `uv run arq atip_api.worker.WorkerSettings` (in `apps/api`) — run the ingestion worker locally (`QUEUE_ENABLED=true`)
- `uv run pytest tests_e2e -q` (in `apps/api`) — release smoke suite against a **running** API
  (`ATIP_E2E_BASE_URL` to target a deployment; LLM-free and self-cleaning)
- `scripts/prod_smoke_test.sh <BASE_URL> [EXPECTED_BUILD_SHA]` — standalone post-deploy
  health + build-identity check (bash + curl only)
- `docker build -t atip-api apps/api` — production API image
- `docker build -f apps/web/Dockerfile --build-arg NEXT_PUBLIC_API_URL=<url> -t atip-web .` — production web image
- `scripts/ops/deploy.sh` — full single-VPS release (build, migrate, roll, smoke); stack in
  `docker/docker-compose.prod.yml`, runbook in `docs/14_PRODUCTION_DEPLOYMENT.md`

## Testing & CI

CI (`.github/workflows/ci.yml`) runs exactly these: ruff + pyright + migration
round-trip + pytest + E2E smoke for the API, and eslint + tsc + `next build`
for the web.

API tests need the docker Postgres running; they use a separate `atip_test`
database. Migrations run once per release via a one-shot `migrate` compose
service — never at app startup; `/health/ready` holds the API out of "ready"
until the schema is at head.

## Production deployment

Single-VPS docker-compose stack; the full operator path is:

```bash
scripts/ops/deploy.sh        # build per-SHA images, migrate, roll, smoke-test
```

Runbooks: `docs/14_PRODUCTION_DEPLOYMENT.md` (deploy),
`docs/13_PROVISIONING_CHECKLIST.md` (secrets/variables),
`docs/12_RELEASE_RUNBOOK.md` (release semantics + rollback),
`docs/15_BACKUP_AND_RECOVERY.md`, `docs/16_OBSERVABILITY.md`.

## Operational notes & known behavior

- `NEXT_PUBLIC_API_URL` is baked into the web image at build time and must
  match the deployed origin, or the session cookie will not flow.
- Redis persistence is intentionally off: queued-but-not-started jobs are lost
  if Redis dies; the API fails them lazily after `JOB_STALE_AFTER_SECONDS` and
  a re-upload recovers.
- Reranking is optional and fail-open: any reranker error keeps the RRF
  ordering (`rerank_used=false` in responses).
- `scripts/ops/compose.sh run --rm api python -m atip_api.cli backfill-chunks`
  reprocesses existing READY documents to populate clause lineage in place
  (chunk IDs and embeddings preserved).

## Contributing

Contribution rules, golden rules (citation provenance is sacred; no mock data
in production paths), and non-goals live in `CLAUDE.md`. Use conventional
commits; keep changes small and reviewable.

## License

No license has been selected yet. All rights reserved until a `LICENSE` file
is added.
