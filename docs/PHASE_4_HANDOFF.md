# Phase 4 Handoff — Evidence Map & PDF Traceability

> Status: **DONE** (completed 2026-07-08). Verified end-to-end (94 API tests, live API
> against a stub LLM, web build + page smoke test).

## What was achieved before Phase 4

### Phase 1 — Foundation (done)
- Monorepo (pnpm + uv): `apps/web` (Next.js App Router, Tailwind, shadcn/ui, TanStack
  Query, generated OpenAPI client) + `apps/api` (FastAPI async, SQLAlchemy 2.x, Alembic).
- Docker Compose: Postgres+pgvector, Redis, Qdrant. **This machine uses non-default
  ports: 5433 / 6380 / 6335 on 127.0.0.1** (defaults are broken locally).
- Workspace CRUD, PDF upload to local storage (`apps/api/storage/`), background
  processing jobs with status polling, E2E health check.

### Phase 2 — Retrieval (done)
- Deterministic chunking pipeline (`processing/chunking.py`, `processing/pipeline.py`):
  per-page text extraction, heading + clause detection (UNECE/FMVSS patterns),
  350–600-token chunks.
- Durable `chunks` table in Postgres with provenance: `chunk_index`, `page_start`,
  `page_end`, `clause_id` (nullable, never invented), `heading`, `text`, `token_count`,
  `content_hash`, generated `text_search` tsvector (GIN).
- **Chunk IDs are deterministic UUIDv5** of document + index + content hash —
  reprocessing is idempotent; IDs must remain stable.
- Embeddings via OpenAI-compatible client (`ai/embeddings.py`); Qdrant upsert/query/
  delete with payload indexes (payload carries `postgres_chunk_id`, `document_id`,
  `clause_id`, `chunk_text`, `page_start`; `version_id` is `null` until Phase 5).
- Hybrid retrieval = Postgres FTS (`websearch_to_tsquery` + `ts_rank_cd`) fused with
  Qdrant semantic search via RRF (`services/retrieval.py`, `POST /workspaces/{id}/search`).
- Without `OPENAI_API_KEY`: processing and FTS still work; semantic retrieval is
  skipped honestly (no mock vectors).

### Phase 3 — Verified RAG (done — see PHASE_3_HANDOFF.md for full detail)
- `ai/llm.py`: streaming chat client behind a protocol; `get_llm_client()` → `None`
  without `OPENAI_API_KEY`. Model from `LLM_MODEL`, `temperature=0`.
- LLM contract (`services/rag_prompts.py`): answer text with inline `[n]` markers, then
  `<<<CLAIMS>>>` sentinel + strict JSON claims/citations block.
- **Verification layer** (`services/verification.py`) — offline, deterministic:
  - claim quotes matched verbatim (whitespace/case-normalized, min 12 chars) against
    exact retrieved chunk text
  - citation status `validated` / `weak`; fake source indices dropped + markers
    stripped; zero validated citations ⇒ `not_found` with standard text
  - answer status: `verified` | `partial` | `unsupported` | `not_found`
- Endpoints (`routers/rag.py`):
  - `POST /api/workspaces/{id}/ask` → `AskResponse` (`answer_md`, `citations` with
    `citation_id`, `postgres_chunk_id`, `clause_id`, `page_start/end`,
    `source_text_snippet`, `status`; `verification`; numbered `sources`)
  - `GET /api/workspaces/{id}/chat` → SSE `sources` → `token`* → `final`/`error`;
    streamed tokens are the unverified draft, client must replace with `final.answer_md`
- Web: `components/chat/chat-panel.tsx` (streaming, verification badge, inline `[n]`
  buttons that highlight/scroll to source cards); `lib/api/stream.ts` (zod-validated SSE).
- 65 tests passing; ruff/pyright/eslint/tsc clean; verified live E2E.

## Invariants that Phase 4 must NOT break
1. **Citation provenance is sacred** — citations only reference actually retrieved
   chunks; metadata (clause_id, pages) is never guessed or invented.
2. **Chunk UUIDv5 stable IDs** — do not change the chunking or ID derivation.
3. **Verification layer semantics** — quote-verbatim matching, `validated`/`weak`
   statuses, `not_found` fallback. Evidence Map consumes these; it must not weaken them.
4. **Sentinel holdback in SSE** — the claims block never leaks into streamed tokens.
5. **Degraded-mode honesty** — no `OPENAI_API_KEY` ⇒ explicit 503/error, never mocks.
6. **Type safety chain** — Pydantic schemas → OpenAPI → regenerated typed web client
   (+ zod only at the SSE boundary).
7. `version_id` stays `null` — versioning is Phase 5.

## Current state relevant to Phase 4 (gaps found at kickoff)
- There is **no endpoint that serves the original PDF file** (documents router only has
  upload/list/get-metadata/job-status). PDF traceability needs `GET /documents/{id}/file`.
- There is **no PDF viewer** in the web app and no pdf library in `package.json`.
- Chunks carry **no bounding-box coordinates** — only page range, clause_id, and exact
  text. Exact-area highlighting must therefore use pdf.js text-layer search of the
  verified quote / chunk text on the cited page (the quote is verbatim by construction,
  which makes this reliable). Do not fabricate coordinates.
