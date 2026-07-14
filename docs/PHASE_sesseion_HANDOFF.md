You are continuing work on ATIP (Automotive Technical Intelligence Platform).

## Critical instruction
Before doing anything else, assume that previous phases were already implemented and verified.  
Your first responsibility is to **understand the current repo state from files**, not to rebuild or re-decide completed work.

Do **not** redo completed phases.  
Do **not** replace existing working implementations with alternative designs unless a real bug or explicit requirement demands it.  
Do **not** introduce scope creep.

---

## Project state summary

### Phase 1 — Foundation
Completed, verified, and committed.

Implemented:
- monorepo structure with `apps/web` and `apps/api`
- Docker Compose infrastructure for:
  - PostgreSQL + pgvector
  - Redis
  - Qdrant
- FastAPI backend with layered architecture
- Next.js frontend with Tailwind, shadcn/ui, TanStack Query, generated OpenAPI client
- workspace CRUD
- PDF upload
- background document processing
- health check endpoints
- local service integration and CORS verification

Status:
- passed and stable
- working tree was clean
- handoff documented

---

### Phase 2 — Retrieval
Completed, verified end-to-end, and committed in 6 conventional commits.

Implemented:
- durable `chunks` persistence in Postgres
- deterministic chunking pipeline
- provenance-preserving metadata
- clause detection for UNECE / FMVSS patterns where actually detected
- chunk UUIDv5 stable IDs
- content-hash-based idempotent reprocessing
- embeddings integration through OpenAI-compatible client abstraction
- Qdrant upsert/query/delete support
- Qdrant payload indexes
- Postgres FTS using `websearch_to_tsquery` and `ts_rank_cd`
- Hybrid Retrieval using Reciprocal Rank Fusion (RRF)
- retrieval API endpoint
- typed web client regeneration
- minimal retrieval UI on workspace page

Important implementation facts:
- chunk IDs must remain stable
- provenance must never be dropped
- clause IDs must never be invented
- `version_id` is currently `null` and versioning is deferred to Phase 5
- if `OPENAI_API_KEY` is missing:
  - processing still completes
  - FTS still works
  - semantic retrieval is skipped honestly
  - no mock vectors
  - no fake degradation masking

Verification already completed:
- tests passed
- lint/typecheck passed
- migrations applied
- local health green
- real FMVSS PDF processed successfully
- live retrieval verified

This phase is already done.  
Do not re-implement retrieval infrastructure unless you find a real defect.

---

## Missing docs note
The following files were referenced somewhere but do **not** exist in the repo:
- `docs/03_ARCHITECTURE.md`
- `docs/06_RAG_SPEC.md`

Do not block on these missing files if the existing docs are enough for the requested phase.  
But if their absence becomes a real blocker, report it explicitly.

---

## Source-of-truth files to read first
Before planning or coding, read only the minimum relevant files first:

- `CLAUDE.md`
- `docs/02_ROADMAP.md`
- `docs/04_DATA_MODEL.md`
- `docs/07_DOC_PROCESSING.md`
- `docs/PHASE_1_HANDOFF.md` if present
- `docs/PHASE_2_HANDOFF.md`
- any directly relevant router/service/schema files for the requested phase

Do **not** scan the whole repo without reason.  
Minimize context usage and stay focused.

---

## Working rules
1. Treat completed work as authoritative unless proven broken.
2. Preserve architecture consistency.
3. Preserve API compatibility unless a change is necessary.
4. Keep provenance, traceability, and determinism intact.
5. Ask a focused question only if a real ambiguity blocks implementation.
6. Keep commits small and conventional.
7. At the end of every phase, update the handoff document.
8. At the end of every phase, explicitly remind the user to **push all completed work to GitHub**.

---

## Git discipline
At the end of each completed phase:
1. ensure tests/lint/typecheck pass
2. ensure docs/handoff are updated
3. commit cleanly
4. remind the user to run:
```bash
git push origin main
