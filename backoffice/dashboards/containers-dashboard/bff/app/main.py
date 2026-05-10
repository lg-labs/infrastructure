"""Containers Dashboard BFF — Phase A skeleton.

Full implementation arrives in Phase B (read-only) and following.
This file only provides the FastAPI factory and the public health
endpoint so that the gateway + healthchecks work out of the box.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse


logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("containers_dashboard")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("containers-dashboard-bff starting (Phase A skeleton)")
    yield
    log.info("containers-dashboard-bff stopping")


app = FastAPI(
    title="Containers Dashboard BFF",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


@app.get("/api/health")
async def health() -> dict[str, Any]:
    """Public health endpoint — no auth (overridden in nginx).

    Phase A: returns ok if process is alive.
    Phase B will check docker.sock + sqlite.
    """
    docker_ok = _check_docker_socket()
    return {
        "status": "ok" if docker_ok else "degraded",
        "docker": "ok" if docker_ok else "unavailable",
        "sqlite": "ok",  # placeholder until Phase B
        "phase": "A",
    }


def _check_docker_socket() -> bool:
    """Best-effort check that the socket file exists and is reachable."""
    sock = "/var/run/docker.sock"
    try:
        return os.path.exists(sock)
    except OSError:
        return False
