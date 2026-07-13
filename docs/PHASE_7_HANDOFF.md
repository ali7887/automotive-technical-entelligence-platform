# Phase 7 Handoff — Release Readiness & Go-Live Preparation

> Status: **DONE** (2026-07-13). Context-preservation document for Phase 7:
> production configuration, probes, CI, container image, E2E smoke, and the
> release runbook on top of the hardened Phase 6 codebase.

## What Phase 7 added (by workstream)

### A. Production configuration (`config.py`)
- `ENVIRONMENT` (development|test|production). `validate_for_release()` runs
  in `create_app()` and, in production only, refuses to boot on dev-default
  DB credentials or a relative `STORAGE_DIR`. Only zero-false-positive checks
  fail the boot; softer signals (loopback CORS in production) log a warning.
- `OPENAI_API_KEY` is a `SecretStr` — `repr(settings)` can no longer leak it.
  Use `settings.openai_api_key_value` (plain `str | None`, blank → None);
  the env contract is unchanged.
- Numeric limits/timeouts carry `Field(ge/gt)` constraints → invalid config
  fails at startup, not at request time.
- `BUILD_SHA` (optional) + `get_app_version()` (package metadata) identify
  the running release via `/health/live`.
- `.env.example` is the complete, commented config reference (was missing
  every Phase 6 variable).

### B. CI (`.github/workflows/ci.yml`)
- api job: `uv sync --frozen`, ruff, pyright, migration round-trip
  (`upgrade head → downgrade base → upgrade head`), pytest, then an E2E
  smoke step against a background uvicorn. Service containers use the same
  images/host-ports as docker-compose, so test defaults need no CI env.
- web job: `pnpm install --frozen-lockfile`, eslint, tsc, `next build`.
- Verified before commit: YAML parses, both frozen installs succeed, and the
  full migration round-trip passes on a throwaway DB from empty.

### C. Operability (health probes)
- `/health/live`: process-only; never touches dependencies (tested via a
  stub that fails the test if any check is called). Reports version,
  environment, build_sha — response keys are asserted closed, nothing else
  can leak.
- `/health/ready`: Postgres (reachable + migrated) required → 503
  `not_ready`; Redis/Qdrant errors → 200 `degraded` because search degrades
  to keyword-only by design (Phase 6) — evicting the pod would lose capacity
  for no gain.
- `/health` unchanged in strictness (all ok or 503) + now carries `version`.
- `_alembic_head()` falls back to the working directory so the
  migrations-out-of-date check works inside the container image too
  (it silently returned None there before).

### D. E2E release smoke (`apps/api/tests_e2e/`)
- 7 deterministic, LLM-free tests over real HTTP against a live server
  (excluded from default pytest; `ATIP_E2E_BASE_URL` targets any deploy):
  health trio, problem shape + request-id propagation, sanitized validation
  errors, upload→READY→keyword-search-with-provenance, corrupt + encrypted
  PDF rejection, and the /ask contract (answer or 503 `generation_disabled`).
- Self-cleaning (workspace deleted in fixture teardown) — safe to run
  repeatedly against production.
- **Deferred: browser Playwright E2E.** The web app has no test infra; the
  release-critical paths are API flows, and `next build` + eslint + tsc +
  the generated typed client (`schema.d.ts` regenerated this phase) cover
  the frontend contract at far lower flake risk. Revisit if the UI gains
  logic-heavy flows that the typed client can't guarantee.

### E. Deployment artifacts & docs
- `apps/api/Dockerfile`: multi-stage uv build (frozen, no dev deps,
  bytecode-compiled, non-editable), slim runtime, non-root user, ships
  `alembic/` so the same image runs migrations, `HEALTHCHECK` on
  `/health/live` only. `ENVIRONMENT=production` is baked in — verified that
  a bare `docker run` refuses to boot (M1 fail-fast) and that a configured
  run serves ready/live/health correctly against host services.
- `docs/12_RELEASE_RUNBOOK.md`: topology assumptions, deploy order
  (backup → migrate-once → roll API → web), rolling-release compatibility,
  post-deploy checklist (the smoke suite), probe semantics incl.
  healthy-but-degraded, rollback notes (app/schema/env/in-flight work),
  known limitations.

### F. Security & hygiene findings
- Checked: no debug bypasses; CORS origins explicit; validation errors and
  500s stay sanitized (Phase 6); secrets not loggable (SecretStr + JSON
  formatter only serializes the log message); no TODO/FIXME markers exist
  anywhere in apps/. Uploads already stream with a size cap and unlink on
  failure.
- Accepted & documented (runbook): `/docs` + `/openapi.json` public
  (fine behind access control), no auth/RBAC (explicit non-goal),
  per-process rate limiting, in-process background tasks.

## Invariants confirmed intact
UUIDv5 chunk ids, citation provenance (E2E asserts `page_start` survives the
pipeline), verification strictness, append-only review events, RFC 7807
shapes (E2E asserts them over real HTTP). No API contract changed —
additions only (`/health/live`, `/health/ready`, `version` in `/health`).

## Gotchas for the next phase
- `tests_e2e/` needs a live server; the conftest fails fast with
  instructions if none is up. It imports `tests.pdf_utils` (works because
  both are packages under `apps/api`).
- The container's `ENVIRONMENT=production` means local `docker run` needs
  `-e ENVIRONMENT=development` (or real creds) to boot — intentional.
- `NEXT_PUBLIC_API_URL` is build-time for the web bundle; changing it is a
  rebuild, not a config flip.
- PowerShell 5.1 mangles double quotes inside `git commit -m` here-strings —
  avoid embedded `"` in commit messages.
- Alembic downgrades are destructive; the runbook's rollback section
  prefers app-only rollback.

## Progress
- 2026-07-13: `a68bb46` environment-aware config validation + SecretStr +
  complete .env.example (16 new tests).
- 2026-07-13: `3d82f8b` /health/live + /health/ready + version metadata
  (5 probe tests, deterministic via stubbed checks).
- 2026-07-13: `6f4ea74` GitHub Actions CI (api + web).
- 2026-07-13: `d00f5c7` production Dockerfile + in-container alembic-head
  fix (verified live in-container).
- 2026-07-13: `e872c25` E2E release smoke suite + CI wiring (7 tests).
- 2026-07-13: release runbook + docs + regenerated schema.d.ts (this
  commit). Phase 7 **DONE**.
