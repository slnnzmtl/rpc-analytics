"""Authorized aggregate reporting."""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from rpc_analytics.contract import AggregateRow, ReportResponse

ALLOWED_FILTERS = (
    "app_version",
    "rekordbox_version",
    "surface",
    "output_format",
    "bit_depth",
    "sample_rate",
)
ALLOWED_GROUP_BY = ("date",) + ALLOWED_FILTERS


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def build_report(
    request: Request,
    *,
    from_date: str | None,
    to_date: str | None,
    group_by: str | None,
    filters: dict[str, str],
) -> JSONResponse:
    state = request.app.state.rpc
    today = _utc_today().isoformat()
    start = from_date or today
    end = to_date or today
    try:
        date.fromisoformat(start)
        date.fromisoformat(end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid date") from exc
    if start > end:
        raise HTTPException(status_code=400, detail="invalid date range")

    group_fields: list[str] | None = None
    if group_by:
        group_fields = [part.strip() for part in group_by.split(",") if part.strip()]
        for field in group_fields:
            if field not in ALLOWED_GROUP_BY:
                raise HTTPException(status_code=400, detail="invalid group_by")

    try:
        rows = state.store.query(start, end, filters=filters, group_by=group_fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    report = ReportResponse(
        reporting_schema_version=1,
        project_id=state.settings.project_id,
        project_name=state.settings.project_name,
        from_date=start,
        to_date=end,
        unique_installs=state.store.count_unique_installs(start, end),
        rows=[AggregateRow.model_validate(row) for row in rows],
    )
    return JSONResponse(report.model_dump(by_alias=True))


async def report_endpoint(
    request: Request,
    authorization: str | None = Header(default=None),
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
    group_by: str | None = Query(default=None),
    app_version: str | None = None,
    rekordbox_version: str | None = None,
    surface: str | None = None,
    output_format: str | None = None,
    bit_depth: str | None = None,
    sample_rate: str | None = None,
) -> JSONResponse:
    await request.app.state.rpc.auth.verify_authorization(authorization)
    filters = {
        key: value
        for key, value in {
            "app_version": app_version,
            "rekordbox_version": rekordbox_version,
            "surface": surface,
            "output_format": output_format,
            "bit_depth": bit_depth,
            "sample_rate": sample_rate,
        }.items()
        if value is not None
    }
    return build_report(
        request,
        from_date=from_date,
        to_date=to_date,
        group_by=group_by,
        filters=filters,
    )
