# rpc-analytics

Privacy-preserving, single-project usage analytics for Rekordbox Playlist Converter.

Public clients send anonymous completed-conversion aggregates to `POST /v1/events`.
Operators read aggregates via private `GET /v1/report` (Bearer token). Project
identity is fixed by server configuration and is never accepted from clients.

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
