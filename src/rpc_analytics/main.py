"""Application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from rpc_analytics import __version__
from rpc_analytics.config import Settings, get_settings
from rpc_analytics.ingest import client_ip_from_request, parse_event, read_limited_body
from rpc_analytics.ratelimit import RateLimiter
from rpc_analytics.store import AggregateStore

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("rpc_analytics")


class AppState:
    settings: Settings
    store: AggregateStore
    limiter: RateLimiter


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
