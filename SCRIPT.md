# SCRIPT — Run ATIP locally (Windows / PowerShell)

Manual launch guide for the full stack: **infra → backend API → frontend**.
Written for this machine (Windows 10, PowerShell, Docker Desktop). Copy‑paste the
blocks in order.

---

## 1. What runs where

| Layer            | Component               | Command home | URL / Port                     |
| ---------------- | ----------------------- | ------------ | ------------------------------ |
| Infra (Docker)   | PostgreSQL (pgvector)   | repo root    | `127.0.0.1:5433`               |
| Infra (Docker)   | Redis                   | repo root    | `127.0.0.1:6380`               |
| Infra (Docker)   | Qdrant                  | repo root    | `127.0.0.1:6335` (gRPC 6336)   |
| **Backend API**  | FastAPI (uvicorn)       | `apps/api`   | http://127.0.0.1:8000          |
| **Frontend**     | Next.js (App Router)    | `apps/web`   | http://localhost:3000          |

The web app talks to the API **same‑origin**: the browser calls `/api/*` and
`/health` on `:3000`, and Next proxies them to `:8000` (see `apps/web/next.config.ts`).
That is why the header chip shows **"API offline"** whenever the backend on
`:8000` isn't running — even though the web server is fine.

> Ports are `5433 / 6380 / 6335`, **not** the defaults `5432 / 6379 / 6333` — native
> services squat on the defaults on this machine. Always use `127.0.0.1`, never
> `localhost`, for the data stores.

---

## 2. Prerequisites (one time, already installed here)

- **Docker Desktop** running
- **uv** (Python) — `uv --version`
- **pnpm** + **Node** — `pnpm --version`

---

## 3. One‑time setup (skip if already done)

Run once per fresh checkout. Safe to re‑run.

```powershell
# from repo root: d:\project\NEW\automotive-technical-entelligence-platform

# Frontend deps
pnpm install

# Backend deps (creates apps/api/.venv)
cd apps\api
uv sync

# Apply DB migrations (Postgres must be up first — see step 4a)
$env:PYTHONUTF8 = '1'
uv run alembic upgrade head
cd ..\..
```

An `apps/api/.env` is **optional** in dev — every setting has a safe default in
code. `apps/web/.env.local` already exists and must keep `NEXT_PUBLIC_API_URL`
**empty** (same‑origin proxy). Do not set it to `http://127.0.0.1:8000`, or the
session cookie stops flowing.

Optional — create a login for yourself:

```powershell
cd apps\api
$env:ATIP_BOOTSTRAP_PASSWORD = 'ChangeMe123!'
uv run python -m atip_api.cli create-user --email you@company.com --org "Your Org" --role org_admin
cd ..\..
```

---

## 4. Launch (3 terminals, in order)

### 4a. Terminal 1 — Infra (Docker)

```powershell
# from repo root
pnpm infra:up
#  ≡ docker compose -f docker/docker-compose.yml up -d --wait
```

Wait for it to report healthy (~30s cold). Verify:

```powershell
docker compose -f docker/docker-compose.yml ps
```

### 4b. Terminal 2 — Backend API (FastAPI on :8000)

```powershell
cd apps\api
$env:PYTHONUTF8 = '1'          # avoids the cp1252 emoji crash on this console
$env:PYTHONIOENCODING = 'utf-8'
uv run uvicorn atip_api.main:app --host 127.0.0.1 --port 8000 --reload
```

> Use `uvicorn` (not `uv run fastapi dev`) — the FastAPI CLI prints a 🚀 banner
> that crashes the cp1252 console unless `PYTHONUTF8=1` is set. The line above
> sets it either way, so both work; `uvicorn` is just quieter.

Leave this running. API docs: http://127.0.0.1:8000/docs

### 4c. Terminal 3 — Frontend (Next.js on :3000)

```powershell
cd apps\web
pnpm dev
```

Open http://localhost:3000 — the header chip should read **Operational** (green).

> Root `pnpm dev` starts the **web app only** (the API is Python, not a pnpm
> workspace). Use the separate backend terminal above for the API.

---

## 5. Verify the whole stack

```powershell
# API direct (should be 200, status: ok, all services ok)
curl.exe -s http://127.0.0.1:8000/health

# Exactly what the browser health chip hits (proxied :3000 -> :8000)
curl.exe -s http://localhost:3000/health
```

A healthy response looks like:

```json
{"status":"ok","services":{"postgres":{"status":"ok"},"redis":{"status":"ok"},"qdrant":{"status":"ok"}},"generation_enabled":false}
```

`generation_enabled` is `false` until you set `OPENAI_API_KEY` — chunking and
keyword search still work; semantic search and answer generation stay disabled.

---

## 6. One‑command launcher (optional)

Paste this at the **repo root** to bring up infra and open the API + web in their
own PowerShell windows:

```powershell
# from repo root
docker compose -f docker/docker-compose.yml up -d --wait

Start-Process powershell -ArgumentList '-NoExit','-Command',
  "Set-Location '$PWD\apps\api'; `$env:PYTHONUTF8='1'; uv run uvicorn atip_api.main:app --host 127.0.0.1 --port 8000 --reload"

Start-Process powershell -ArgumentList '-NoExit','-Command',
  "Set-Location '$PWD\apps\web'; pnpm dev"

Write-Host "API  -> http://127.0.0.1:8000/docs"
Write-Host "Web  -> http://localhost:3000"
```

---

## 7. Stop / teardown

```powershell
# In each app terminal: Ctrl+C

# Stop infra (keeps data volumes)
docker compose -f docker/docker-compose.yml down

# Nuke data too (fresh DB next start — you'll re-run migrations)
docker compose -f docker/docker-compose.yml down -v
```

---

## 8. Troubleshooting

| Symptom in UI / terminal                         | Cause                                   | Fix                                                                 |
| ------------------------------------------------ | --------------------------------------- | ------------------------------------------------------------------ |
| Header chip **"API offline"** (red)              | Backend on `:8000` not running          | Start Terminal 2 (step 4b)                                         |
| Header chip **"Degraded"** (amber)               | API up, a data store is down            | `pnpm infra:up`; check `docker ... ps`                            |
| `UnicodeEncodeError ... '\U0001f680'` on startup | cp1252 console + emoji banner           | `$env:PYTHONUTF8='1'` before running (already in the commands)     |
| Login "Failed to fetch" / cookie not set         | `NEXT_PUBLIC_API_URL` was set in dev    | Empty it in `apps/web/.env.local`, restart `next dev`             |
| `ConnectionRefusedError [WinError 1225]` en masse| Docker Desktop not running              | Launch Docker Desktop, wait for engine, `pnpm infra:up`           |
| Auth failures against Postgres                   | Hitting native `:5432` instead of `:5433` | Confirm URLs use `127.0.0.1:5433` (not `localhost`, not `5432`)  |
| API answers but `generation_enabled:false`       | No `OPENAI_API_KEY`                     | Expected in dev; set the key in `apps/api/.env` to enable AI       |
