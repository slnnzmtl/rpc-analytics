"""Ingest endpoint helpers."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import Request
from pydantic import ValidationError

from rpc_analytics.contract import (
    MAX_BODY_BYTES,
    ConversionCompletedEvent,
    ConversionFailedEvent,
    IngestEvent,
    InstallEvent,
    StatusResponse,
)

EVENT_MODELS: dict[
    str, type[ConversionCompletedEvent] | type[InstallEvent] | type[ConversionFailedEvent]
] = {
    "conversion_completed": ConversionCompletedEvent,
    "install": InstallEvent,
    "conversion_failed": ConversionFailedEvent,
}

logger = logging.getLogger("rpc_analytics")


def client_ip_from_request(request: Request) -> str:
    """Use X-Forwarded-For only when the peer is loopback (Caddy)."""
    peer = request.client.host if request.client else ""
    if peer in {"127.0.0.1", "::1"}:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip() or peer
    return peer or "unknown"


async def read_limited_body(request: Request) -> tuple[bytes | None, StatusResponse | None, int | None]:
    """Return (body, error_response, status_code)."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            return None, StatusResponse(status="oversized"), 413
        chunks.append(chunk)
    return b"".join(chunks), None, None


def parse_event(body: bytes) -> tuple[IngestEvent | None, StatusResponse, int]:
    try:
        data: Any = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, StatusResponse(status="invalid"), 400

    if not isinstance(data, dict):
        return None, StatusResponse(status="invalid"), 400

    schema_version = data.get("schema_version")
    event_name = data.get("event")
    model = EVENT_MODELS.get(event_name) if isinstance(event_name, str) else None
    if schema_version != 1 or model is None:
        return None, StatusResponse(status="unsupported"), 422

    try:
        event = model.model_validate(data)
    except ValidationError:
        return None, StatusResponse(status="invalid"), 400

    logger.info(
        "ingest status=accepted route=/v1/events schema_version=%s event=%s",
        event.schema_version,
        event.event,
    )
    return event, StatusResponse(status="accepted"), 202
