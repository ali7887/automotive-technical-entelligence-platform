# Backup & Recovery

What gets backed up, how it's verified, and the exact restore order.
Scripts live in `scripts/ops/`; they all honor `ATIP_BACKUP_DIR`
(default `/var/backups/atip`).

## What must be backed up, and why in this order

| Priority | Store | Contents | Backup mechanism |
|---|---|---|---|
| 1 | PostgreSQL | **System of record**: workspaces, documents, chunks + provenance, evidence, jobs | `pg_dump -Fc` (compressed, transaction-consistent) |
| 2 | `uploads_data` volume | The uploaded PDFs themselves — rows reference these paths; this is the only copy | `tar.gz` of `STORAGE_DIR` |
| 3 | Qdrant | Vectors — **derivable** from Postgres chunks (deterministic UUIDv5 chunk IDs; reprocessing re-embeds) | collection snapshot API |
| — | Redis | Nothing durable (health check only). **Deliberately not backed up**; persistence is disabled in the compose file. Revisit if Redis ever backs rate limiting or caching. | none |

### "Application-consistent enough", defined

The three artifacts are taken at slightly different instants, not in one
atomic cut. That is acceptable for this stack because Postgres is the single
source of truth and the other two stores reconcile against it:

- **Postgres dump** is internally transaction-consistent (single snapshot).
- **Uploads** newer than the dump are orphan files (harmless, invisible);
  uploads *missing* relative to the dump surface as documents whose file is
  gone — re-upload is the recovery, same as the volume-loss case in
  `docs/12_RELEASE_RUNBOOK.md`.
- **Qdrant** drift in either direction is self-healing: chunk IDs are
  deterministic, so reprocessing a document overwrites its vectors in place;
  stale vectors for deleted chunks can't be cited (citations resolve against
  Postgres chunks — provenance never depends on Qdrant alone).

Practical rule: run the three backups back-to-back (`backup_all.sh` does)
during a quiet window; minutes of skew between them is fine.

## Directory structure

```
/var/backups/atip/
  postgres/ atip_20260713_031500Z.dump        # last 7 (daily)
            weekly/atip_20260712_031500Z.dump # last 4 (Sundays)
  uploads/  uploads_20260713_031502Z.tar.gz   # same retention pattern
            weekly/…
  qdrant/   atip_chunks-….snapshot            # same retention pattern
            weekly/…
```

Naming: UTC timestamps `YYYYMMDD_HHMMSSZ` (Qdrant snapshots keep the
server-generated name, which also embeds collection + timestamp).

## Running backups

```bash
scripts/ops/backup_all.sh          # all three + retention pruning
scripts/ops/backup_postgres.sh     # individually
scripts/ops/backup_uploads.sh
scripts/ops/backup_qdrant.sh
```

Cron (nightly 03:15 UTC, as the deploy user):

```cron
15 3 * * * cd /opt/atip && ./scripts/ops/backup_all.sh >> /var/log/atip-backup.log 2>&1
```

`backup_all.sh` exits non-zero if **any** store fails (cron mail / your
alerting fires) but still attempts the others. Retention: last 7 per store;
Sundays the newest artifact is copied to `weekly/`, last 4 kept.

**Off-host copies are your job**: sync `/var/backups/atip` to object storage
(e.g. `rclone sync /var/backups/atip remote:atip-backups` after the cron
line). A backup on the same disk as the database survives bugs, not disks.

## Integrity: how "silently empty" is prevented

- **Postgres**: the dump is verified with `pg_restore --list` *inside the
  container* before it is streamed out; the host copy must have the `PGDMP`
  magic bytes and ≥4 KB. Failures delete the artifact and exit non-zero.
- **Uploads**: `tar -tzf` must read the archive end-to-end on the host
  (entry count printed).
- **Qdrant**: snapshot is created with `wait=true`, and the copied file's
  size must equal the size the snapshot API reported.
- Quarterly (or before any risky migration): do a **real restore rehearsal**
  of the newest dump into a scratch database:

```bash
# pg_restore reads the dump from stdin directly — do NOT pass /dev/stdin as a
# filename (custom-format restore misreads it as a seekable file and fails)
scripts/ops/compose.sh exec -T postgres sh -c \
  'createdb -U "$POSTGRES_USER" atip_restore_test &&
   pg_restore -U "$POSTGRES_USER" -d atip_restore_test --no-owner &&
   psql -U "$POSTGRES_USER" -d atip_restore_test -tAc "select count(*) from documents" &&
   dropdb -U "$POSTGRES_USER" atip_restore_test' \
  < /var/backups/atip/postgres/<newest>.dump
```

## Disaster recovery (full restore)

Order matters: **Postgres → uploads → Qdrant → validate**.

```bash
# 0. Stack up, app stopped (restore_postgres.sh stops api itself)
scripts/ops/compose.sh up -d postgres qdrant redis

# 1. Postgres — the system of record
scripts/ops/restore_postgres.sh /var/backups/atip/postgres/<file>.dump --yes
#    (also re-runs `migrate`: brings an older dump up to the running
#     release's schema head — this is the version-compatibility step)

# 2. Uploads — the files the restored rows point at
scripts/ops/compose.sh stop api
scripts/ops/compose.sh run --rm --no-deps -v /var/backups/atip/uploads/<file>.tar.gz:/restore.tar.gz:ro \
  --entrypoint sh api -c 'rm -rf /data/uploads/* && tar -xzf /restore.tar.gz -C /data'
scripts/ops/compose.sh start api

# 3. Qdrant — vectors (optional but avoids a full re-embed)
scripts/ops/restore_qdrant.sh /var/backups/atip/qdrant/<file>.snapshot --yes

# 4. Validate: schema at head + build identity + readiness
scripts/prod_smoke_test.sh https://<domain> "$(git rev-parse HEAD)"
curl -s https://<domain>/health | grep -o '"detail":"migrated[^"]*"'

# 5. Spot-check the app: open a workspace, run a search, open a citation.
```

Version compatibility: never restore a dump from a *newer* release into an
older codebase. Older dump → current code is the supported direction
(step 1 migrates it forward). If Qdrant vectors lag the restored rows,
documents affected can be reprocessed — retrieval degrades to
keyword-only for them in the meantime, it does not fail.

## Losing one store only

- **Qdrant volume lost, no snapshot**: recreate nothing manually — reprocess
  documents (re-embeds into a fresh collection). Keyword search keeps
  working the whole time.
- **Uploads volume lost**: rows survive; affected documents need re-upload
  (accepted limitation, `docs/12_RELEASE_RUNBOOK.md`).
- **Postgres lost**: restore dump (steps 1, 4, 5). Uploads/Qdrant need no
  touch if their volumes are intact.
