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

## Phase 6 — Hardening & Edge Cases (Done — see PHASE_6_HANDOFF.md)
- optimistic locking on evidence items (version column + expected_version);
  lost races → 409, never a silent overwrite; re-extraction holds a
  per-document advisory lock (parallel extraction → 409)
- RFC 7807 problem details on every error (type/title/status/detail/instance
  + code/request_id extensions); internals masked on 500s and logged
- correlation IDs (X-Request-ID) + structured one-line JSON logging
- rate limiting on /ask, /chat, and extraction (429 + Retry-After)
- hardened PDF intake: signature/encryption/page-cap/text-layer checks at
  upload (422/413 problems), blocking parsing kept off the event loop
- dependency resilience: deterministic timeouts (OpenAI/Qdrant), tenacity
  backoff with jitter, DB pre-ping + retried connection acquisition,
  keyword-only search fallback when embeddings are down
Acceptance:
- concurrent edits to one evidence item produce 409, data is never clobbered
- corrupt/encrypted/scanned PDF uploads return clean RFC 7807 422/413 payloads
- transient DB/LLM outages retry up to 3 times and degrade gracefully
  (search stays available keyword-only); Phase 3–5 regressions all green

## Phase 7 — Release Readiness & Go-Live Preparation (Done — see PHASE_7_HANDOFF.md)
- environment-aware configuration: ENVIRONMENT=production fail-fasts on
  dev-default DB credentials / relative STORAGE_DIR; OPENAI_API_KEY is a
  SecretStr; numeric limits validated at startup; .env.example is the
  complete config reference
- liveness (/health/live, never touches deps, reports version + BUILD_SHA)
  and readiness (/health/ready: Postgres required, Redis/Qdrant only degrade)
  split from the strict /health diagnostic
- GitHub Actions CI: lockfile-frozen installs, ruff/pyright/pytest with real
  service containers, migration round-trip (base ↔ head), eslint/tsc/next
  build, live-server E2E smoke job
- production API container (multi-stage uv, non-root, ships alembic for
  same-image migrations, liveness-only HEALTHCHECK)
- release smoke suite (apps/api/tests_e2e): 7 deterministic LLM-free flows
  over real HTTP, reusable as the post-deploy check via ATIP_E2E_BASE_URL
- docs/12_RELEASE_RUNBOOK.md: topology, deploy/migration order, probes,
  healthy-but-degraded semantics, rollback notes, known limitations
Acceptance:
- a misconfigured production boot fails with an actionable error, never a
  silently insecure default
- CI reproduces every documented local check from a clean clone
- the smoke suite passes against a live deployment without an LLM key
