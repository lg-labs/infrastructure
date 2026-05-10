"""Projects router (Phase I) — read-only.

GET /projects                  → list all compose-projects (cards)
GET /projects/{name}           → detail with topology graph

Mutations (start/stop/restart/remove) are NOT here; the FE reuses
the existing /containers/* routers, so RBAC + denylist + audit are
already enforced upstream.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from ..deps import require_reader
from ..models.projects import ProjectDetail, ProjectListItem
from ..repos.projects_repo import ProjectsRepo, get_projects_repo

log = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


def _repo_dep() -> ProjectsRepo:
    return get_projects_repo()


@router.get(
    "",
    response_model=list[ProjectListItem],
    dependencies=[Depends(require_reader)],
)
def list_projects(
    include_unmanaged: bool = Query(False, description="Include the '(unmanaged)' pseudo-project"),
    repo: ProjectsRepo = Depends(_repo_dep),
) -> list[ProjectListItem]:
    return repo.list_projects(include_unmanaged=include_unmanaged)


@router.get(
    "/{name}",
    response_model=ProjectDetail,
    dependencies=[Depends(require_reader)],
)
def get_project(
    name: str,
    repo: ProjectsRepo = Depends(_repo_dep),
) -> ProjectDetail:
    return repo.get_project(name)
