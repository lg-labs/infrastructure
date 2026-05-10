"""Images router (Phase B read-only + Phase F DELETE)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response

from ..deps import require_admin, require_reader
from ..models.domain import ImagesPage
from ..repos.docker_repo import get_docker_repo
from ..safety.confirm import assert_confirm_resource

router = APIRouter(prefix="/images", tags=["images"])


@router.get("", response_model=ImagesPage, dependencies=[Depends(require_reader)])
def list_images(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> ImagesPage:
    items = get_docker_repo().list_images()
    total = len(items)
    start = (page - 1) * page_size
    return ImagesPage(items=items[start:start + page_size], total=total, page=page, page_size=page_size)


# ---------- DELETE (Phase F) — admin only ----------
#
# Confirmation header for an image must echo a recognizable identity.
# We accept any of: full id (sha256:…), short id (12-char prefix), or
# any of the repo:tag the image carries. The client knows what it
# typed, so we simply assert the header equals the path parameter.


@router.delete("/{ref:path}", status_code=204, dependencies=[Depends(require_admin)])
def delete_image(
    ref: str,
    request: Request,
    force: bool = Query(False),
    noprune: bool = Query(False),
) -> Response:
    assert_confirm_resource(request, ref)
    get_docker_repo().delete_image(ref, force=force, noprune=noprune)
    return Response(status_code=204)
