# ATIP — Claude Code Runtime Guide
Minimal token-budgeting instructions for deterministic phase-based development.

## 1. Phase-Specific File Loading (Token Control)
Claude Code must NEVER load the entire docs directory.  
Only provide the subset listed below for each phase.

### Phase 1 — Foundation
- CLAUDE.md
- docs/02_ROADMAP.md
- docs/04_DATA_MODEL.md
- docs/07_DOC_PROCESSING.md
- docs/11_DEPLOYMENT_DEV.md

### Phase 2 — Retrieval (Qdrant + Hybrid Search)
- CLAUDE.md
- docs/02_ROADMAP.md
- docs/03_ARCHITECTURE.md
- docs/06_RAG_SPEC.md

### Phase 3 — Verified RAG
- CLAUDE.md
- docs/02_ROADMAP.md
- docs/05_API_CONTRACT.md
- docs/06_RAG_SPEC.md
- docs/08_UI_SPEC.md
- docs/10_TESTING.md

### Phase 4 — Evidence Map
- CLAUDE.md
- docs/01_PRODUCT.md
- docs/02_ROADMAP.md
- docs/04_DATA_MODEL.md
- docs/06_RAG_SPEC.md
- docs/08_UI_SPEC.md

### Phase 5 — Version Diff
- CLAUDE.md
- docs/01_PRODUCT.md
- docs/02_ROADMAP.md
- docs/04_DATA_MODEL.md
- docs/08_UI_SPEC.md
- docs/10_TESTING.md

### Phase 6 — Polish
- CLAUDE.md
- docs/02_ROADMAP.md
- docs/08_UI_SPEC.md
- docs/10_TESTING.md
- docs/11_DEPLOYMENT_DEV.md

---

## 2. Interaction Loop (Strict)
1. Ali pastes the phase prompt (e.g., prompts/01_phase_template.md)
2. Claude switches to Plan Mode → produces:
   - step-by-step plan
   - small commit batches
3. Ali approves or refines.
4. Claude writes code + tests.
5. Claude runs lint/typecheck/tests.
6. Claude commits using Conventional Commits.
7. Ali **resets the Claude Code session** to clear past context.

---

## 3. Qdrant Integration Rules (MVP)
- Metadata lives in Postgres.
- Embeddings live in Qdrant.
- Qdrant payload must include:
  - `postgres_chunk_id: string`
  - `version_id: string`
- Retrieval pipeline = FTS (Postgres) + Vector (Qdrant) → RRF fusion → lightweight rerank.
- RAG is grounded only on the fused result.

---

## 4. Health Check Requirements
Before implementing RAG or advanced tasks, `/health` must validate:
- Postgres reachable and migrated.
- Redis reachable.
- Qdrant reachable; collection exists.
- Vector dimension matches embedding model.
