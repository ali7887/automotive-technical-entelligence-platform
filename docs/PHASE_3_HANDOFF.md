# Phase 3 Handoff — Verified RAG

## Status
Phase 3 (Verified RAG) completed, verified end-to-end (live API + real browser), committed.

## Delivered

### Backend
- `ai/llm.py`: streaming chat client behind a protocol (mirrors `ai/embeddings.py`);
  `get_llm_client()` returns `None` without `OPENAI_API_KEY`. Model from `LLM_MODEL`
  (default `gpt-4o-mini`), `temperature=0`.
- LLM output contract (`services/rag_prompts.py`): answer text with inline `[n]`
  markers, then a `<<<CLAIMS>>>` sentinel followed by strict JSON
  `{"not_found", "confidence", "claims": [{"text", "citations": [{"source", "quote"}]}]}`.
  This keeps tokens streamable while claims stay machine-checkable.
- Verification layer (`services/verification.py`), fully offline/deterministic:
  - every claim quote is matched verbatim (whitespace/case-normalized, min 12 chars)
    against the exact retrieved chunk text
  - citation statuses: `validated` (quote found) / `weak` (source exists, quote not
    verifiable — snippet falls back to a real chunk excerpt, never the unverified quote)
  - citations to nonexistent source indices are dropped; their inline markers are
    stripped from the answer
  - zero validated citations ⇒ `not_found: true` and the answer is replaced with the
    standard "Not found" text (weak support never ships as an answer)
  - malformed/missing claims JSON ⇒ treated as unverifiable ⇒ `not_found`
  - first validated quote per source wins `source_text_snippet`
  - answer status: `verified` | `partial` | `unsupported` | `not_found`
- Endpoints (`routers/rag.py`):
  - `POST /api/workspaces/{id}/ask` → full `AskResponse`: `answer_md`, `not_found`,
    `confidence`, structured `citations` (`citation_id` = inline `[n]`,
    `postgres_chunk_id`, `clause_id`, `page_start/end`, `source_text_snippet`,
    `status`), `verification` breakdown, numbered `sources`, `semantic_used`, `model`
  - `GET /api/workspaces/{id}/chat` → SSE: `sources` → `token`* → `final`
    (full `AskResponse`) or `error`; query params `question`, `document_id`, `top_k`
  - streamed tokens are the unverified draft; a sentinel-sized holdback guarantees the
    claims block never leaks; clients must replace the draft with `final.answer_md`
  - retrieval reuses the Phase 2 `SearchService` (RRF hybrid) and runs before
    streaming starts; empty retrieval short-circuits to `not_found` without an LLM call
  - no `OPENAI_API_KEY`: `POST /ask` → 503 `generation_disabled` with a user-friendly
    message; `/chat` → SSE `error` event; search stays fully functional
  - LLM failures: 502 `generation_failed` (POST) / SSE `error` event (never a hang)

### Web
- `components/chat/chat-panel.tsx` on the workspace page: single-turn QA thread with
  streaming draft, verification badge (Verified / Partially verified / Not found /
  Unsupported), confidence, warnings, and a document filter (`READY` docs only).
- Inline `[n]` markers render as buttons; hover/click highlights (and scrolls to) the
  matching source card (document, clause badge, pages, quoted snippet); weak citations
  are labeled "unverified quote".
- `lib/api/stream.ts`: EventSource client; SSE payloads are zod-validated at the
  stream boundary (they are outside the OpenAPI surface). A `MessageEvent` named
  `error` is a structured server error; a bare `Event` is a connection failure.
- Typed client regenerated from the app's OpenAPI (`AskResponse`, `Citation`,
  `RetrievedSourceRead`).

## Important implementation notes
- **No conversation memory**: each question is answered independently (chat history is
  client-side display only). Server-side memory was not in Phase 3 scope.
- **Provenance is never invented**: citations can only reference chunks that were
  actually retrieved and shown to the model; `version_id` remains `null` (Phase 5).
- The roadmap's "clicks highlight correct PDF region" is satisfied at the metadata
  level (citation → document/clause/page/quote highlight). In-PDF region highlighting
  needs the PDF viewer and belongs with the Evidence Map / viewer work.
- `OPENAI_API_KEY` is still unset on this machine; the live degraded path is the
  default experience until a key is configured.

## Verification
- `uv run pytest`: 65 passed — verification unit tests incl. adversarial cases
  (fabricated quotes, fake source indices, malformed claims JSON, unanswerable
  questions, too-short quotes) and endpoint tests with a deterministic fake LLM
  (streamed in 7-char pieces to exercise sentinel holdback).
- `ruff` + `pyright` clean; `pnpm lint` + `pnpm typecheck` clean.
- Live E2E: real PDF uploaded → READY; no-key path returns 503/`error` event with
  search unaffected; with a local OpenAI-compatible stub, `/ask` returned
  `verification.status: "verified"` with the citation mapping to the real chunk
  (clause `S14.8.7`, page 1) and `/chat` streamed `sources` → 14 `token`s → `final`
  with zero sentinel leakage; web UI driven in Chrome (loading → streaming → verified
  answer with clickable citations; disabled state without key).

## Next phase
Phase 4 — Evidence Map (per prompts/04_evidence_map.md). Verified answers already
expose everything it needs: per-answer sources, claims, and validated citations.
