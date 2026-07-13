# ATIP — Automotive Technical Intelligence Platform

Verified AI Workspace for Automotive Compliance & Engineering Documents.

Monorepo:

- `apps/api` — FastAPI backend (uv, SQLAlchemy 2.x, Alembic, PostgreSQL + pgvector, Redis, Qdrant)
- `apps/web` — Next.js frontend (App Router, TypeScript, Tailwind, shadcn/ui, TanStack Query)
- `docker/` — local dev services

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

## Commands

- `pnpm dev | lint | typecheck` (workspace-wide); `pnpm --filter web build` — production web build
- `pnpm --filter web gen:api` — regenerate the typed API client from the running API's OpenAPI schema
- `uv run pytest` / `uv run ruff check .` / `uv run pyright` / `uv run alembic upgrade head` (in `apps/api`)
- `uv run pytest tests_e2e -q` (in `apps/api`) — release smoke suite against a **running** API
  (`ATIP_E2E_BASE_URL` to target a deployment; LLM-free and self-cleaning)
- `scripts/prod_smoke_test.sh <BASE_URL> [EXPECTED_BUILD_SHA]` — standalone post-deploy
  health + build-identity check (bash + curl only)
- `docker build -t atip-api apps/api` — production API image

CI (`.github/workflows/ci.yml`) runs exactly these: ruff + pyright + migration
round-trip + pytest + E2E smoke for the API, and eslint + tsc + `next build` for the web.

API tests need the docker Postgres running; they use a separate `atip_test` database.

Configuration reference: `.env.example`. Deploy/rollback/monitoring: `docs/12_RELEASE_RUNBOOK.md`.
See `docs/` for product specs and roadmap; `CLAUDE.md` for contribution rules.
