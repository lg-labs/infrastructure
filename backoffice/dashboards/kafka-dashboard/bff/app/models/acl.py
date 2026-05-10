"""Pydantic models for ACL-metadata (design.md §3.5).

The cluster Kafka **does not** apply these. The UI must surface a permanent
banner. See `app/repos/acl_metadata_repo.py` for whitelist constants.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..repos.acl_metadata_repo import (
    OPERATIONS,
    PATTERN_TYPES,
    PERMISSION_TYPES,
    RESOURCE_TYPES,
)

# Re-exported as Literal types so FastAPI/OpenAPI documents the choices
Operation = Literal["READ", "WRITE", "CREATE", "DELETE", "ALTER", "DESCRIBE", "ALL"]
ResourceType = Literal["TOPIC", "GROUP", "CLUSTER"]
PatternType = Literal["LITERAL", "PREFIXED"]
PermissionType = Literal["ALLOW", "DENY"]


def _validate_principal(v: str) -> str:
    v = v.strip()
    if not v.startswith(("User:", "Group:")):
        raise ValueError("principal must start with 'User:' or 'Group:'")
    if len(v) <= len("User:"):
        raise ValueError("principal must have a non-empty name part")
    return v


def _validate_resource_name(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("resource_name must be non-empty")
    return v


class AclMetadata(BaseModel):
    """Read DTO matching design §3.5 example."""

    id: str
    principal: str
    host: str = "*"
    operation: Operation
    resource_type: ResourceType
    resource_name: str
    pattern_type: PatternType
    permission_type: PermissionType
    note: str | None = None
    created_at: str
    created_by: str


class AclMetadataListResp(BaseModel):
    items: list[AclMetadata]
    total: int
    page: int
    page_size: int


class AclMetadataCreateReq(BaseModel):
    principal: str = Field(..., examples=["User:team-payments", "Group:operators"])
    host: str = Field(default="*", min_length=1, max_length=255)
    operation: Operation
    resource_type: ResourceType
    resource_name: str
    pattern_type: PatternType
    permission_type: PermissionType
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("principal")
    @classmethod
    def _v_principal(cls, v: str) -> str:
        return _validate_principal(v)

    @field_validator("resource_name")
    @classmethod
    def _v_resource(cls, v: str) -> str:
        return _validate_resource_name(v)


class AclMetadataUpdateReq(AclMetadataCreateReq):
    """Same shape as create. PUT replaces all fields except id/created_*."""
