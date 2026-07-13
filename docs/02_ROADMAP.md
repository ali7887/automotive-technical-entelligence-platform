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

## Phase 3 — Verified RAG (Done — see PHASE_3_HANDOFF.md)
- LLM orchestration over retrieved chunks (ask + SSE chat endpoints)
- structured answer validation (claims + citation mapping)
- workspace chat UI with streaming and verified inline citations
Acceptance:
- zero fabricated citations: every citation is quote-verified against real chunks
- citation clicks highlight the source (document, clause, page, quote);
  in-PDF region highlighting is deferred to the PDF viewer work (see handoff)

## Phase 4 — Evidence Map & PDF Traceability (Done — see PHASE_4_HANDOFF.md)
- PDF traceability: file-serving endpoint + in-app react-pdf viewer; inline [n]
  citations and evidence cards open the viewer at the cited page with the
  verified quote highlighted via text-layer matching (chunks carry no
  coordinates; nothing is invented)
- Supporting Evidence panel on answers with "Verify on document" buttons
- verified requirement extraction per document (LLM + Phase 3 quote
  verification; only requirements with validated citations persist)
- Evidence Map UI table with editable status/risk; export as JSON + Markdown
Acceptance:
- clicking a citation opens the source PDF at the right page and highlights
  the quoted text
- extracted evidence items map to real chunks; fabricated quotes are dropped
  and surfaced as warnings (verified live with a stub LLM)

## Phase 5 — Review Workflow & Audit Trail (Done — see PHASE_5_HANDOFF.md)
- review workflow on evidence items: NEW/IN_REVIEW/APPROVED/REJECTED/
  NEEDS_REVISION with an explicit server-side state machine (invalid
  transitions → 409, nothing written)
- append-only `evidence_review_events` audit table; every mutation (workflow
  actions, inline status/risk edits, system archival) appends exactly one event
- re-extraction lifecycle: unreviewed items are replaced; items with review
  state or history are archived (citations + audit trail preserved), never
  silently deleted
- Review Queue UI: filters (review status, risk, archived), sorting,
  pagination, detail drawer with citations, state-aware actions, and a
  history timeline
- exports carry review metadata and optionally the full per-item history
Acceptance:
- every review decision is traceable: who, what, when, from→to status
- rejected transitions write nothing; audit history is strictly append-only
- re-extraction never destroys reviewed evidence (verified by integration
  tests and a live smoke test)
