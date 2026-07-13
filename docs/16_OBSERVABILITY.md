# Observability

How logs flow, how to query them by `request_id`, and what to alert on
first. Log *format* semantics (what the API emits, problem-details
correlation): `docs/12_RELEASE_RUNBOOK.md` → "Querying the logs".

## Pipeline

```
containers (json-file logs)
   └► vector (docker_logs source, filtered to the atip-prod compose project)
        └► remap: parse the API's JSON lines into structured fields,
                  label events with service + environment
             ├► file archive  /var/log/atip/<UTC day>/<service>.ndjson  (always on)
             └► loki          http://loki:3100                          (optional overlay)
```

- **Why Vector** (not Promtail): Promtail is deprecated upstream (Grafana's
  successor is Alloy); Vector is a single small container with first-class
  `docker_logs` ingestion, real JSON parsing (VRL) instead of regex pipeline
  stages, disk-buffered delivery, and a native Loki sink when we want it —
  the lightest option that keeps logs *structured* end to end.
- The API's fields (`timestamp`, `level`, `logger`, `message`, `request_id`,
  `exc_info`) are merged into each event — never flattened into a text blob.
  Non-JSON lines from redis/qdrant/caddy pass through with the raw line in
  `message` and still carry `service`/`environment`.
- Config: `docker/observability/vector.toml` (+ `vector-loki.toml` via the
  `docker/docker-compose.loki.yml` overlay). Vector reads the docker socket
  read-only — root-equivalent on the host; accepted single-VPS tradeoff
  (the alternative, per-service file tailing, loses crash loops and caddy).
- `request_id` is deliberately a JSON **field**, not a Loki label: label
  values must stay low-cardinality (`service`, `environment`, `level`).

## Where to look

```bash
# Live tail, single service
scripts/ops/compose.sh logs -f api

# Shipped archive (per service, per UTC day) — on the atip_logs volume
scripts/ops/compose.sh exec vector ls /var/log/atip/
scripts/ops/compose.sh exec vector cat /var/log/atip/2026-07-13/api.ndjson | jq -c '…'
# or bind it to the host: docker volume inspect atip-prod_atip_logs
```

Archive retention (the volume is not pruned by Vector). Weekly cron:

```cron
0 4 * * 1 docker run --rm -v atip-prod_atip_logs:/logs alpine find /logs -mindepth 1 -maxdepth 1 -type d -mtime +30 -exec rm -rf {} +
```

## Queries

`jq` against the archive (identical filters work on `compose.sh logs api`):

```bash
# 1. Trace one request end to end (id from the problem body or X-Request-ID header)
jq -c 'select(.request_id == "<id>")' api.ndjson

# 2. Error sweep with tracebacks
jq -c 'select(.level == "ERROR") | {timestamp, request_id, message, exc_info}' api.ndjson

# 3. Access-log view: every 4xx/5xx served
jq -c 'select(.logger == "uvicorn.access" and (.message | test(" [45][0-9][0-9]$")))' api.ndjson

# 4. Readiness failures (the API logs dependency check failures as warnings/errors)
jq -c 'select(.message | test("health|not_ready|degraded"; "i"))' api.ndjson
```

LogQL (Loki overlay enabled; `ATIP_COMPOSE_EXTRA=docker-compose.loki.yml`):

```logql
{service="api"} | json | request_id="<id>"                                  # trace a request
{service="api", level="ERROR"} | json                                       # error sweep
{service="api"} | json | logger="uvicorn.access" |~ " 5[0-9][0-9]$"         # 5xx access lines
sum(rate({service="api"} | json | logger="uvicorn.access" |~ " 5[0-9][0-9]$" [5m]))  # 5xx rate
{service="api"} |= "degraded"                                               # readiness degradation
```

Loki is not published on the host. Query from inside the network:

```bash
scripts/ops/compose.sh run --rm ops-curl -sG http://loki:3100/loki/api/v1/query_range \
  --data-urlencode 'query={service="api"} | json | request_id="<id>"'
```

or SSH-tunnel a temporary Grafana pointed at `http://loki:3100`.

## Alerting: what to watch first (in this order)

| Signal | How to detect (no extra infra) | Threshold |
|---|---|---|
| Container restarts | `docker events --filter event=restart` or `docker ps` RestartCount in node exporter/cron | any restart of api/postgres/caddy |
| Readiness failing | external monitor (Uptime Kuma / healthchecks.io / UptimeRobot) on `https://<domain>/health/ready` | 503 for >2 min |
| Readiness **degraded** | same monitor, keyword match on `"degraded"` in the 200 body | any occurrence (Qdrant/Redis down — serve traffic, fix dependency) |
| DB connectivity | `/health` (strict) returns 503; api log `postgres` errors | immediate |
| Qdrant health | `"degraded"` body naming qdrant; log query #4 | 15 min (search is keyword-only meanwhile) |
| 5xx spike | LogQL 5xx-rate query above, or cron + jq count on the day file | >1% of requests over 5 min |
| Search/chat latency | uvicorn.access durations aren't logged today — watch client-side or add timing middleware later | sustained user-visible slowness |
| Backup failures | cron exit status of `backup_all.sh` (cron MAILTO or a healthchecks.io ping) | any non-zero |
| TLS expiry | Caddy renews automatically; external cert monitor as backstop | <14 days remaining |

Minimal viable setup: one external uptime monitor on `/health/ready` +
cron MAILTO for backups + the restart check. Everything else can wait for
Loki/Grafana.

## Incident debugging runbook snippets

**A user reports a failing action:**
1. Get `request_id` — it's in the error toast payload (problem body) and the
   `X-Request-ID` response header.
2. `jq -c 'select(.request_id == "<id>")'` over that day's `api.ndjson`
   (query #1) — you get the access line plus every app record, including
   `exc_info` if it 500'd.
3. No records at all → the request died at the proxy:
   `scripts/ops/compose.sh logs caddy | grep -i error`.

**Readiness flapping:**
1. `curl -s https://<domain>/health/ready` — the body names the failing check.
2. `not_ready` (503) = Postgres: `compose.sh logs postgres`, disk space, then
   `compose.sh run --rm migrate` if the detail says "not migrated".
3. `degraded` (200) = Qdrant/Redis: restart that dependency only. Do not
   bounce the api; it is serving keyword-only by design.

**Everything is down:**
`docker ps` → which container is missing → `scripts/ops/compose.sh logs --tail 100 <svc>`
→ if the api refused to boot, the last line names the offending variable
(fail-fast config check). Disk full is the classic silent killer: `df -h`.
