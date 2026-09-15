"""Application entrypoint."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from rpc_analytics import __version__
from rpc_analytics.auth import AuthVerifier
from rpc_analytics.config import Settings, get_settings
from rpc_analytics.ingest import client_ip_from_request, parse_event, read_limited_body
from rpc_analytics.ratelimit import RateLimiter
from rpc_analytics.report import report_endpoint
from rpc_analytics.store import AggregateStore

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("rpc_analytics")

DASHBOARD_HTML = Path(__file__).resolve().parent / "static" / "dashboard.html"
FAVICON_SVG = Path(__file__).resolve().parent / "static" / "favicon.svg"
DASHBOARD_CONFIG_PLACEHOLDER = "__RPC_ANALYTICS_DASHBOARD_CONFIG__"


class AppState:
    settings: Settings
    store: AggregateStore
    limiter: RateLimiter
    auth: AuthVerifier


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    state = AppState()
    state.settings = settings
    state.store = AggregateStore(settings.sqlite_path)
    state.limiter = RateLimiter(
        capacity=settings.rate_limit_capacity,
        refill_per_second=settings.rate_limit_refill_per_second,
        salt_seed=settings.rate_limit_salt_seed,
    )
    state.auth = AuthVerifier(settings)
    app.state.rpc = state
    yield


app = FastAPI(
    title="rpc-analytics",
    version=__version__,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


def _state(request: Request) -> AppState:
    return request.app.state.rpc


@app.get("/health")
def health(request: Request) -> Response:
    store = _state(request).store
    if not store.check_writable():
        return JSONResponse({"status": "degraded"}, status_code=503)
    return JSONResponse({"status": "ok"})


@app.get("/dashboard")
def dashboard(request: Request) -> HTMLResponse:
    if not DASHBOARD_HTML.is_file():
        raise HTTPException(status_code=404, detail="dashboard unavailable")
    settings = _state(request).settings
    template = DASHBOARD_HTML.read_text(encoding="utf-8")
    config = {
        "supabaseUrl": settings.supabase_url,
        "supabaseAnonKey": settings.supabase_anon_key,
    }
    # JSON in a <script> context: escape </ to avoid breaking out of the tag.
    config_json = json.dumps(config).replace("<", "\\u003c")
    if DASHBOARD_CONFIG_PLACEHOLDER not in template:
        raise HTTPException(status_code=500, detail="dashboard template invalid")
    html = template.replace(DASHBOARD_CONFIG_PLACEHOLDER, config_json)
    return HTMLResponse(html, media_type="text/html; charset=utf-8")


@app.get("/favicon.svg")
@app.get("/favicon.ico")
def favicon() -> FileResponse:
    if not FAVICON_SVG.is_file():
        raise HTTPException(status_code=404, detail="favicon unavailable")
    return FileResponse(FAVICON_SVG, media_type="image/svg+xml")


@app.post("/v1/events")
async def ingest_events(request: Request) -> Response:
    state = _state(request)
    ip = client_ip_from_request(request)
    if not state.limiter.allow(ip):
        logger.info("ingest status=rate_limited route=/v1/events")
        return JSONResponse({"status": "rate_limited"}, status_code=429)

    body, err, code = await read_limited_body(request)
    if err is not None and code is not None:
        logger.info("ingest status=%s route=/v1/events", err.status)
        return JSONResponse(err.model_dump(), status_code=code)

    assert body is not None
    event, status, status_code = parse_event(body)
    if event is None:
        logger.info("ingest status=%s route=/v1/events", status.status)
        return JSONResponse(status.model_dump(), status_code=status_code)

    state.store.upsert_event(event, day=datetime.now(timezone.utc).date())
    return JSONResponse(status.model_dump(), status_code=status_code)


app.add_api_route("/v1/report", report_endpoint, methods=["GET"])
