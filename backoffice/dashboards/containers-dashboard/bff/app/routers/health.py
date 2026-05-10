"""GET /api/health — public, no auth (overridden in nginx)."""
from __future__ import annotations

from fastapi import APIRouter

from ..models.domain import HealthResponse
from ..repos.db import get_conn
from ..repos.docker_repo import get_docker_repo

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    docker_ok = get_docker_repo().ping()

    sqlite_ok = True
    try:
        get_conn().execute("SELECT 1").fetchone()
    except Exception:
        sqlite_ok = False

    overall: str = "ok" if (docker_ok and sqlite_ok) else "degraded"
    return HealthResponse(
        status=overall,                                       # type: ignore[arg-type]
        docker="ok" if docker_ok else "unavailable",          # type: ignore[arg-type]
        sqlite="ok" if sqlite_ok else "unavailable",          # type: ignore[arg-type]
    )
