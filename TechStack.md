ATIP Implementation Report

## 1. Project Overview

What it is. ATIP (Automotive Technical Intelligence Platform) is a verified AI workspace for automotive compliance and engineering documents (FMVSS, UNECE regulations, ISO standards). It is a monorepo with a FastAPI backend (apps/api/) and a Next.js frontend (apps/web/), backed by PostgreSQL, Qdrant, and Redis.

Problem it solves. Compliance engineers cannot act on unverifiable LLM output. ATIP's core invariant, enforced in code rather than by prompt-hoping: no AI statement is ever shown or stored unless its supporting quote is found verbatim in a retrieved chunk. Answers that fail verification are withheld (verification.py:229-241); extracted requirements without a validated citation are never persisted (evidence.py:198-200).

Workflows supported today:

Sign in (server-side sessions) → dashboard of workspaces with document rollups.
Upload a regulation PDF → validated, clause-aware chunked, embedded, indexed (async job with staged progress).
Hybrid search (keyword + semantic, RRF-fused, optionally reranked) with clause/page provenance.
Ask AI: streamed verified answers with clickable [n] citations that open the PDF at the cited page with the quote highlighted.
Evidence Map: LLM extraction of normative requirements per document, each backed by quote-verified citations; inline compliance-status/risk editing; JSON/Markdown export.
Review Queue: an audited human-review state machine over evidence items with an append-only event trail.


## 2. Tech Stack

