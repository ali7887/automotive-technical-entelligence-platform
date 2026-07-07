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

## Commands

- `pnpm dev | lint | typecheck` (workspace-wide)
- `pnpm --filter web gen:api` — regenerate the typed API client from the running API's OpenAPI schema
- `uv run pytest` / `uv run ruff check .` / `uv run pyright` / `uv run alembic upgrade head` (in `apps/api`)

API tests need the docker Postgres running; they use a separate `atip_test` database.

See `docs/` for product specs and roadmap; `CLAUDE.md` for contribution rules.
