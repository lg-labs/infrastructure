"""Networks router (Phase B read-only + Phase F DELETE)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response

from ..deps import require_admin, require_reader
from ..models.domain import NetworksPage
from ..repos.docker_repo import get_docker_repo
from ..safety.confirm import assert_confirm_resource

router = APIRouter(prefix="/networks", tags=["networks"])


@router.get("", response_model=NetworksPage, dependencies=[Depends(require_reader)])
def list_networks(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> NetworksPage:
    items = get_docker_repo().list_networks()
    total = len(items)
    start = (page - 1) * page_size
    return NetworksPage(items=items[start:start + page_size], total=total, page=page, page_size=page_size)


# ---------- DELETE (Phase F) — admin only ----------
#
# Builtin networks (bridge/host/none) -> 403 builtin_network_protected (in repo).
# Networks with attached containers -> 409 network_in_use (in repo).


@router.delete("/{ref}", status_code=204, dependencies=[Depends(require_admin)])
def delete_network(ref: str, request: Request) -> Response:
    assert_confirm_resource(request, ref)
    get_docker_repo().delete_network(ref)
    return Response(status_code=204)