- `prompts/04_evidence_map.md` (requirement extraction, evidence items, JSON/Markdown
  export, editable status/risk table) vs. the kickoff brief (PDF traceability, evidence
  panel, click-to-highlight) describe different scopes — resolved with the user at
  kickoff; see "Agreed scope" below.

## Agreed scope
User decision (2026-07-08): **both tracks in one phase**, Track A first.

- **Track A — PDF Traceability**: `GET /api/documents/{id}/file` streaming endpoint;
  react-pdf (pdf.js) viewer on the workspace page; clicking an inline citation `[n]` or
  an evidence card opens the viewer at the cited page and highlights the verified quote
  via text-layer search (no stored coordinates — fallback is page-level scroll);
  Evidence Panel listing each citation (document, clause, pages, snippet, status) with
  a "Verify on Document" button.
- **Track B — Evidence Map (per prompts/04_evidence_map.md)**: requirement extraction
  from processed documents (reusing the Phase 3 LLM client + verification layer —
  every extracted requirement's citation must be quote-verified); `evidence_items`
  persistence + Alembic migration; export as JSON + Markdown; UI table with editable
  status and risk; deterministic tests for extraction + citation validation.

## Delivered

### Track A — PDF Traceability
- `GET /api/documents/{id}/file` (routers/documents.py): streams the stored PDF
  inline; 404 when the document or its file is missing.
- `components/pdf/pdf-viewer.tsx`: react-pdf viewer (client-only via `next/dynamic`,
  `ssr: false` — pdf.js needs browser APIs). Worker configured via
  `new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url)`; **`pdfjs-dist` must
  stay a direct dependency** (pnpm strict node_modules) or the Turbopack build breaks.
- Quote highlighting: `customTextRenderer` marks text-layer fragments matching the
  verified quote using the same whitespace/case normalization as the verification
  layer, with edge-overlap handling for quotes spanning line fragments; graceful
  fallback is plain page-level navigation.
- `components/pdf/evidence-viewer-panel.tsx`: slide-over dialog (Esc/backdrop close,
  open-original-in-new-tab); opened via the `useEvidenceViewer` zustand store.
- Chat panel: inline `[n]` markers and evidence cards open the viewer at the cited
  page; citation list renamed "Supporting evidence" with per-citation
  "Verify on document" buttons.

### Track B — Evidence Map
- Models (`models/evidence.py`) + migration `9d4e1f6a2c53`: `evidence_items`
  (reviewer-owned `status`/`risk` enums) and `evidence_citations` (chunk provenance
  snapshot: chunk_id, clause_id, pages, verified quote). `chunk_id` deliberately has
  **no FK to chunks**: re-processing a document must not silently delete evidence.
- Extraction (`services/evidence.py`, `services/evidence_prompts.py`): batches of 12
  chunks per LLM call in chunk_index order; model must output strict JSON
  `{"requirements": [{"text", "citations": [{"source", "quote"}]}]}`; every quote is
  verified via the Phase 3 `quote_supported` rules. Only requirements with ≥1
  validated citation persist; fabricated/unverifiable quotes and nonexistent source
  indices are dropped, counted, and returned as warnings. Cross-batch dedupe by
  normalized requirement text. **Re-extraction replaces the document's items,
  including reviewer status/risk** (surfaced in the UI).
- Endpoints (`routers/evidence.py`): `POST /api/documents/{id}/evidence/extract`
  (503 without key, 404 missing, 409 non-READY), `GET /api/workspaces/{id}/evidence`
  (`document_id` filter), `PATCH /api/evidence/{item_id}` (status/risk),
  `GET .../evidence/export` (JSON) and `.../evidence/export.md` (Markdown attachment).
- Web (`components/evidence/evidence-map-panel.tsx`): per-document extraction with
  replace warning, requirements table with editable status/risk selects, citation
  chips that open the PDF viewer at the evidence, JSON/Markdown export downloads,
  loading/empty/error states.
- Extraction is synchronous; fine for MVP-sized documents, a background job would be
  needed for very large regulations (noted, not built — keep out of scope creep).

## Verification (2026-07-08)
- `uv run pytest`: 94 passed (29 new: extraction parsing/citation-validation unit
  tests incl. fabricated quotes, fake source indices, too-short quotes, dedupe;
  endpoint tests with deterministic fake LLMs incl. malformed output, re-extract
  replacement, 503/404/409/422 paths, exports).
- `ruff` + `pyright` clean; `pnpm lint` + `pnpm typecheck` + `pnpm build` clean.
- Migration applied against dev Postgres (`alembic upgrade head` → `9d4e1f6a2c53`).
- Live E2E with an OpenAI-compatible stub (scratchpad, port 8089): upload → READY →
  file endpoint streams `%PDF` inline → extraction persisted the verified requirement
  (clause `S5.1.2`, p. 1) and dropped the fabricated one with warnings → PATCH
  status/risk → Markdown export rendered correctly → Phase 3 `/ask` regression still
  `verified`. Web dev server renders the workspace page with the Evidence Map panel.

## Progress
- 2026-07-08: handoff initialized; repo state audited; plan proposed.
- 2026-07-08: Track A + Track B implemented, tested, live-verified; phase complete.

## Next phase
Phase 5 — Version Diff (`version_id` is still `null` everywhere; chunk UUIDv5 IDs and
content-hash idempotency were designed with versioning in mind).
