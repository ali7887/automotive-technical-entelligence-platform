Read CLAUDE.md and docs/02_ROADMAP.md, 03_ARCHITECTURE.md, 11_DEPLOYMENT_DEV.md.

Goal: Phase 1 setup ONLY (no product features except skeleton + health-check).
Tasks:
- create monorepo layout
- docker compose: postgres(+pgvector) + redis + qdrant
- Next.js app scaffold
- FastAPI scaffold (uv)
- simple /health endpoint
- web calls API /health

Before coding:
- propose a short plan with small commits
- wait for approval

After coding:
- list exact commands for local dev
- verify docker, CORS, and env wiring
