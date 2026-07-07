# Roadmap & Acceptance Criteria

## Phase 1 — Foundation (Done — see PHASE_1_HANDOFF.md)
- monorepo setup (pnpm + uv)
- docker compose: postgres(+pgvector) + redis + qdrant
- schema + alembic migrations (Workspace, Document, ProcessingJob)
- workspace CRUD (API+UI)
- upload PDF + storage (local/dev)
- processing job status polling
- health check endpoint verifying all services E2E

Acceptance:
- upload a real regulation → status "ready"
- web can call api health-check end-to-end (CORS/env verified)

## Phase 2 — Retrieval (Qdrant + Hybrid Search) (Done — see PHASE_2_HANDOFF.md)
- embeddings + qdrant integration
- postgres FTS keyword search
- hybrid retrieval (RRF)
Acceptance:
- hybrid retrieval returns accurate clauses with scores

## Phase 3 — Verified RAG
- structured answer validation (claims + citation mapping)
Acceptance:
- zero fabricated citations; clicks highlight correct PDF region
