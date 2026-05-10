"""Volumes router (Phase B: read-only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..deps import require_reader
from ..models.domain import VolumesPage
from ..repos.docker_repo import get_docker_repo

router = APIRouter(prefix="/volumes", tags=["volumes"])


@router.get("", response_model=VolumesPage, dependencies=[Depends(require_reader)])
def list_volumes(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> VolumesPage:
    items = get_docker_repo().list_volumes()
    total = len(items)
    start = (page - 1) * page_size
    return VolumesPage(items=items[start:start + page_size], total=total, page=page, page_size=page_size)