Layer	Technology	Where	Why (in this project)
Frontend framework	Next.js 16.2.10 (App Router), React 19.2.4	apps/web/	App Router + middleware give route guards and a same-origin /api/* dev proxy (next.config.ts) so the HttpOnly cookie is always first-party
Frontend language	TypeScript 5, strict	apps/web	End-to-end type safety against generated API types
Styling	Tailwind CSS v4 (CSS-first @theme)	globals.css	Token-driven theming; every component consumes CSS variables, never raw hex
Components	shadcn/ui on Base UI (@base-ui/react), CVA variants, lucide-react icons	components/ui/	Owned, editable primitives instead of a locked component library
Server state	TanStack Query v5	every panel	Caching, polling (refetchInterval fns), invalidation graph across tabs
Client state	Zustand v5 (two small stores)	lib/store.ts	Cross-component signals only: upload-job tracker, evidence-viewer target
API client	openapi-fetch + openapi-typescript	lib/api/client.ts, schema.d.ts	OpenAPI is the source of truth; pnpm gen:api regenerates types from the live spec
Runtime validation	zod v4	lib/api/stream.ts, lib/validation.ts	SSE payloads are outside the OpenAPI surface, so they're zod-validated at the stream boundary
PDF rendering	react-pdf 10 / pdfjs-dist 5	pdf-viewer.tsx	In-app page rendering with a text layer used for quote highlighting
Backend	FastAPI (async) + Pydantic v2 + pydantic-settings	apps/api/src/atip_api/	Async end-to-end (asyncpg, AsyncQdrantClient, AsyncOpenAI); typed settings with production fail-fast checks (config.py:103-123)
ORM/migrations	SQLAlchemy 2.x (typed Mapped) + Alembic (8 migrations)	models/, apps/api/alembic/versions	Migrations include FTS generated column, review workflow, optimistic locking, tenancy
Primary DB	PostgreSQL 16 (pgvector image)	docker compose	Relational data and the keyword search leg (generated tsvector + GIN index on chunks)
Vector DB	Qdrant 1.18	vectorstore.py	Cosine ANN over 1536-dim embeddings; point id = Postgres chunk UUID; payload-indexed workspace/document filters
Queue/worker	Redis 7 + arq	queue.py, worker.py	arq chosen over Celery/RQ because the pipeline is already coroutine-based and arq runs async natively (no fork — works on Windows dev)
AI	OpenAI-compatible clients (AsyncOpenAI), text-embedding-3-small, gpt-4o-mini default, temperature 0	ai/	Protocol-based abstractions so tests inject deterministic fakes; base_url override supports any compatible provider
Resilience	tenacity (exp backoff + full jitter, 3 attempts)	resilience.py	SDK retries disabled; one explicit retry policy for transient OpenAI/DB errors
Auth	Opaque session tokens, bcrypt, SHA-256 token hashes	auth.py	Server-revocable sessions (delete row = instant logout) instead of JWTs
Testing	pytest + pytest-asyncio (23 test files + 7-flow e2e smoke suite), ruff, pyright; eslint + tsc on web	apps/api/tests, apps/api/tests_e2e	LLM-free deterministic tests via fake clients
Deployment	Docker: dev compose (pg/redis/qdrant), prod compose with Caddy TLS edge, internal-only data network, arq worker service, Vector/Loki log shipping	docker/	Single-server production topology; only Caddy publishes ports


## 3. Feature-by-Feature Breakdown
3.1 Authentication & Sessions
Purpose: Provisioned-account login with revocable server-side sessions and tenant isolation.
User-facing behavior: /login card form; failures show one identical RFC 7807 message for unknown email / bad password / deactivated account (anti-enumeration, routers/auth.py:60-77); ?next= redirect honored only for internal paths (login/page.tsx:1000-1002); sign-out in the header.
Backend endpoints: POST /api/auth/login (rate limited 10/min/IP), POST /api/auth/logout (idempotent), GET /api/auth/me.
Logic/patterns: bcrypt password hashes run off the event loop via anyio.to_thread; login mints a 32-byte secrets.token_urlsafe token, stores only its SHA-256 in a sessions row with TTL (14-day default), client IP, and user agent; cookie is HttpOnly + SameSite=Strict + Secure-in-production. Expired sessions are deleted lazily on first use. RBAC: PLATFORM_ADMIN/ORG_ADMIN/MEMBER account roles plus per-workspace WORKSPACE_EDITOR/WORKSPACE_VIEWER memberships; cross-tenant workspace probes return 404 (not 403) so foreign workspaces are indistinguishable from nonexistent ones (auth.py authorize_workspace). Route protection is a FastAPI dependency (WorkspaceViewerDep/WorkspaceEditorDep) applied to every workspace-scoped route. On the web, middleware.ts redirects cookie-less visitors to /login (explicitly documented as UX-only, not security), and an openapi-fetch response interceptor hard-redirects to /login on any 401.
Status: Complete. No public registration by design — users are created via python -m atip_api.cli create-user (cli.py).
Limitations: No password reset, no MFA, session list/revocation UI (post-MVP; RBAC beyond this is a stated Non-Goal).
3.2 Workspaces (CRUD + Dashboard)
Purpose: A workspace groups documents for one regulation/standard/project inside an organization.
User-facing behavior: Dashboard shows a 4-KPI row (Workspaces / Documents / Pages indexed / Processing) and a card grid. Each card is a stretched-link with a derived state badge, doc/page counts, "Updated" date, and a ⋯ menu (Rename dialog, Delete confirm via AlertDialog). Empty/loading/error states all exist.
Endpoints: POST/GET/PATCH/DELETE /api/workspaces[/{id}] — creator becomes editor; listing is membership-scoped.
Logic: use-workspace-overviews.ts fans out one documents query per workspace with useQueries (shared ["documents", id] cache keys with the detail page), reduces to per-workspace rollups (documentCount/pageCount/ready/processing/failed/updatedAt), and only publishes dashboard totals once every workspace has reported so KPIs never undercount. Badge priority: failed > processing > ready > empty (workspace-list.tsx:27-42). Processing KPI is a derived status function (dashboard-view.tsx:51-66). Name validation: shared zod schema (trim, 1–200 chars) mirroring the Pydantic constraint.
Status: Complete.
3.3 Document Upload & Processing Pipeline
Purpose: Turn a PDF into clause-aware, provenance-carrying retrieval chunks.
User-facing behavior: "Upload PDF" button → hidden file input → 202 Accepted → one sticky sonner toast per job that advances through stage labels ("Queued…", "Extracting text…", "Vectorizing…") and settles success/error (job-watcher.tsx, 1.5 s polling). The Documents tab table polls at 2 s while anything is PENDING/PROCESSING.
Endpoints: POST /api/workspaces/{id}/documents (multipart, editor role), GET .../documents, GET /api/documents/{id}, GET /api/documents/{id}/file (inline FileResponse), GET /api/jobs/{job_id}.
Validation/edge cases (all typed RFC 7807 errors): extension check (415); streamed-to-disk write with a running 50 MB cap (413); upload-time precheck_pdf — %PDF- magic, encryption (422), page cap 2000, scan detection by sampling 5 spread pages for extractable text (422 empty_text_layer) (pdf_checks.py); partial files unlinked on any failure. The pipeline re-validates fully.
Async execution: If QUEUE_ENABLED, the job is enqueued to arq with _job_id = DB job id (double-enqueue is a no-op); on enqueue failure or disabled queue it falls back to FastAPI BackgroundTasks in-process (documents router:50-53). The worker retries unexpected failures with linear backoff up to JOB_MAX_TRIES=3; PdfValidationError is terminal on first try. A crashed worker can't strand a job: reconcile_stale_job lazily fails PENDING/PROCESSING jobs older than 30 min on read (services/documents.py).
Chunking (the real algorithm, chunking.py): pure/deterministic. Regex detects clause-heading lines in two families — UNECE/ISO (6.4.3.1 Heading, requires ≥1 dot) and FMVSS (S5.1.2 Heading). A line-accumulating chunker flushes at a soft target of 450 est. tokens (chars/4), hard max 600, min 200 before a clause boundary may split. Each chunk carries page_start/page_end, clause_id, heading, plus structural lineage computed from headings seen so far: parent_clause_id (nearest ancestor actually printed) and a human-readable section_path ("S14 … > S14.8 … > S14.8.7 …"). Chunk id = UUIDv5 of (document_id, chunk_index, sha256(text)) — deliberately excluding structural metadata, so reprocessing refreshes lineage in place without invalidating embeddings, and doubles as the Qdrant point id.
Indexing: diff-based upsert — stale chunk ids deleted (Postgres + Qdrant), unchanged chunks untouched, only new/unembedded chunks embedded (batch 128). An embedding/Qdrant outage never fails ingestion: chunks persist, search degrades to keyword-only, unembedded chunks are picked up on reprocess (pipeline.py:139-161).
Status: Complete. Limitation: no OCR (Non-Goal), no document delete/re-upload UI (re-upload creates a new document).
3.4 Hybrid Search
Purpose: Provenance-first retrieval across a workspace; also the retrieval engine for Ask AI.
Endpoint: POST /api/workspaces/{id}/search → SearchResponse with per-result SearchScores.
Algorithm (retrieval.py):
Keyword leg — Postgres FTS: generated tsvector column over clause_id + heading + text with GIN index, websearch_to_tsquery, ranked by ts_rank_cd, chunk-id tiebreak; only chunks of READY documents match.
Semantic leg — embed the query, Qdrant cosine query_points filtered by workspace/document payload indexes. Returns None (not an error) when no API key or on runtime failure.
Fusion — textbook Reciprocal Rank Fusion: score(d) = Σ 1/(k + rank), k=60, deterministic sort by (−score, id).
Optional rerank leg — HTTP cross-encoder (Cohere/Jina/TEI-compatible contract) over up to 30 fused candidates; reranked items lead, unscored ones keep RRF order behind them; any failure silently falls back to RRF. Off by default.
Hydrated results re-gated on DocumentStatus.READY (covers Qdrant hits referencing mid-reprocess documents).
UI (search-panel.tsx): useMutation-driven form; result cards show clause badge, document, p./pp. pages, a mono score line (RRF 0.0323 · kw #1 · sem #4), heading, a whitespace-collapsed 4-line excerpt, and an "Open in document" button that opens the shared PDF viewer with the chunk text as highlight quote. A "keyword-only" notice appears when semantic_used is false. Idle/error/no-results states exist.
Status: Complete; reranking implemented but disabled by default (config-dependent). Semantic leg requires OPENAI_API_KEY.
3.5 Ask AI (Verified RAG)
Purpose: Question answering that cannot fabricate citations.
Endpoints: POST /api/workspaces/{id}/ask (JSON) and GET /api/workspaces/{id}/chat (SSE via EventSource — a GET so the cookie flows natively; shares a 30/min rate-limit bucket with /ask).
Generation contract (rag_prompts.py): the model receives numbered sources (document, clause, pages, section path, text) and must emit an answer with inline [n] markers, then a <<<CLAIMS>>> sentinel followed by strict JSON: {not_found, confidence, claims:[{text, citations:[{source, quote}]}]}. Temperature 0.
Verification (deterministic, offline, verification.py): each quote is checked with whitespace-collapsed, casefolded substring matching against the exact retrieved chunk (min 12 chars). Citations to nonexistent sources are dropped; unverified quotes downgrade to "weak" with a chunk excerpt as snippet; inline markers without claims become weak evidence; invalid markers are stripped from the answer text. Zero validated citations ⇒ status unsupported ⇒ the entire answer is replaced with a fixed "Not found" response (JSON: 404; SSE: error event telling the client to discard the streamed draft). Statuses: verified / partial / unsupported / not_found.
Streaming detail: the service withholds a sentinel-length tail of every delta so <<<CLAIMS>>> can never leak into visible tokens (rag.py:126-146). Retrieval completes before streaming starts so no DB session is held mid-stream.
UI (chat-panel.tsx): local Exchange[] state (question, streaming draft with pulse cursor, sources count, final result); zod-validated SSE handlers; verification badge (Verified/Partially verified/Unsupported/Not found), confidence, "keyword-only retrieval" note; [n] markers rendered as interactive buttons via regex split, hover-synced with citation cards (scrollIntoView), click opens the PDF viewer; warning list; per-document scoping select; whole panel gated by generation_enabled from /health with an amber explainer and disabled inputs.
Status: Complete. Environment-dependent: fully disabled (503 generation_disabled) without OPENAI_API_KEY. Limitation: answer_md is rendered as plain text with whitespace-pre-line, not parsed markdown; single-turn (no conversation memory) by design.
3.6 Evidence Map (Verified Requirement Extraction)
Purpose: Turn one document into a reviewable register of normative requirements, each pinned to verified quotes.
Endpoints: POST /api/documents/{id}/evidence/extract (editor, rate-limited 10/min), GET /api/workspaces/{id}/evidence, PATCH /api/evidence/{item_id}, exports (3.9).
Extraction logic (evidence.py): chunks are processed in deterministic batches of 12 in chunk_index order; per batch the LLM must output strict JSON {"requirements":[{text, citations:[{source, quote}]}]} (no streamed prose); every quote runs through the same quote_supported check; requirements are whitespace-normalized and cross-batch deduped casefolded; requirements with zero surviving citations are dropped with a warning, never stored. Concurrency: a Postgres pg_try_advisory_xact_lock keyed on the document id makes parallel extraction a 409. Re-extraction lifecycle: never-reviewed items (NEW, no events) are deleted; items with review state/history are archived (archived_at + a SYSTEM EXTRACTION_ARCHIVED audit event) — provenance is never destroyed. EvidenceCitation.chunk_id is deliberately not a foreign key: citations are provenance snapshots (clause, pages, quote copied at verification time) that must survive reprocessing.
UI (evidence-map-panel.tsx): document picker (READY only) + "Extract requirements" (disabled without generation); results table with requirement text, citation chips (clause id or page) that open the PDF viewer, and inline Status/Risk NativeSelects that PATCH with expected_version + actor_name (optimistic lock; a stale_version 409 triggers a table refetch); toasts report extracted/dropped/archived counts; footer badge "all citations quote-verified".
Status: Complete; requires OPENAI_API_KEY for extraction (viewing/reviewing existing evidence works without).
3.7 Review Queue & Audit Trail
Purpose: Human sign-off on extracted evidence with a tamper-evident history.
Endpoints: GET /api/evidence/review-queue (filters: workspace/document/review_status/risk/include_archived; 6 sorts; limit/offset — tenant-scoped to accessible workspaces when no workspace_id is given), GET /api/evidence/{id}, POST /api/evidence/{id}/review, GET /api/evidence/{id}/history.
State machine (evidence.py:94-107): a pure transition function — START_REVIEW allowed from NEW/NEEDS_REVISION/APPROVED/REJECTED → IN_REVIEW; APPROVE/REJECT/REQUEST_REVISION only from IN_REVIEW; COMMENT/SET_RISK never change workflow status; invalid moves raise 409 and write nothing. Two orthogonal status dimensions: review_status (workflow) vs status (compliance verdict, edited in the Evidence Map).
Audit trail: every mutation appends exactly one EvidenceReviewEvent (action, previous/next status and risk, comment, actor name/type, JSONB extra) with a monotonic Identity seq column because same-transaction timestamps can't order a timeline. Rows are insert-only. Concurrency safety: version column mapped as SQLAlchemy version_id_col; every update runs WHERE version = loaded, and clients send expected_version — lost races are 409 stale_version, never silent overwrites.
UI: review-queue-panel.tsx — filter/sort selects, archived toggle, paginated table (20/page, keepPreviousData), keyboard-operable rows (Enter/Space + focus ring), "append-only audit trail" badge. review-detail-drawer.tsx — slide-over with citations (open in PDF viewer), state-aware action buttons (Reject/Request-revision require a comment), reviewer name persisted in localStorage (reviewer.ts), risk setter, and a newest-first timeline rendering transitions, comments, and system events. Escape-key layering: the drawer ignores Escape while the PDF viewer (which stacks above it) is open.
Status: Complete. Note: actor_name is a free-text reviewer field, not bound to the authenticated user — an acknowledged MVP simplification.
3.8 PDF Viewer & Citation-to-Document Navigation
Purpose: The "verify" in Verified AI — every citation, evidence chip, and search hit lands on the actual page with the quote marked.
Architecture: one global Zustand store (useEvidenceViewer) holds an EvidenceTarget {documentId, documentName, page, quote?, clauseId?}; four producers call openEvidence (chat inline markers + citation cards, evidence map chips, review-drawer citations, search result cards); one consumer, evidence-viewer-panel.tsx, renders a slide-over dialog (backdrop button, Escape, role="dialog", header with clause badge/"evidence on p. N"/open-in-new-tab, clamped "Looking for" quote strip).
Highlighting logic (pdf-viewer.tsx): chunks carry no PDF coordinates, so nothing is invented — the verified quote is located by text matching in pdf.js's text layer via customTextRenderer. Both sides are normalized exactly like the backend verifier (lowercase, collapse whitespace); a text-layer fragment is wrapped in <mark> if it's contained in the quote, contains it, or overlaps its edge by ≥12 chars (suffix/prefix scan, edgeOverlap). Fragment-granularity marking, HTML-escaped.
Details: pdf.js is dynamically imported with ssr: false (touches DOMMatrix/canvas); worker from pdfjs-dist via import.meta.url; ResizeObserver-driven page width (cap 1000 px); prev/next paging with clamping; a "Back to evidence (p. N)" affordance appears when the user navigates away from the cited page; loading/error/no-data states.
Status: Complete. Limitations: text-match highlighting can miss hyphenation/ligature-mangled extractions (fails soft — page still opens); no keyboard paging; no zoom control.
3.9 Exports
JSON: client-side Blob download of GET .../evidence/export (optionally include_history), typed EvidenceMapExport.
Markdown: GET .../evidence/export.md — server-rendered by export_markdown (evidence.py:599-647): grouped by document, per-item status/risk/review/clause line, quoted evidence with p./pp. ranges, optional per-item history; served as a text/markdown attachment. Both filterable by document/review_status/risk. UI disables both buttons at zero items (the anchor case renders a real disabled button since anchors ignore disabled).
Status: Complete.
3.10 Health, Status & Capability Gating
Endpoints (health.py): /health (full diagnostic: Postgres reachable and at Alembic head, Redis PING, Qdrant collection exists with the expected vector dim; any failure → 503 with per-service detail; also reports generation_enabled); /health/live (process-only, for orchestrators); /health/ready (Postgres required; Redis/Qdrant only degrade, since search falls back keyword-only).
Frontend: use-health.ts polls /health every 30 s (treats a 503 body as data, not an error). Consumers: the header chip (health-status.tsx — Operational/Degraded/API offline/Checking with a failing-services tooltip) and useGenerationEnabled(), which gates Ask AI and extraction. Deliberate tri-state: undefined while unknown keeps controls enabled instead of flashing disabled on first load.
Status: Complete.
3.11 Error Handling & API Hygiene (cross-cutting)
Every error is an RFC 7807 problem-details body with code and request_id extensions; ~18 typed AppError subclasses map domain failures to correct statuses (409 for state-machine/optimistic-lock/advisory-lock conflicts, 422 for PDF defects, 429 with Retry-After, 502/503 for generation) (errors.py). Unhandled exceptions are logged with traceback and masked. A correlation id (X-Request-ID, pure-ASGI middleware so SSE isn't buffered) flows through logs, error bodies, and even into worker jobs via the persisted request_id. Structured one-line JSON logging with uvicorn's loggers rerouted (observability.py). Per-IP sliding-window rate limiting (in-memory deques; login 10/min, ask+chat 30/min, extract 10/min) (ratelimit.py).

## 4. UI/Design System Implementation ("ATIP Neutral Technical")
Tokens (globals.css): all color as CSS custom properties bridged into Tailwind v4 via @theme inline. Neutral surfaces (--background #f8fafc, --card #fff, --muted #f3f4f6), near-black primary (#111827), and a single interaction accent #2563eb shared by --ring, --link, --info — blue means "interactive/selected", never decoration. Radius scale derived from one --radius: 0.625rem by multipliers.
Semantic state triads: success/warning/destructive/info, each with -strong (text) and -soft (tint background) variants. Consistency is enforced by convention + shared maps: badges use soft-tint variants defined once in badge.tsx; review/risk colorings live in single lookup tables (review-labels.ts) consumed by queue, drawer, and timeline alike; document pipeline state is one StatusBadge component.
Typography: Geist Sans (UI) / Geist Mono via next/font variables; serif reserved for the ATIP wordmark. Mono + tabular-nums consistently marks technical metadata: clause ids, page refs, scores, counts, timestamps.
Dark readiness: a full .dark variable block exists (functional placeholder, explicitly "not tuned"); components only consume tokens, so dark mode is a variable override away. Light-only is the supported surface — honest partial.
Primitives (components/ui/): shadcn-style on Base UI — Button (CVA: 6 variants × 8 sizes, render prop polymorphism), Badge (10 variants), Card, Dialog, AlertDialog, DropdownMenu, Input, Label, NativeSelect, Skeleton, Table, Sonner toaster, custom TabList/TabPanel (ARIA tablist, underline style, count chips suppressed at zero, panels kept mounted so chat threads survive tab switches), and EmptyState (dashed-border surface with icon tile, title, description, action slot; error variant auto-injects an alert icon).
Interaction/accessibility patterns: universal focus-visible rings (ring-3 ring-ring/50); keyboard-operable table rows; stretched-link cards with has-[a:focus-visible] ring; dialogs with aria-modal, backdrop close, Escape (with viewer-over-drawer layering); aria-labels on icon buttons and filters; role="alert" on the login error.


## 5. Data Flow and Logic Patterns
Same-origin API everywhere: dev proxies /api/* + /health/* through Next rewrites; production routes them at Caddy. The HttpOnly cookie is therefore always first-party — including for EventSource — and CORS never applies in practice.
Server/client split: pages are thin server components; all data-bearing UI is client components on TanStack Query. Query-key architecture doubles as the invalidation graph: ["documents", wsId] is shared by dashboard rollups, documents table, chat's document picker, and evidence panel; a review action invalidates item, history, queue, and evidence list together.
Polling as state machine: refetchInterval callbacks return false once terminal (documents 2 s while processing; job watcher 1.5 s until READY/FAILED; health fixed 30 s).
Verification-first gating (the signature pattern): LLM output → strict parse (Pydantic on the API; zod on SSE) → deterministic quote check → drop/downgrade/withhold. The same quote_supported normalization is reimplemented identically in the PDF highlighter, so "what verified" is exactly "what highlights".
Graceful-degradation ladder: no API key → generation 503 + UI banner, search keyword-only; Qdrant/embedding down → semantic leg returns None, results flagged semantic_used=false; reranker fails → RRF order; queue down → in-process processing; Redis/Qdrant down → API still "ready" (degraded).
Honest small algorithms: RRF summation; sliding-window rate limiting with monotonic deques; deterministic UUIDv5 chunk identity for idempotent reprocessing; token estimation as len/4; excerpt cleanup replace(/\s+/g," ").trim() + line-clamp; page-ref formatting centralized in formatPages; derived status reducers for KPI/badges; advisory-lock keying by the first 8 bytes of the document UUID; optimistic locking via version columns; append-only sequencing via a Postgres Identity column.


## 6. Testing and Verification
Backend: 23 pytest files under apps/api/tests/ (~200 tests; async mode) covering chunking, processing, hybrid search, rerank, verified RAG, evidence extraction/review, auth, concurrency/optimistic locking, rate limiting, resilience/retries, PDF hardening, problem details, health, worker, config fail-fast. LLM/embedding calls are replaced by deterministic fakes behind the Protocol seams in ai/. Plus a 7-flow LLM-free e2e smoke suite (tests_e2e/) runnable against a live deployment via ATIP_E2E_BASE_URL.
Static: ruff + pyright (basic) on the API; eslint + tsc --noEmit on the web. Both web checks pass clean as of this session.
Type-safety chain: Pydantic schemas → OpenAPI → openapi-typescript codegen → openapi-fetch — request/response types are verified at compile time; zod re-validates the untyped SSE boundary at runtime.
CI (per roadmap Phase 7): GitHub Actions with real service containers, an Alembic base↔head round-trip, and the live-server smoke job.
Manual/visual: the recent UI passes were verified with headless-Chrome CDP screenshots (login, dashboard, workspace tabs, 1024 px responsiveness) against the running dev stack.
No frontend unit/component tests — verification there is lint + types + live inspection.


## 7. Outstanding Constraints or Known Gaps
Environment-dependent: Ask AI, extraction, and semantic search require OPENAI_API_KEY (all three degrade explicitly, with UI messaging); reranking needs RERANK_ENABLED + RERANK_URL; async queue needs QUEUE_ENABLED + the worker container (dev default is in-process).
Not implemented (explicit Non-Goals or later phases): OCR/scanned PDFs, Version Diff (a prompt spec exists at prompts/05_version_diff.md; version_id is stored as null in Qdrant payloads and SearchResult rather than invented), diagnostics/CAN/DTC, knowledge graph, billing, enterprise RBAC beyond the two-tier role model.
Partial: dark theme (tokens present, untuned, no toggle); answer_md rendered as plain text, not markdown; reviewer identity is free-text rather than the session user; rate limiter is per-process in-memory (documented as swappable for Redis when multi-process).
Operational notes: no document deletion endpoint; no frontend test suite; PDF quote highlighting is text-match based and can fail soft on unusual text extractions.

## 8. Executive Summary
Fully built: the complete verified-document loop — authenticated multi-tenant workspaces; hardened PDF ingestion with deterministic clause-aware chunking and idempotent re-indexing; hybrid retrieval (Postgres FTS + Qdrant, RRF k=60, optional cross-encoder rerank); verified RAG with streamed SSE answers, offline quote verification, and answer withholding; verified requirement extraction into an Evidence Map; an audited review workflow with a state machine, optimistic locking, and an append-only event trail; a shared PDF evidence viewer that closes the loop from every citation back to the highlighted source page; JSON/Markdown exports; and production infrastructure (Caddy TLS edge, internal-only data network, arq worker, liveness/readiness probes, RFC 7807 + correlation-id observability, CI with real services).

Production-polished: the full UI surface — token-driven design system, consistent loading/empty/error/disabled states on every panel, capability gating tied to live backend health, accessible focus/keyboard behavior — validated by lint, typecheck, ~200 backend tests, and live screenshot review.

Remaining/future-phase: Version Diff, OCR, markdown answer rendering, tuned dark mode, frontend tests, Redis-backed rate limiting, and binding reviewer identity to the session user.