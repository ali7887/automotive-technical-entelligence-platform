# ATIP — Automotive Technical Intelligence Platform

## What this project is
A Verified AI Workspace for Automotive Compliance & Engineering Documents.
Upload regulatory/standard PDFs → clause-aware chunking w/ provenance → hybrid retrieval → verified answers w/ clause/page citations → PDF citation highlight → Evidence Maps → Version Diff.

This is NOT a generic chatbot. Portfolio-grade polish required for top-tier automotive companies like Porsche.

## Golden rules (must follow)
1. Read docs/02_ROADMAP.md before any work; implement ONLY the active phase.
2. No scope creep: do not build anything listed in Non-Goals.
3. Plan first (short plan + commits). Wait for approval before coding.
4. Small reviewable commits. Conventional commits.
5. Citation provenance is sacred: chunk metadata must never be dropped or guessed.
6. No mock data in production paths. Seed data only under scripts/seed/.
7. End-to-end type safety: Pydantic on API, zod on web, OpenAPI is source of truth.
8. If specs are ambiguous, ask. Do not invent product decisions.
9. Never hallucinate answers: if not supported by retrieved chunks, say "Not found".

## Non-Goals (MVP)
OCR pipelines, vision LLM, diagnostics/CAN/DTC, NHTSA API, heavy agents/LangGraph, full knowledge graph, RBAC/enterprise permissions, billing.

## Stack
- Frontend: Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + TanStack Query + Zustand
- Backend: FastAPI (async) + SQLAlchemy 2.x + Alembic + PostgreSQL (pgvector) + Qdrant + Redis
- AI: OpenAI-compatible client, hybrid retrieval, reciprocal rank fusion (RRF).

## Repo layout
atip/
  apps/
    web/   # Next.js
    api/   # FastAPI
  packages/
  docs/
  prompts/
  scripts/
  docker/

## Definition of Done
- tests pass, lint/typecheck clean, migrations included.
- UI has loading/empty/error states.
- verified outputs: citations exist, map to real chunks, validation step passes.

## Commands
- pnpm dev | pnpm lint | pnpm typecheck | pnpm test
- uv run fastapi dev | uv run pytest | uv run alembic upgrade head
- docker compose up -d
