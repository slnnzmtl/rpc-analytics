"""Reporting auth, aggregate shape, and backup/restore (DDD-133)."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rpc_analytics.config import get_settings
from rpc_analytics.contract import valid_example_payload
from rpc_analytics.main import app
from rpc_analytics.store import AggregateStore


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db = tmp_path / "analytics.db"
    monkeypatch.setenv("SQLITE_PATH", str(db))
    monkeypatch.setenv("REPORT_TOKEN", "test-report-token")
    monkeypatch.setenv("PROJECT_ID", "rekordbox-playlist-converter")
    monkeypatch.setenv("PROJECT_NAME", "Rekordbox Playlist Converter")
    monkeypatch.setenv("RATE_LIMIT_CAPACITY", "100")
    monkeypatch.setenv("RATE_LIMIT_REFILL_PER_SECOND", "10")
    monkeypatch.setenv("RATE_LIMIT_SALT_SEED", "test-salt")
    get_settings.cache_clear()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_report_unauthorized(client: TestClient) -> None:
    assert client.get("/v1/report").status_code == 401


def test_report_forbidden(client: TestClient) -> None:
    response = client.get("/v1/report", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 403


def test_report_authorized_shape(client: TestClient) -> None:
    assert client.post("/v1/events", json=valid_example_payload()).status_code == 202
    today = datetime.now(timezone.utc).date().isoformat()
    response = client.get(
        f"/v1/report?from={today}&to={today}",
        headers={"Authorization": "Bearer test-report-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["reporting_schema_version"] == 1
    assert body["project_id"] == "rekordbox-playlist-converter"
    assert body["project_name"] == "Rekordbox Playlist Converter"
    assert body["from"] == today
    assert len(body["rows"]) == 1
    assert body["rows"][0]["converted"] == 12
    assert body["rows"][0]["event_count"] == 1


def test_report_filter_surface(client: TestClient) -> None:
    payload = valid_example_payload()
    assert client.post("/v1/events", json=payload).status_code == 202
    payload["surface"] = "cli"
    payload["outcomes"]["converted"] = 2
    assert client.post("/v1/events", json=payload).status_code == 202
    today = datetime.now(timezone.utc).date().isoformat()
    response = client.get(
        f"/v1/report?from={today}&to={today}&surface=cli",
        headers={"Authorization": "Bearer test-report-token"},
    )
    assert response.status_code == 200
    rows = response.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["surface"] == "cli"
    assert rows[0]["converted"] == 2


def test_backup_restore_sqlite(tmp_path: Path) -> None:
    src = tmp_path / "src.db"
    backup = tmp_path / "backup.db"
    restored = tmp_path / "restored.db"
    store = AggregateStore(src)
    from rpc_analytics.contract import ConversionCompletedEvent

    store.upsert_event(ConversionCompletedEvent.model_validate(valid_example_payload()))
    with sqlite3.connect(src) as conn:
        conn.backup(sqlite3.connect(backup))
    shutil.copy(backup, restored)
    restored_store = AggregateStore(restored)
    today = datetime.now(timezone.utc).date().isoformat()
    rows = restored_store.query(today, today)
    assert len(rows) == 1
    assert rows[0]["appended"] == 15
