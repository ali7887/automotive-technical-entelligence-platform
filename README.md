# ATIP — Automotive Technical Intelligence Platform

ATIP is a verified AI workspace for automotive compliance and engineering documents. It helps teams upload regulations and standards, search them with full provenance, and generate answers only when the supporting evidence can be verified against the source text.

## What ATIP does

ATIP is built for document-first regulatory and engineering workflows where traceability matters more than fluent but unverifiable AI output. The platform combines clause-aware PDF processing, hybrid retrieval, evidence-backed AI answers, and human review tools in one workspace-oriented application.

## Core features

- **Workspace dashboard** — organize documents by regulation, standard, or project with workspace-level rollups for documents, indexed pages, and processing status.
- **Secure sign-in and access control** — server-side sessions with organization isolation and per-workspace roles.
- **PDF upload and processing** — validate, extract, chunk, embed, and index technical PDFs through an asynchronous pipeline with visible job progress.
- **Clause-aware document structure** — preserve clause IDs, headings, section lineage, and page ranges so retrieval results remain auditable.
- **Hybrid search** — combine PostgreSQL full-text search with Qdrant semantic retrieval using Reciprocal Rank Fusion (RRF), with optional reranking.
- **Ask AI with verified citations** — generate answers with inline citations that are shown only when their quotes are validated against retrieved chunks.
- **Evidence Map** — extract requirements from documents into a structured evidence register backed by quote-verified citations.
- **Review Queue and audit trail** — support human review workflows with status transitions, comments, risk tracking, and append-only history.
- **PDF evidence viewer** — open cited pages directly and highlight the quoted text so users can verify claims in context.
- **Export options** — export evidence as JSON or Markdown for downstream review and reporting.
- **Operational health signals** — expose backend readiness and capability status so AI features can degrade clearly and safely when dependencies are unavailable.

## Why it is different

ATIP is intentionally not a generic chatbot. Its core rule is simple: unsupported AI output is not accepted. If a generated answer or extracted requirement cannot be tied to a validated source quote, it is downgraded or withheld instead of being presented as fact.

## Main workflows

1. Sign in and open a workspace dashboard.
2. Upload a regulatory or standards PDF.
3. Wait for asynchronous validation, chunking, embedding, and indexing.
4. Search the document set with keyword or hybrid retrieval.
5. Ask a question and inspect clickable citations in the PDF viewer.
6. Extract reviewable evidence items from a document.
7. Review, annotate, and export the resulting evidence.

## Architecture

```text
Next.js frontend (apps/web)
        |
        v
FastAPI backend (apps/api)
        |
        +-- PostgreSQL   relational data and full-text search
        +-- Qdrant       vector retrieval
        +-- Redis        async job queue
        +-- arq worker   document processing pipeline
```

ATIP is implemented as a monorepo with a Next.js frontend and an async FastAPI backend. The data layer uses PostgreSQL for system-of-record and keyword retrieval, Qdrant for semantic search, and Redis plus arq for background processing.

## Technology stack

- **Frontend:** Next.js, React, TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, Zustand
- **Backend:** FastAPI, Pydantic, SQLAlchemy, Alembic
- **Data and search:** PostgreSQL, Qdrant, Redis
- **AI layer:** OpenAI-compatible generation and embedding clients
- **Quality and tooling:** pytest, pyright, ruff, eslint, TypeScript checks, Docker

## Repository structure

```text
apps/
  api/      FastAPI backend, worker, migrations, tests
  web/      Next.js frontend

docker/     local and production container setup

docs/       roadmap, architecture, deployment, and operations notes

prompts/    prompt templates and feature specifications

scripts/    operational and deployment scripts
```

## Key product behavior

### Verified RAG

ATIP validates generated answers after retrieval. Quotes cited by the model are checked against the exact retrieved text. Results are labeled according to verification outcome, and unsupported answers are not shown as trustworthy output.

### Evidence-first UX

Citations are first-class. Search results, AI answers, evidence items, and review actions all link back to the underlying document page and source quote.

### Graceful degradation

If AI generation is unavailable, the platform does not fail blindly. Keyword search and document access remain available, while generation-dependent actions are disabled with clear status messaging.

## Typical capabilities available in the UI

- Dashboard with workspace KPIs and processing indicators
- Workspace cards and document lists
- Upload controls and job-state feedback
- Search panel with provenance-rich results
- Ask AI panel with inline citation buttons
- Evidence Map for requirement extraction and review
- Review Queue with audit history and reviewer actions
- Shared PDF viewer for source inspection
- Health/status indicators for backend capability gating

## Local development notes

The project is designed to run with containerized supporting services and separate web and API applications. In a typical local setup:

- the frontend runs on `http://localhost:3000`
- the API runs on `http://127.0.0.1:8000`
- supporting services include PostgreSQL, Redis, and Qdrant

Common observed environment variables include:

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `LLM_MODEL`

Refer to the repository's `docs/` directory and project configuration files for exact setup, deployment, and environment details.

## Quality and verification

The implementation includes automated backend tests, static analysis, and type checking. The system also uses typed API contracts and runtime validation at boundaries such as streaming events.

## Current limitations

Known gaps or future-phase areas include:

- OCR for scanned PDFs is not implemented
- dark mode is not fully tuned as a supported surface
- some AI features depend on external model credentials
- semantic retrieval and reranking can be environment-dependent
- reviewer identity may still be simplified in MVP flows

## Documentation

For deeper technical and operational details, review:

- `docs/`
- `prompts/`
- `CLAUDE.md`

## Summary

ATIP is a traceable, evidence-backed AI platform for automotive technical documents. Its value is not only in finding answers, but in proving where those answers came from.

## Contributing

Contribution rules, golden rules (citation provenance is sacred; no mock data
in production paths), and non-goals live in `CLAUDE.md`. Use conventional
commits; keep changes small and reviewable.

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE).