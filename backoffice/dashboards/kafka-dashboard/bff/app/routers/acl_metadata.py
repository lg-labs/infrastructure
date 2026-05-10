"""ACL-metadata router (US-7, C-A; design.md §3.5).

These endpoints operate on SQLite **only**. The Kafka cluster does NOT enforce
the ACLs (design §A6). The UI surfaces a permanent banner.

Authz:
    - GET / list   → reader (all roles)
    - POST/PUT/DEL → admin only (gateway also enforces this; BFF redoubles for
      defense-in-depth)
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response

from ..deps import CurrentUser, require_admin, require_reader
from ..errors import (
    AclMetadataDuplicate,
    AclMetadataNotFound,
    ConfirmationRequired,
)
from ..models.acl import (
    AclMetadata,
    AclMetadataCreateReq,
    AclMetadataListResp,
    AclMetadataUpdateReq,
)
from ..repos import acl_metadata_repo

router = APIRouter(prefix="/acl-metadata", tags=["acl-metadata"])
log = logging.getLogger(__name__)


def _is_unique_violation(exc: sqlite3.IntegrityError) -> bool:
    msg = str(exc).lower()
    return "unique" in msg and "acl_metadata" in msg


# ---------- LIST ----------

@router.get("", response_model=AclMetadataListResp,
            dependencies=[Depends(require_reader)])
def list_acl_metadata(
    principal: str = Query(""),
    resource_name: str = Query(""),
    resource_type: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> AclMetadataListResp:
    rows, total = acl_metadata_repo.list_all(
        principal=principal or None,
        resource_name=resource_name or None,
        resource_type=resource_type or None,
        page=page,
        page_size=page_size,
    )
    return AclMetadataListResp(
        items=[AclMetadata(**r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------- GET ----------

@router.get("/{acl_id}", response_model=AclMetadata,
            dependencies=[Depends(require_reader)])
def get_acl_metadata(acl_id: str) -> AclMetadata:
    row = acl_metadata_repo.get(acl_id)
    if row is None:
        raise AclMetadataNotFound(acl_id)
    return AclMetadata(**row)


# ---------- CREATE ----------

@router.post("", response_model=AclMetadata, status_code=201)
def create_acl_metadata(
    req: AclMetadataCreateReq,
    user: Annotated[CurrentUser, Depends(require_admin)],
) -> AclMetadata:
    try:
        row = acl_metadata_repo.insert(
            principal=req.principal,
            host=req.host,
            operation=req.operation,
            resource_type=req.resource_type,
            resource_name=req.resource_name,
            pattern_type=req.pattern_type,
            permission_type=req.permission_type,
            note=req.note,
            user=user.user or "unknown",
        )
    except sqlite3.IntegrityError as e:
        if _is_unique_violation(e):
            raise AclMetadataDuplicate(
                principal=req.principal,
                resource_type=req.resource_type,
                resource_name=req.resource_name,
                operation=req.operation,
                permission_type=req.permission_type,
            )
        raise  # unexpected — surfaces as 500
    log.info("acl_metadata.create id=%s principal=%s op=%s resource=%s",
             row["id"], req.principal, req.operation, req.resource_name)
    return AclMetadata(**row)


# ---------- UPDATE ----------

@router.put("/{acl_id}", response_model=AclMetadata)
def update_acl_metadata(
    acl_id: str,
    req: AclMetadataUpdateReq,
    user: Annotated[CurrentUser, Depends(require_admin)],
) -> AclMetadata:
    try:
        row = acl_metadata_repo.update(
            acl_id,
            principal=req.principal,
            host=req.host,
            operation=req.operation,
            resource_type=req.resource_type,
            resource_name=req.resource_name,
            pattern_type=req.pattern_type,
            permission_type=req.permission_type,
            note=req.note,
        )
    except sqlite3.IntegrityError as e:
        if _is_unique_violation(e):
            raise AclMetadataDuplicate(
                principal=req.principal,
                resource_type=req.resource_type,
                resource_name=req.resource_name,
                operation=req.operation,
                permission_type=req.permission_type,
            )
        raise
    if row is None:
        raise AclMetadataNotFound(acl_id)
    log.info("acl_metadata.update id=%s by=%s", acl_id, user.user or "unknown")
    return AclMetadata(**row)


# ---------- DELETE ----------

@router.delete("/{acl_id}", status_code=204)
def delete_acl_metadata(
    acl_id: str,
    user: Annotated[CurrentUser, Depends(require_admin)],
    x_confirm_resource: Annotated[str | None, Header()] = None,
) -> Response:
    if x_confirm_resource != acl_id:
        raise ConfirmationRequired(acl_id)
    if not acl_metadata_repo.delete(acl_id):
        raise AclMetadataNotFound(acl_id)
    log.info("acl_metadata.delete id=%s by=%s", acl_id, user.user or "unknown")
    return Response(status_code=204)
