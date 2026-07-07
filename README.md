# ATIP — Automotive Technical Intelligence Platform

Verified AI Workspace for Automotive Compliance & Engineering Documents.

Monorepo:

- `apps/api` — FastAPI backend (uv, SQLAlchemy 2.x, Alembic, PostgreSQL + pgvector, Redis, Qdrant)
- `apps/web` — Next.js frontend (App Router, TypeScript, Tailwind, shadcn/ui, TanStack Query)
- `docker/` — local dev services

## Quickstart (dev)

```bash
# 1. Services
docker compose -f docker/docker-compose.yml up -d

# 2. API
cd apps/api
cp ../../.env.example .env   # adjust if needed
uv sync
uv run alembic upgrade head
uv run fastapi dev src/atip_api/main.py

# 3. Web (new terminal, repo root)
pnpm install
pnpm dev
```

- API: http://localhost:8000 (OpenAPI at `/docs`)
- Web: http://localhost:3000
- Health: http://localhost:8000/health

## Commands

- `pnpm dev | lint | typecheck | test` (workspace-wide)
- `uv run pytest` / `uv run ruff check` / `uv run alembic upgrade head` (in `apps/api`)

See `docs/` for product specs and roadmap; `CLAUDE.md` for contribution rules.
