"""Ingest, aggregation, and rate-limit tests (DDD-132)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rpc_analytics.config import get_settings
from rpc_analytics.contract import (
    MAX_BODY_BYTES,
    valid_example_payload,
    valid_install_payload,
)
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


def test_ingest_aggregates_input_file_types(client: TestClient) -> None:
    payload = valid_example_payload()
    response = client.post("/v1/events", json=payload)
    assert response.status_code == 202

    store = AggregateStore(get_settings().sqlite_path)
    today = datetime.now(timezone.utc).date().isoformat()
    row = store.query(today, today)[0]
    assert row["input_mp3"] == 4
    assert row["input_flac"] == 3
    assert row["input_alac"] == 0

    legacy = valid_example_payload()
    del legacy["input_file_types"]
    assert client.post("/v1/events", json=legacy).status_code == 202
    row2 = store.query(today, today)[0]
    assert row2["input_mp3"] == 4
    assert row2["event_count"] == 2


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
    assert tables == {"aggregates", "install_days"}


def test_ingest_without_install_id_unique_zero(client: TestClient) -> None:
    assert client.post("/v1/events", json=valid_example_payload()).status_code == 202
    today = datetime.now(timezone.utc).date().isoformat()
    response = client.get(
        f"/v1/report?from={today}&to={today}",
        headers={"Authorization": "Bearer test-report-token"},
    )
    assert response.status_code == 200
    assert response.json()["unique_installs"] == 0


def test_ingest_same_install_id_counts_once(client: TestClient) -> None:
    payload = valid_example_payload()
    payload["install_id"] = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert client.post("/v1/events", json=payload).status_code == 202
    assert client.post("/v1/events", json=payload).status_code == 202
    today = datetime.now(timezone.utc).date().isoformat()
    response = client.get(
        f"/v1/report?from={today}&to={today}",
        headers={"Authorization": "Bearer test-report-token"},
    )
    assert response.status_code == 200
    assert response.json()["unique_installs"] == 1


def test_ingest_two_install_ids_count_two(client: TestClient) -> None:
    a = valid_example_payload()
    a["install_id"] = "11111111-1111-1111-1111-111111111111"
    b = valid_example_payload()
    b["install_id"] = "22222222-2222-2222-2222-222222222222"
    assert client.post("/v1/events", json=a).status_code == 202
    assert client.post("/v1/events", json=b).status_code == 202
    today = datetime.now(timezone.utc).date().isoformat()
    response = client.get(
        f"/v1/report?from={today}&to={today}",
        headers={"Authorization": "Bearer test-report-token"},
    )
    assert response.status_code == 200
    assert response.json()["unique_installs"] == 2


def test_ingest_same_install_across_days_counts_once(client: TestClient) -> None:
    from datetime import date, timedelta

    from rpc_analytics.contract import ConversionCompletedEvent
    from rpc_analytics.store import AggregateStore

    store = AggregateStore(get_settings().sqlite_path)
    event = ConversionCompletedEvent.model_validate(
        {**valid_example_payload(), "install_id": "33333333-3333-3333-3333-333333333333"}
    )
    day_a = date(2026, 9, 1)
    day_b = day_a + timedelta(days=1)
    store.upsert_event(event, day=day_a)
    store.upsert_event(event, day=day_b)
    assert store.count_unique_installs(day_a.isoformat(), day_b.isoformat()) == 1


def test_ingest_bad_install_id_rejected(client: TestClient) -> None:
    payload = valid_example_payload()
    payload["install_id"] = "not-a-uuid"
    response = client.post("/v1/events", json=payload)
    assert response.status_code == 400
    assert response.json() == {"status": "invalid"}


def test_ingest_install_accepted_counts_unique(client: TestClient) -> None:
    payload = valid_install_payload()
    response = client.post("/v1/events", json=payload)
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert client.post("/v1/events", json=payload).status_code == 202

    store = AggregateStore(get_settings().sqlite_path)
    today = datetime.now(timezone.utc).date().isoformat()
    assert store.query(today, today) == []

    response = client.get(
        f"/v1/report?from={today}&to={today}",
        headers={"Authorization": "Bearer test-report-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["unique_installs"] == 1
    assert body["rows"] == []


def test_ingest_install_cli_surface(client: TestClient) -> None:
    payload = valid_install_payload()
    payload["surface"] = "cli"
    payload["install_id"] = "44444444-4444-4444-4444-444444444444"
    assert client.post("/v1/events", json=payload).status_code == 202


def test_ingest_install_rejects_project_id(client: TestClient) -> None:
    payload = valid_install_payload()
    payload["project_id"] = "evil"
    response = client.post("/v1/events", json=payload)
    assert response.status_code == 400
    assert response.json() == {"status": "invalid"}


def test_ingest_install_rejects_conversion_fields(client: TestClient) -> None:
    payload = valid_install_payload()
    payload["rekordbox_version"] = "7.0.5"
    response = client.post("/v1/events", json=payload)
    assert response.status_code == 400
    assert response.json() == {"status": "invalid"}


def test_ingest_install_missing_install_id(client: TestClient) -> None:
    payload = valid_install_payload()
    del payload["install_id"]
    response = client.post("/v1/events", json=payload)
    assert response.status_code == 400
    assert response.json() == {"status": "invalid"}


def test_ingest_install_bad_install_id(client: TestClient) -> None:
    payload = valid_install_payload()
    payload["install_id"] = "not-a-uuid"
    response = client.post("/v1/events", json=payload)
    assert response.status_code == 400
    assert response.json() == {"status": "invalid"}


def test_ingest_install_bad_version(client: TestClient) -> None:
    payload = valid_install_payload()
    payload["app_version"] = "not a version"
    response = client.post("/v1/events", json=payload)
    assert response.status_code == 400
    assert response.json() == {"status": "invalid"}


def test_ingest_unknown_event_unsupported(client: TestClient) -> None:
    payload = valid_install_payload()
    payload["event"] = "session_started"
    response = client.post("/v1/events", json=payload)
    assert response.status_code == 422
    assert response.json() == {"status": "unsupported"}


def test_ingest_install_and_conversion_same_id_count_once(client: TestClient) -> None:
    install = valid_install_payload()
    conversion = valid_example_payload()
    conversion["install_id"] = install["install_id"]
    assert client.post("/v1/events", json=install).status_code == 202
    assert client.post("/v1/events", json=conversion).status_code == 202
    today = datetime.now(timezone.utc).date().isoformat()
    response = client.get(
        f"/v1/report?from={today}&to={today}",
        headers={"Authorization": "Bearer test-report-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["unique_installs"] == 1
    assert len(body["rows"]) == 1
    assert body["rows"][0]["event_count"] == 1
