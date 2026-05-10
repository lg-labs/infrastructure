"""GET /api/summary — global Docker host overview (US-9)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import require_reader
from ..models.domain import ComponentsHealth, SummaryResponse
from ..repos.db import get_conn
from ..repos.docker_repo import get_docker_repo

router = APIRouter(tags=["summary"])


@router.get("/summary", response_model=SummaryResponse, dependencies=[Depends(require_reader)])
def summary() -> SummaryResponse:
    repo = get_docker_repo()
    data = repo.get_summary()

    sqlite_ok = True
    try:
        get_conn().execute("SELECT 1").fetchone()
    except Exception:
        sqlite_ok = False

    return SummaryResponse(
        containers=data["containers"],
        images_total=data["images_total"],
        volumes_total=data["volumes_total"],
        networks_total=data["networks_total"],
        daemon_version=data.get("daemon_version"),
        daemon_api_version=data.get("daemon_api_version"),
        images_size_mb=data["images_size_mb"],
        components=ComponentsHealth(
            docker="ok",
            sqlite="ok" if sqlite_ok else "unavailable",   # type: ignore[arg-type]
        ),
    )
