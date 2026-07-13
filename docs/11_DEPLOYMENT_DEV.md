# Dev & Deployment Notes (MVP)

- Docker Compose orchestrates: PostgreSQL (with pgvector), Redis, and Qdrant locally.
- CORS: Backend must explicitly allow Next.js local port (default 3000) and production Vercel domain.
- Frontend is configured to build as a static/serverless SPA on Vercel, decoupled from the API build step.
- Production deployment, verification, and rollback: see `12_RELEASE_RUNBOOK.md`.
  Configuration reference: repo-root `.env.example`.
