# Phase 2 Handoff — Retrieval

## Status
Phase 2 (Retrieval) completed, verified end-to-end, committed.

## Delivered
- `chunks` table (Alembic `7c41d2a90b13`) with full provenance:
  `chunk_id`, `document_id`, `workspace_id`, `chunk_index`, `page_start`/`page_end`,
  `clause_id`, `heading`, `text`, `token_count`, `content_hash`, `embedded_at`
- Deterministic clause-aware chunking (`processing/chunking.py`):
  - 350–600 token target (tokens estimated as chars/4)
  - detects UNECE-style (`6.4.3.1`) and FMVSS-style (`S5.1.2`) clause numbering;
    clause ids are never invented
  - chunk id = UUIDv5(document_id, chunk_index, content_hash) → stable across
    re-processing and shared with Qdrant point ids
- Pipeline: extract → chunk → persist → embed → Qdrant upsert; unchanged chunks
  are not re-embedded, stale chunks/vectors are deleted
- Embeddings: OpenAI-compatible client (`ai/embeddings.py`),
  `text-embedding-3-small`, dim 1536, batched, isolated behind a protocol
- Qdrant: idempotent collection + payload indexes (`workspace_id`, `document_id`);
  payload carries `postgres_chunk_id`, `version_id`, `clause_id`, `chunk_text`,
  `page_start`, `page_end`, `chunk_index`
- Postgres FTS: generated `tsvector` column (clause id + heading + text) with GIN
  index; ranked with `ts_rank_cd` over `websearch_to_tsquery`, deterministic
  id tiebreak
- Hybrid retrieval: `POST /api/workspaces/{workspace_id}/search`
  - body: `query` (1–500 chars), optional `document_id`, `top_k` (1–50, default 10)
  - both legs fetch `min(50, max(20, top_k*3))` candidates, fused with RRF
    (`score = Σ 1/(RRF_K + rank)`, `RRF_K=60`, configurable)
  - each result preserves provenance plus a score breakdown:
    `rrf`, `keyword_rank/score`, `semantic_rank/score`
- Web: search panel on the workspace page (typed client regenerated), with
  loading/empty/error states and a keyword-only notice

## Important implementation notes
- **`OPENAI_API_KEY` is not set on this machine.** By design:
  - processing still chunks, persists, and FTS-indexes; documents reach READY
  - embedding is skipped with a logged warning; `chunks.embedded_at` stays NULL
  - search responds with `semantic_used: false` and keyword-only results
  - once a key is set, re-processing a document embeds pending chunks
    (only unembedded/changed content is embedded)
  - if a key IS set and embedding/Qdrant fails, the processing job FAILS honestly
- `version_id` is carried as `null` everywhere (payloads, API responses):
  document versioning arrives with Version Diff (Phase 5) and ids are never invented.
- `docs/03_ARCHITECTURE.md` and `docs/06_RAG_SPEC.md` referenced by
  `README_FOR_CLAUDE_CODE.md` do not exist in the repo; Phase 2 was built from
  `02_ROADMAP`, `04_DATA_MODEL`, `07_DOC_PROCESSING`, and the phase prompt.
- Blank/scanned PDFs (no text layer) still reach READY with zero chunks — OCR is
  a non-goal.

## Verification
- `uv run pytest`: 37 passed (chunking determinism, provenance persistence,
  embedding/upsert idempotency, FTS behavior, RRF math, endpoint validation)
- `ruff` + `pyright` clean; `pnpm lint` + `pnpm typecheck` clean
- `uv run alembic upgrade head` applied cleanly; `/health` fully `ok`
- Live E2E: real FMVSS 108 PDF (124 pages) → READY in ~4s → 290 chunks
  (289 with detected clause ids, pages 1–124); search for
  "photometric requirements for headlamps" returned `S14.8.7 Photometry test`
  as top hit with scores
- Qdrant collection `atip_chunks`: dim 1536 cosine, payload indexes present

## Next phase
Phase 3 — Verified RAG:
- structured answer validation (claims + citation mapping)
- citations must map to real chunks; PDF region highlighting
