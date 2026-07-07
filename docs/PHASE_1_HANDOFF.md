# Phase 1 Handoff

## Status
Phase 1 completed, verified end-to-end, committed, and pushed.

## Delivered
- Monorepo skeleton
- apps/web (Next.js)
- apps/api (FastAPI)
- Docker services:
  - Postgres + pgvector
  - Redis
  - Qdrant
- Alembic initial migration
- Workspace CRUD
- PDF upload
- Processing job with in-process BackgroundTasks
- /health endpoint with:
  - Postgres check
  - Redis ping
  - Qdrant collection + dimension validation
- Web health widget
- Workspaces UI
- Documents table with polling

## Important implementation notes
- Due to local port conflicts:
  - Postgres mapped to 5433
  - Redis mapped to 6380
  - Qdrant mapped to 6335
- Use `127.0.0.1` instead of `localhost` for local service URLs.
- IPv6 loopback was not forwarded properly on this machine.
- Processing currently uses FastAPI BackgroundTasks.
- Chunking and Qdrant upserts are intentionally deferred to Phase 2.

## Verification
- pytest passed
- ruff clean
- pyright clean
- pnpm lint clean
- pnpm typecheck clean
- /health ok
- Real FMVSS 108 PDF uploaded successfully and reached READY

## Next phase
Phase 2 — Retrieval:
- embeddings
- chunk persistence
- Qdrant upserts
- Postgres FTS
- hybrid retrieval with RRF
