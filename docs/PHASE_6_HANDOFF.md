# Phase 6 Handoff — Hardening & Edge Cases

> Status: **DONE** (2026-07-13). Context-preservation document for Phase 6:
> concurrency safety, RFC 7807 errors, rate limiting, PDF hardening, and
> dependency resilience on top of the Phase 1–5 feature set.

## What Phase 6 added (by deliverable)

### A. Data integrity & transaction safety
- `evidence_items.version` (int, migration `c5e8a1f92b47`) mapped with
  SQLAlchemy `version_id_col`: every UPDATE runs `WHERE version = <loaded>`,
  so a lost race raises `StaleDataError` instead of silently overwriting.
  The service translates it (after rollback — nothing is written) into a
  409 `stale_version` problem.
- Review POST and evidence PATCH accept an optional `expected_version`;
  when it no longer matches, the API answers 409 `stale_version` up front.
  The web drawer/map send the version they are rendering and refetch on
  conflict.
- Re-extraction takes `pg_try_advisory_xact_lock(document key)` for the
  length of its transaction; a parallel extraction of the same document gets
  409 `extraction_in_progress`. Key = first 8 bytes of the document UUID
  (signed big-endian), see `services/evidence.py:_advisory_key`.

### B. RFC 7807 problem details (`errors.py`)
- Every error response is `application/problem+json` with `type`
  (`/errors/<code>`), `title`, `status`, `detail`, `instance` (request path)
  plus extensions `code` (stable machine id, kept from the pre-7807 API so
  existing clients/tests survive) and `request_id`.
- Handlers: `AppError`, `RequestValidationError` (client-safe `errors`
  list of `{loc, msg}` — pydantic `ctx`/`url` never leak),
  `StarletteHTTPException`, DB `OperationalError`/`InterfaceError` → 503,
  and a catch-all that logs the traceback and returns a masked 500.
- `X-Request-ID` is accepted (sanitized, capped at 64 chars) or generated,
  echoed on every response, stamped on problem bodies and every log line
  (`observability.py`, contextvar + pure-ASGI middleware — BaseHTTPMiddleware
  was avoided deliberately: it buffers SSE).
- Structured JSON logging: one JSON object per line (timestamp, level,
  logger, message, request_id, exc_info). Configured once per process;
  `LOG_JSON=false` switches to plain formatting for local debugging.

### C. Rate limiting (`ratelimit.py`)
- Sliding-window limiter (60s window) keyed by bucket + client IP, stored on
  `app.state`. `/ask` and `/chat` share one bucket
  (`RATE_LIMIT_ASK_PER_MINUTE=30`); extraction has its own
  (`RATE_LIMIT_EXTRACT_PER_MINUTE=10`). Over-limit → 429 `rate_limited`
  problem with a computed `Retry-After` header. `RATE_LIMIT_ENABLED=false`
  disables it.
- Memory-backed and per-process by design (MVP single-process uvicorn); the
  limiter sits behind a plain `check(key, limit) -> retry_after|None`
  interface so a Redis implementation can drop in for multi-process.

### D. Hardened PDF processing
- Upload pre-check (`processing/pdf_checks.py`, run via `anyio.to_thread`):
  `%PDF-` signature, parseability, encryption, page cap
  (`MAX_PDF_PAGES=2000`), and sampled text-layer detection (5 pages spread
  across the document). Rejections are typed 422/413 problems
  (`pdf_corrupted`, `pdf_encrypted`, `empty_text_layer`, `file_too_large`);
  the stored file is unlinked and no document row is created.
- The pipeline re-validates everything on every (re)process, including a
  whole-document `EMPTY_TEXT_LAYER` check, since stored files may predate
  the pre-check.
- **Behavior change vs Phase 2**: scanned/blank PDFs now fail the upload with
  422 instead of becoming READY documents with zero chunks. OCR remains out
  of scope.

### E. Dependency resilience (`resilience.py`)
- OpenAI clients: 60s timeout, SDK retries off; tenacity owns retries —
  3 attempts, exponential backoff with full jitter, only for
  APIConnectionError/APITimeoutError/RateLimitError/InternalServerError.
  LLM streams retry only while being established, never mid-flight
  (a restarted stream could emit duplicate tokens).
- Qdrant clients get a 10s timeout.
- DB: `pool_pre_ping=True` plus retried connection acquisition (3 attempts,
  jittered backoff) in `get_session`. Mid-transaction statements are
  deliberately NOT retried — retrying inside a broken transaction risks
  partial writes; instead connection-level failures map to a 503
  `service_unavailable` problem with `Retry-After: 5`.
- Chaos fallbacks: embeddings/Qdrant down during search → keyword-only
  results (`semantic_used=false`); down during ingestion → chunks persist
  unembedded and the document still becomes READY (picked up on reprocess).
  This closes a gap found by the new chaos test: previously an embedding
  outage FAILED the whole document.

## Invariants confirmed intact
- UUIDv5 chunk ids, citation provenance snapshots, verification strictness,
  Phase 3 `/ask`/SSE schemas (SSE `error` events still use `code`/`message`),
  append-only review events, archive-on-re-extraction. The `code` extension
  member keeps the old error contract readable by pre-7807 clients.

## Web changes
- `errorMessage()` reads RFC 7807 `detail` (falls back to `message` for SSE
  events). `ApiError` type mirrors the problem shape.
- Review drawer and Evidence Map send `expected_version` with mutations; a
  409 `stale_version` triggers a refetch so the UI shows what won the race,
  plus an explanatory toast.
- `schema.d.ts` regenerated from the live OpenAPI (offline dump, same
  procedure as Phase 5).

## Tests (146 passing, 32 new) and verification
- New suites: `test_problem_details.py` (7), `test_concurrency.py` (5),
  `test_pdf_hardening.py` (6), `test_rate_limit.py` (6),
  `test_resilience.py` (8). Adjusted to Phase 6 contracts:
  `test_documents.py` (corrupt → 422 up front; fixtures now carry a text
  layer), `test_processing.py` (blank PDF → 422), `test_evidence.py`
  (non-READY guard exercised directly).
- Migration `c5e8a1f92b47` verified `upgrade → downgrade → upgrade` on the
  dev DB (tests use `metadata.create_all`, so this is checked separately).
- ruff + pyright + eslint + tsc + `next build` clean; live smoke test below.

## Gotchas for the next phase
- `configure_logging` is once-per-process on purpose (pytest's caplog handler
  must survive repeated `create_app()` calls).
- Tests asserting unhandled-exception behavior need
  `ASGITransport(raise_app_exceptions=False)`.
- The settings singleton is `lru_cache`d; tests tune limits via
  `monkeypatch.setattr(get_settings(), ...)`.
- Rate limiter state is per app instance; each test client gets a fresh one.

## Progress
- 2026-07-13: `639e47a` RFC 7807 + correlation ids + JSON logging.
- 2026-07-13: `a5b3de0` optimistic locking + extraction advisory lock
  (migration `c5e8a1f92b47`).
- 2026-07-13: `d451791` hardened PDF validation.
- 2026-07-13: `d7df36e` sliding-window rate limiting.
- 2026-07-13: `d3b5601` dependency resilience (timeouts/tenacity/DB).
- 2026-07-13: web alignment + docs (this commit). Phase 6 **DONE**.
