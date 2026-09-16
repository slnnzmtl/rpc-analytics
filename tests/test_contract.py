"""Contract validation and schema-version tests (DDD-131)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from rpc_analytics.contract import (
    INGEST_SCHEMA_VERSION,
    MAX_BODY_BYTES,
    REPORTING_SCHEMA_VERSION,
    ConversionCompletedEvent,
    InstallEvent,
    ReportResponse,
    valid_example_payload,
    valid_install_payload,
)


def test_valid_example_parses() -> None:
    event = ConversionCompletedEvent.model_validate(valid_example_payload())
    assert event.schema_version == INGEST_SCHEMA_VERSION
    assert event.event == "conversion_completed"
    assert event.outcomes.converted == 12


def test_reject_unknown_field_project_id() -> None:
    payload = valid_example_payload()
    payload["project_id"] = "should-not-be-accepted"
    with pytest.raises(ValidationError):
        ConversionCompletedEvent.model_validate(payload)


def test_reject_unknown_nested_outcome_field() -> None:
    payload = valid_example_payload()
    payload["outcomes"]["tracks"] = 9
    with pytest.raises(ValidationError):
        ConversionCompletedEvent.model_validate(payload)


def test_reject_unknown_input_file_type_field() -> None:
    payload = valid_example_payload()
    payload["input_file_types"]["wma"] = 1
    with pytest.raises(ValidationError):
        ConversionCompletedEvent.model_validate(payload)


def test_input_file_types_optional_for_legacy_clients() -> None:
    payload = valid_example_payload()
    del payload["input_file_types"]
    event = ConversionCompletedEvent.model_validate(payload)
    assert event.input_file_types is None


def test_unsupported_schema_version() -> None:
    payload = valid_example_payload()
    payload["schema_version"] = 2
    with pytest.raises(ValidationError):
        ConversionCompletedEvent.model_validate(payload)


def test_unsupported_event_name() -> None:
    payload = valid_example_payload()
    payload["event"] = "conversion_failed"
    with pytest.raises(ValidationError):
        ConversionCompletedEvent.model_validate(payload)


def test_outcome_cap() -> None:
    payload = valid_example_payload()
    payload["outcomes"]["converted"] = 10001
    with pytest.raises(ValidationError):
        ConversionCompletedEvent.model_validate(payload)


def test_version_shape() -> None:
    payload = valid_example_payload()
    payload["app_version"] = "not a version"
    with pytest.raises(ValidationError):
        ConversionCompletedEvent.model_validate(payload)


def test_max_body_constant() -> None:
    assert MAX_BODY_BYTES == 4096
    assert len(json.dumps(valid_example_payload()).encode()) < MAX_BODY_BYTES


def test_report_response_shape() -> None:
    report = ReportResponse.model_validate(
        {
            "reporting_schema_version": REPORTING_SCHEMA_VERSION,
            "project_id": "rekordbox-playlist-converter",
            "project_name": "Rekordbox Playlist Converter",
            "from": "2026-09-01",
            "to": "2026-09-14",
            "rows": [
                {
                    "date": "2026-09-14",
                    "app_version": "1.2.0",
                    "rekordbox_version": "7.0.5",
                    "surface": "gui",
                    "output_format": "wav",
                    "bit_depth": "24",
                    "sample_rate": "48000",
                    "converted": 12,
                    "copied": 3,
                    "skipped": 1,
                    "appended": 15,
                    "event_count": 1,
                }
            ],
        }
    )
    dumped = report.model_dump(by_alias=True)
    assert dumped["from"] == "2026-09-01"
    assert dumped["reporting_schema_version"] == 1
    assert dumped["project_id"] == "rekordbox-playlist-converter"
    assert dumped["unique_installs"] == 0


def test_reject_bad_install_id() -> None:
    payload = valid_example_payload()
    payload["install_id"] = "not-a-uuid"
    with pytest.raises(ValidationError):
        ConversionCompletedEvent.model_validate(payload)


def test_optional_install_id_accepted() -> None:
    payload = valid_example_payload()
    payload["install_id"] = "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE"
    event = ConversionCompletedEvent.model_validate(payload)
    assert event.install_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_valid_install_parses() -> None:
    event = InstallEvent.model_validate(valid_install_payload())
    assert event.schema_version == INGEST_SCHEMA_VERSION
    assert event.event == "install"
    assert event.install_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_install_rejects_conversion_fields() -> None:
    payload = valid_install_payload()
    payload["outcomes"] = {"converted": 1, "copied": 0, "skipped": 0, "appended": 1}
    with pytest.raises(ValidationError):
        InstallEvent.model_validate(payload)


def test_install_rejects_project_id() -> None:
    payload = valid_install_payload()
    payload["project_id"] = "should-not-be-accepted"
    with pytest.raises(ValidationError):
        InstallEvent.model_validate(payload)


def test_install_requires_install_id() -> None:
    payload = valid_install_payload()
    del payload["install_id"]
    with pytest.raises(ValidationError):
        InstallEvent.model_validate(payload)


def test_install_rejects_bad_install_id() -> None:
    payload = valid_install_payload()
    payload["install_id"] = "not-a-uuid"
    with pytest.raises(ValidationError):
        InstallEvent.model_validate(payload)


def test_install_normalizes_install_id() -> None:
    payload = valid_install_payload()
    payload["install_id"] = "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE"
    event = InstallEvent.model_validate(payload)
    assert event.install_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_contract_doc_exists() -> None:
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs" / "contract.md").read_text(encoding="utf-8")
    assert "conversion_completed" in text
    assert '"event": "install"' in text
    assert "reporting_schema_version" in text
    assert "project_id" in text
    assert "install_id" in text
    assert "unique_installs" in text
