# rpc-analytics

Privacy-preserving, single-project usage analytics for Rekordbox Playlist Converter.

Public clients send anonymous usage events to `POST /v1/events`: one-shot
`install`, successful `conversion_completed` aggregates, and failed-job
`conversion_failed` (closed reason only).
Operators read aggregates via `GET /v1/report` (Bearer `REPORT_TOKEN` or an
allowlisted Supabase JWT) or the `GET /dashboard` UI (Supabase email/password).
Project identity is fixed by server configuration and is never accepted from clients.

## Stack

Python 3.12, FastAPI, Pydantic v2, SQLite WAL, uvicorn, pytest. Apache-2.0.

## Quick start (local)

```bash
cp .env.example .env
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
uvicorn rpc_analytics.main:app --host 127.0.0.1 --port 8091
```

## Usage

Day-to-day ingest and reporting: [docs/usage.md](docs/usage.md).

## Deploy

See [docs/architecture.md](docs/architecture.md), [docs/deploy.md](docs/deploy.md),
and [docs/operations.md](docs/operations.md).

## License

Apache License 2.0. See [LICENSE](LICENSE).
