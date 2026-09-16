"""Versioned ingestion and reporting contracts (DDD-131)."""

from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

INGEST_SCHEMA_VERSION = 1
REPORTING_SCHEMA_VERSION = 1
MAX_BODY_BYTES = 4096
OUTCOME_MAX = 10_000

INPUT_FILE_TYPE_KEYS = ("mp3", "wav", "aiff", "flac", "m4a", "alac", "other")

VERSION_RE = re.compile(r"^\d{1,4}(\.\d{1,4}){0,3}$")
INSTALL_ID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class Surface(str, Enum):
    gui = "gui"
    cli = "cli"


class OutputFormat(str, Enum):
    wav = "wav"
    aiff = "aiff"


class BitDepth(str, Enum):
    sixteen = "16"
    twenty_four = "24"


class SampleRate(str, Enum):
    rate_44100 = "44100"
    rate_48000 = "48000"


class Outcomes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    converted: int = Field(ge=0, le=OUTCOME_MAX)
    copied: int = Field(ge=0, le=OUTCOME_MAX)
    skipped: int = Field(ge=0, le=OUTCOME_MAX)
    appended: int = Field(ge=0, le=OUTCOME_MAX)


class InputFileTypes(BaseModel):
    """Per-batch counts of source files by extension bucket (lowercase)."""

    model_config = ConfigDict(extra="forbid")

    mp3: int = Field(ge=0, le=OUTCOME_MAX)
    wav: int = Field(ge=0, le=OUTCOME_MAX)
    aiff: int = Field(ge=0, le=OUTCOME_MAX)
    flac: int = Field(ge=0, le=OUTCOME_MAX)
    m4a: int = Field(ge=0, le=OUTCOME_MAX)
    alac: int = Field(ge=0, le=OUTCOME_MAX)
    other: int = Field(ge=0, le=OUTCOME_MAX)


def _short_dotted_version(value: str) -> str:
    cleaned = value.strip()
    if not VERSION_RE.fullmatch(cleaned):
        raise ValueError("must be a short dotted version string")
    return cleaned


def _uuid_install_id(value: str) -> str:
    cleaned = value.strip()
    if not INSTALL_ID_RE.fullmatch(cleaned):
        raise ValueError("must be a UUID string")
    return cleaned.lower()


class ConversionCompletedEvent(BaseModel):
    """v1 completed-conversion ingest payload. Rejects unknown fields."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    event: Literal["conversion_completed"]
    app_version: str
    rekordbox_version: str
    surface: Surface
    output_format: OutputFormat
    bit_depth: BitDepth
    sample_rate: SampleRate
    outcomes: Outcomes
    input_file_types: InputFileTypes | None = None
    install_id: str | None = None

    @field_validator("app_version", "rekordbox_version")
    @classmethod
    def short_dotted_version(cls, value: str) -> str:
        return _short_dotted_version(value)

    @field_validator("install_id")
    @classmethod
    def uuid_install_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _uuid_install_id(value)


class InstallEvent(BaseModel):
    """v1 one-shot install ingest payload. Rejects unknown fields."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    event: Literal["install"]
    app_version: str
    surface: Surface
    install_id: str

    @field_validator("app_version")
    @classmethod
    def short_dotted_version(cls, value: str) -> str:
        return _short_dotted_version(value)

    @field_validator("install_id")
    @classmethod
    def uuid_install_id(cls, value: str) -> str:
        return _uuid_install_id(value)


IngestEvent = ConversionCompletedEvent | InstallEvent


class StatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


class AggregateRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    app_version: str
    rekordbox_version: str
    surface: str
    output_format: str
    bit_depth: str
    sample_rate: str
    converted: int
    copied: int
    skipped: int
    appended: int
    input_mp3: int = 0
    input_wav: int = 0
    input_aiff: int = 0
    input_flac: int = 0
    input_m4a: int = 0
    input_alac: int = 0
    input_other: int = 0
    event_count: int = Field(
        description="Number of accepted ingest requests that contributed to this row"
    )


class ReportResponse(BaseModel):
    """Machine-readable aggregate report for future federated dashboards."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    reporting_schema_version: Literal[1] = 1
    project_id: str
    project_name: str
    from_date: str = Field(alias="from")
    to_date: str = Field(alias="to")
    unique_installs: int = Field(
        default=0,
        description="Distinct install_id hashes seen in the from–to UTC range",
    )
    rows: list[AggregateRow]


def valid_example_payload() -> dict:
    return {
        "schema_version": 1,
        "event": "conversion_completed",
        "app_version": "1.2.0",
        "rekordbox_version": "7.0.5",
        "surface": "gui",
        "output_format": "wav",
        "bit_depth": "24",
        "sample_rate": "48000",
        "outcomes": {
            "converted": 12,
            "copied": 3,
            "skipped": 1,
            "appended": 15,
        },
        "input_file_types": {
            "mp3": 4,
            "wav": 2,
            "aiff": 1,
            "flac": 3,
            "m4a": 1,
            "alac": 0,
            "other": 1,
        },
    }


def valid_install_payload() -> dict:
    return {
        "schema_version": 1,
        "event": "install",
        "app_version": "1.2.0",
        "surface": "gui",
        "install_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    }
