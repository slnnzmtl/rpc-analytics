# Operations

## Backup

Copy the SQLite file while the container is running (WAL mode):

```bash
docker compose exec rpc-analytics \
  python -c "import sqlite3; sqlite3.connect('/data/analytics.db').backup(sqlite3.connect('/tmp/backup.db'))"
docker cp rpc-analytics:/tmp/backup.db ./analytics-$(date -u +%Y%m%d).db
```

Or stop the service and copy the volume file.

## Restore

```bash
docker compose stop rpc-analytics
# replace volume data with the backup file at SQLITE_PATH
docker compose start rpc-analytics
curl -sS http://127.0.0.1:8091/health
```

## Upgrade

```bash
git pull   # or replace tree
docker compose build
docker compose up -d
curl -sS http://127.0.0.1:8091/health
```

Schema is additive aggregates only; no raw-event migrations. `install` and
optional conversion `install_id` add `install_days` (hash only) via
`CREATE TABLE IF NOT EXISTS`. `install` events also UPSERT `install_aggregates`
(day / app_version / surface counts) and do not write conversion aggregates.
`conversion_failed` UPSERTs `failure_aggregates` (day / app_version / surface /
reason) and also hashes `install_id` into `install_days`. New conversion
dimensions (e.g. `input_*` file-type counts) are added with `ALTER TABLE` on
startup when missing.

## Synthetic demo seed

Wipe aggregates and refill 14 UTC days with fake installs (demo volumes only):

```bash
cd /root/containers/02-private/analytic-system
docker exec -i rpc-analytics sh -c 'cat > /tmp/seed_synthetic.py' < scripts/seed_synthetic.py
docker exec -e SQLITE_PATH=/data/analytics.db rpc-analytics \
  python /tmp/seed_synthetic.py --reset --days 14 --users 36 --seed 42
```

Then open `/dashboard` and confirm the Users stat matches `unique_installs`.

## Rollback

```bash
git checkout <previous-commit>
docker compose build
docker compose up -d
```

Restore a SQLite backup if a bad deploy wrote bad aggregates.

## Clone for another project

1. New Compose project directory and volume name
2. New `.env` with unique `PROJECT_ID`, `PROJECT_NAME`, `REPORT_TOKEN`, salts
3. New hostname + Caddy site (ingest + health only)
4. Same image; never share the SQLite volume
