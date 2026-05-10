"""Pydantic domain models for request/response (design.md §3.3)."""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


TOPIC_NAME_RE = re.compile(r"^lglabs\.[a-z0-9]([a-z0-9._-]*[a-z0-9])?$")
MAX_TOPIC_NAME_LEN = 249

CleanupPolicy = Literal["delete", "compact", "compact,delete"]


def validate_topic_name(name: str) -> str:
    if len(name) > MAX_TOPIC_NAME_LEN:
        raise ValueError(f"name too long ({len(name)} > {MAX_TOPIC_NAME_LEN})")
    if not TOPIC_NAME_RE.fullmatch(name):
        raise ValueError(f"name must match {TOPIC_NAME_RE.pattern}")
    return name


class TopicSummary(BaseModel):
    name: str
    partitions: int
    replication_factor: int
    min_insync_replicas: int | None = None
    cleanup_policy: str | None = None
    retention_ms: int | None = None
    is_internal: bool = False
    description: str | None = None
    owner: str | None = None


class PartitionDetail(BaseModel):
    id: int
    leader: int
    replicas: list[int]
    isr: list[int]


class TopicDetail(TopicSummary):
    configs: dict[str, str] = Field(default_factory=dict)
    partitions_detail: list[PartitionDetail] = Field(default_factory=list)
    created_at: str | None = None
    created_by: str | None = None
    updated_at: str | None = None
    updated_by: str | None = None


class CreateTopicReq(BaseModel):
    name: str
    partitions: int = Field(..., ge=1, le=100)
    replication_factor: int = Field(3, ge=1, le=3)
    cleanup_policy: CleanupPolicy = "delete"
    retention_ms: int = Field(604_800_000, ge=60_000, le=31_536_000_000)
    min_insync_replicas: int = Field(2, ge=1, le=3)
    description: str = Field(..., min_length=10)
    owner: str = Field(..., min_length=1)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        return validate_topic_name(v)


class UpdateTopicReq(BaseModel):
    partitions: int | None = Field(None, ge=1, le=100)
    cleanup_policy: CleanupPolicy | None = None
    retention_ms: int | None = Field(None, ge=60_000, le=31_536_000_000)
    min_insync_replicas: int | None = Field(None, ge=1, le=3)
    description: str | None = Field(None, min_length=10)
    owner: str | None = None


class TopicListResp(BaseModel):
    items: list[TopicSummary]
    total: int
    page: int
    page_size: int


class SummaryResp(BaseModel):
    brokers_alive: int
    topics_total: int
    topics_internal_hidden: int
    schemas_total: int
    acl_metadata_total: int
    components: dict[str, str]
