# Phase 5 Handoff — Review Workflow & Audit Trail

> Status: **DONE** (started 2026-07-08, completed 2026-07-13). This file is the
> context-preservation document for Phase 5.

## What was completed in Phases 1–4

### Phase 1 — Foundation (done)
- Monorepo (pnpm + uv): `apps/web` (Next.js App Router, Tailwind, shadcn/ui, TanStack
  Query, generated OpenAPI client) + `apps/api` (FastAPI async, SQLAlchemy 2.x, Alembic).
- Docker Compose: Postgres+pgvector, Redis, Qdrant. **This machine uses non-default
  ports 5433 / 6380 / 6335 on 127.0.0.1** (defaults are broken locally).
- Workspace CRUD, PDF upload to local storage, background processing jobs with status
  polling, E2E health check.

### Phase 2 — Retrieval (done)
- Deterministic chunking with provenance (`chunk_index`, `page_start/end`, `clause_id`
  nullable and never invented, `heading`, exact `text`, `content_hash`).
- **Chunk IDs are deterministic UUIDv5** of document + index + content hash; reprocessing
  is idempotent.
- Hybrid retrieval: Postgres FTS + Qdrant semantic search fused with RRF.
- Without `OPENAI_API_KEY`: FTS still works, semantic search skipped honestly, no mocks.

### Phase 3 — Verified RAG (done)
- `POST /api/workspaces/{id}/ask` and SSE `GET /api/workspaces/{id}/chat`.
- Verification layer (`services/verification.py`), offline and deterministic:
  claim quotes matched **verbatim** (whitespace/case-normalized, min 12 chars) against
  exact retrieved chunk text; citation status `validated`/`weak`; fabricated source
  indices dropped; zero validated citations ⇒ `not_found`.
- Web chat panel with streaming, verification badge, inline `[n]` citation buttons.

### Phase 4 — Evidence Map & PDF Traceability (done)
- `GET /api/documents/{id}/file` streams the stored PDF; react-pdf viewer
  (`components/pdf/pdf-viewer.tsx`, client-only) highlights the verified quote via
  text-layer matching; **fallback is page-level navigation** (chunks carry no
  coordinates; nothing is invented).
- Verified requirement extraction (`services/evidence.py`): LLM proposes requirements
  over batches of 12 chunks; every citation quote is verified with the Phase 3
  `quote_supported` rules; only requirements with ≥1 validated citation persist;
  fabrications are dropped and surfaced as warnings.
- Persistence: `evidence_items` (reviewer-owned compliance `status` + `risk`) and
  `evidence_citations` (**provenance snapshots**: chunk_id with deliberately **no FK to
  chunks**, clause_id, pages, verified quote) — migration `9d4e1f6a2c53`.
- Evidence Map UI table with editable status/risk, citation chips that open the PDF
  viewer, JSON + Markdown export.
- 94 API tests passing at Phase 4 close; ruff/pyright/eslint/tsc clean.

## Current state of the key subsystems

- **Retrieval**: stable; `POST /api/workspaces/{id}/search` (hybrid RRF).
- **Verification**: `services/verification.py` is the single source of truth for quote
  verification; both `/ask` and evidence extraction use it. Do not weaken it.
- **PDF traceability**: `GET /api/documents/{id}/file` + `useEvidenceViewer` zustand
  store + `evidence-viewer-panel.tsx`. Any UI that shows a citation opens the viewer via
  `openEvidence({documentId, documentName, page, quote, clauseId})`.
- **Evidence extraction**: synchronous, per READY document,
  `POST /api/documents/{id}/evidence/extract`. As of Phase 4 close, re-extraction
  **replaced** all of the document's items (including reviewer state) — Phase 5 changes
  this (see lifecycle strategy below).

## Architectural invariants — must not be broken

1. **Stable chunk IDs** — UUIDv5 derivation of chunk IDs must not change.
2. **No invented provenance** — clause IDs, pages, quotes are copied from real chunks
   only; never guessed.
3. **Verification stays strict and verbatim** — whitespace/case-normalized exact
   matching, minimum quote length; no fuzzy matching, no thresholds loosened.
4. **Evidence citations are provenance snapshots** — `evidence_citations.chunk_id` has
   no FK to `chunks` on purpose; snapshots must survive chunk reprocessing.
5. **PDF highlighting degrades gracefully** — quote-not-found on the text layer must
   fall back to page-level navigation, never an error, never invented coordinates.
6. **Phase 3 `/ask` must not regress** — schema, verification semantics, and SSE
   sentinel holdback are frozen.
7. **Degraded-mode honesty** — no `OPENAI_API_KEY` ⇒ explicit 503, never mock output.
8. **Type-safety chain** — Pydantic → OpenAPI → regenerated typed web client.

## Known implementation constraints

- **Extraction is synchronous** — acceptable for MVP-sized documents; do not build
  background jobs in Phase 5.
- **`pdfjs-dist` must remain a direct dependency** in `apps/web/package.json`
  (pnpm strict node_modules; the Turbopack build breaks otherwise).
- **Avoid recursive repo scans** — `node_modules`/`.venv`/`.next` make broad globs time
  out on this machine; read only files needed for the active phase.
- Local dev DB/services: 127.0.0.1:5433 (Postgres), 6380 (Redis), 6335 (Qdrant).
- Enum values in this codebase are UPPERCASE `StrEnum`s (`EvidenceStatus`,
  `EvidenceRisk`, …); new enums follow the same convention.

