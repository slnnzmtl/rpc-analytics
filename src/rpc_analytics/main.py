"""Application entrypoint (routes filled in by later tickets)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from rpc_analytics import __version__
from rpc_analytics.config import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    get_settings()
    yield


app = FastAPI(
    title="rpc-analytics",
    version=__version__,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness placeholder; DDD-132 adds SQLite writable check."""
    return {"status": "ok"}
