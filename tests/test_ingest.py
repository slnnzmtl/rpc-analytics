"""Ingest, aggregation, and rate-limit tests (DDD-132)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rpc_analytics.config import get_settings
from rpc_analytics.contract import MAX_BODY_BYTES, valid_example_payload
from rpc_analytics.main import app
from rpc_analytics.ratelimit import RateLimiter
from rpc_analytics.store import AggregateStore


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db = tmp_path / "analytics.db"
    monkeypatch.setenv("SQLITE_PATH", str(db))
    monkeypatch.setenv("REPORT_TOKEN", "test-report-token")
    monkeypatch.setenv("RATE_LIMIT_CAPACITY", "5")
    monkeypatch.setenv("RATE_LIMIT_REFILL_PER_SECOND", "0")
    monkeypatch.setenv("RATE_LIMIT_SALT_SEED", "test-salt")
    get_settings.cache_clear()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_health_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ingest_accepted_and_aggregated(client: TestClient, tmp_path: Path) -> None:
    payload = valid_example_payload()
    response = client.post("/v1/events", json=payload)
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}

    response2 = client.post("/v1/events", json=payload)
    assert response2.status_code == 202

    store = AggregateStore(get_settings().sqlite_path)
    today = datetime.now(timezone.utc).date().isoformat()
    rows = store.query(today, today)
    assert len(rows) == 1
    assert rows[0]["converted"] == 24
    assert rows[0]["event_count"] == 2


def test_ingest_rejects_project_id(client: TestClient) -> None:
    payload = valid_example_payload()
    payload["project_id"] = "evil"
    response = client.post("/v1/events", json=payload)
    assert response.status_code == 400
    assert response.json() == {"status": "invalid"}


def test_ingest_unsupported_schema(client: TestClient) -> None:
    payload = valid_example_payload()
    payload["schema_version"] = 99
    response = client.post("/v1/events", json=payload)
    assert response.status_code == 422
    assert response.json() == {"status": "unsupported"}


def test_ingest_oversized(client: TestClient) -> None:
    huge = {"schema_version": 1, "pad": "x" * (MAX_BODY_BYTES + 10)}
    response = client.post(
        "/v1/events",
        content=json.dumps(huge).encode(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json() == {"status": "oversized"}


def test_rate_limit(client: TestClient) -> None:
    payload = valid_example_payload()
    codes = [client.post("/v1/events", json=payload).status_code for _ in range(6)]
    assert 429 in codes
    assert codes.count(202) == 5


def test_rate_limiter_does_not_store_ip() -> None:
    limiter = RateLimiter(capacity=2, refill_per_second=0, salt_seed="s")
    assert limiter.allow("203.0.113.9")
    assert "203.0.113.9" not in limiter._buckets
    assert all(len(k) == 64 for k in limiter._buckets)


def test_store_has_no_raw_events_table(tmp_path: Path) -> None:
    store = AggregateStore(tmp_path / "a.db")
    import sqlite3

    with sqlite3.connect(store.path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert tables == {"aggregates"}