## Phase 5 scope — Review Workflow & Audit Trail

Add a human review workflow over evidence items: explicit review status
(`NEW`/`IN_REVIEW`/`APPROVED`/`REJECTED`/`NEEDS_REVISION`), review actions
(`START_REVIEW`/`APPROVE`/`REJECT`/`REQUEST_REVISION`/`COMMENT`/`SET_RISK`), an
append-only `evidence_review_events` audit table, a Review Queue UI with filtering/
sorting/detail drawer/history timeline, and exports that carry review metadata and
optionally history.

**Kept separate from provenance**: review data lives on `evidence_items` (current
snapshot) and in `evidence_review_events` (append-only history). `evidence_citations`
is never touched by review actions.

**Two status dimensions, on purpose**: the Phase 4 compliance `status`
(OPEN/COMPLIANT/…) answers *"is the product compliant with this requirement?"*; the new
`review_status` answers *"has a human reviewed this extracted evidence?"*. Phase 5 adds
`review_status` without disturbing the Phase 4 field.

### State machine (authoritative)
- `START_REVIEW`: allowed from `NEW`, `NEEDS_REVISION`, `APPROVED`, `REJECTED`
  (re-opens a decided item) → `IN_REVIEW`. Not allowed from `IN_REVIEW`.
- `APPROVE` / `REJECT` / `REQUEST_REVISION`: allowed only from `IN_REVIEW` →
  `APPROVED` / `REJECTED` / `NEEDS_REVISION`. Comment **required** for `REJECT` and
  `REQUEST_REVISION`.
- `COMMENT`: allowed from any status; no status change; comment required.
- `SET_RISK`: allowed from any status; no status change; `risk` required.
- Invalid transitions ⇒ 409 with a clear message; nothing is written.
- Every accepted action appends exactly one `evidence_review_events` row.

### Re-extraction lifecycle rule (risk register #1)
Re-extraction must not silently destroy reviewed evidence:
- items whose `review_status` is `NEW` **and** have no review events are hard-deleted
  (nothing to preserve);
- items with any review history are **archived** (`archived_at` set), keeping their
  citations and full audit trail; archived items are excluded from the queue and
  exports by default.
- An `EXTRACTION_ARCHIVED` system event is appended to each archived item so the
  timeline explains why it left the queue.

### Audit-bypass rule (risk register #2)
`PATCH /api/evidence/{item_id}` (Phase 4 inline status/risk edits) now also appends
audit events for what it changes; it cannot mutate `review_status` — workflow
transitions go through `POST /api/evidence/{item_id}/review` only.

## Implementation notes (what shipped, and the one design addition)

- **Backend** (`a4da252`): models/schemas/repository/service as planned, plus router
  endpoints `POST /api/evidence/{id}/review`, `GET /api/evidence/{id}` (detail with
  event_count/last_event), `GET /api/evidence/{id}/history`,
  `GET /api/evidence/review-queue` (filters/sort/pagination; declared before the
  `{item_id}` routes so the literal path wins), and export endpoints extended with
  `document_id`/`review_status`/`risk`/`include_history` query params.
- **`seq` column added to `evidence_review_events`** (BigInteger Identity, unique,
  indexed with item id): `created_at` is transaction-fixed in Postgres, so two events
  written in one request (e.g. PATCH changing status *and* risk) had no deterministic
  order. History is ordered by `seq` everywhere. Caught by the audit-integrity test.
- Migration `b7a3c9e51d24` verified `upgrade → downgrade → upgrade` on the dev DB.
- **Web** (`e44ec38`): `components/review/review-queue-panel.tsx` (filters, sort,
  archived toggle, pagination, loading/empty/error states) +
  `review-detail-drawer.tsx` (citations → PDF viewer click-through, state-aware
  actions, comment gating for REJECT/REQUEST_REVISION, risk setting, history
  timeline). Reviewer name persists in localStorage (`lib/reviewer.ts`) and is sent
  as `actor_name` on review actions **and** on audited Evidence Map inline edits.
  Evidence Map exports gained an include-history toggle. The review drawer sits at
  z-40 under the PDF viewer (z-50) and hides while the viewer is open; Escape closes
  the viewer first, then the drawer.
- **Tests**: 114 API tests passing (20 new in `tests/test_evidence_review.py`:
  transition matrix, comment/risk payload rules, audit ordering + write-nothing on
  409, queue filtering/sorting/pagination, re-extraction archive lifecycle,
  archived-item read-only, export metadata/history). ruff + pyright + eslint + tsc
  clean; `next build` passes.
- **Smoke test** (live server on the alembic-migrated dev DB): full cycle
  START_REVIEW → REJECT(422 without comment) → REJECT → reopen → APPROVE, history
  and detail endpoints, markdown export with history — all verified over HTTP.

## Progress
- 2026-07-08: repo state audited (Phase 4 verified done); this handoff written;
  implementation plan proposed.
- 2026-07-13: backend milestone committed (`a4da252` — endpoints, seq audit ordering,
  20 tests, migration verified both directions).
- 2026-07-13: web milestone committed (`e44ec38` — Review Queue UI, detail drawer,
  timeline, reviewer identity, export history toggle). Phase 5 **DONE**.
