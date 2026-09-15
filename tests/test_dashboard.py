"""Operator dashboard shell with Supabase login UI."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rpc_analytics.config import get_settings
from rpc_analytics.contract import valid_example_payload
from rpc_analytics.main import DASHBOARD_HTML, app


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
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-anon-key")
    get_settings.cache_clear()
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_dashboard_html_exists() -> None:
    assert DASHBOARD_HTML.is_file()


def test_dashboard_returns_login_html(client: TestClient) -> None:
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "Usage dashboard" in body
    assert "test-report-token" not in body
    assert "REPORT_TOKEN" not in body
    assert 'id="email"' in body
    assert 'id="password"' in body
    assert "Sign in" in body
    assert "sessionStorage" in body
    assert "https://example.supabase.co" in body
    assert "test-anon-key" in body
    assert "__RPC_ANALYTICS_DASHBOARD_CONFIG__" not in body
    assert "favicon" in body
    assert "60000" in body
    assert "Choose a date range, then Load." not in body
    assert "Sign in to load the last 14 UTC days." in body
    assert "Users" in body


def test_favicon_svg(client: TestClient) -> None:
    response = client.get("/favicon.svg")
    assert response.status_code == 200
    assert "image/svg+xml" in response.headers["content-type"]
    assert b"<svg" in response.content
    assert client.get("/favicon.ico").status_code == 200


def test_dashboard_group_by_date_still_works(client: TestClient) -> None:
    assert client.post("/v1/events", json=valid_example_payload()).status_code == 202
    today = datetime.now(timezone.utc).date().isoformat()
    response = client.get(
        f"/v1/report?from={today}&to={today}&group_by=date",
        headers={"Authorization": "Bearer test-report-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["reporting_schema_version"] == 1
    assert len(body["rows"]) == 1
    assert body["rows"][0]["event_count"] == 1
    assert body["rows"][0]["converted"] == 12
