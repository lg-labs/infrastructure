"""Topics router (US-1..4, US-9 export)."""

import json
import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response

from ..deps import CurrentUser, require_reader, require_writer
from ..errors import (
    ConfirmationRequired,
    InternalTopicProtected,
    InvalidOwner,
    InvalidPartitions,
    InvalidTopicName,
    TopicNotFound,
)
from ..models.domain import (
    CreateTopicReq,
    PartitionDetail,
    TopicDetail,
    TopicListResp,
    TopicSummary,
    UpdateTopicReq,
    validate_topic_name,
)
from ..owners import list_owner_ids
from ..repos import topic_metadata_repo
from ..repos import acl_metadata_repo
from ..repos.kafka_repo import get_kafka_repo, is_internal

router = APIRouter(prefix="/topics", tags=["topics"])
log = logging.getLogger(__name__)


def _to_summary(name: str, info_partial: dict | None, meta: dict | None) -> TopicSummary:
    """Build a summary from quick listing (no per-topic describe)."""
    return TopicSummary(
        name=name,
        partitions=(info_partial or {}).get("partitions", 0),
        replication_factor=(info_partial or {}).get("replication_factor", 0),
        is_internal=is_internal(name),
        description=(meta or {}).get("description"),
        owner=(meta or {}).get("owner"),
    )


def _to_detail(info, meta: dict | None) -> TopicDetail:
    cleanup = info.configs.get("cleanup.policy")
    retention = info.configs.get("retention.ms")
    min_isr = info.configs.get("min.insync.replicas")
    return TopicDetail(
        name=info.name,
        partitions=info.partitions,
        replication_factor=info.replication_factor,
        is_internal=info.is_internal,
        cleanup_policy=cleanup,
        retention_ms=int(retention) if retention is not None else None,
        min_insync_replicas=int(min_isr) if min_isr is not None else None,
        configs=info.configs,
        partitions_detail=[
            PartitionDetail(id=p.id, leader=p.leader, replicas=p.replicas, isr=p.isr)
            for p in info.partition_details
        ],
        description=(meta or {}).get("description"),
        owner=(meta or {}).get("owner"),
        created_at=(meta or {}).get("created_at"),
        created_by=(meta or {}).get("created_by"),
        updated_at=(meta or {}).get("updated_at"),
        updated_by=(meta or {}).get("updated_by"),
    )


def _describe_with_retry(repo, name: str, attempts: int = 5, delay_s: float = 0.3):
    """Describe a topic with brief retries.

    Kafka may return UNKNOWN_TOPIC for a few hundred ms after create_topics()
    while metadata propagates. Retry to give the cluster a moment to converge.
    """
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return repo.describe_topic(name)
        except TopicNotFound as e:
            last_exc = e
            if i + 1 < attempts:
                time.sleep(delay_s)
    raise last_exc  # type: ignore[misc]


# ---------- LIST ----------

@router.get("", response_model=TopicListResp, dependencies=[Depends(require_reader)])
def list_topics(
    include_internal: bool = Query(False),
    search: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> TopicListResp:
    repo = get_kafka_repo()
    all_names = repo.list_topics()

    if not include_internal:
        all_names = [n for n in all_names if not is_internal(n)]
    if search:
        s = search.lower()
        all_names = [n for n in all_names if s in n.lower()]

    total = len(all_names)
    start = (page - 1) * page_size
    end = start + page_size
    page_names = all_names[start:end]

    metas = topic_metadata_repo.get_many(page_names)
    items = [_to_summary(n, None, metas.get(n)) for n in page_names]
    return TopicListResp(items=items, total=total, page=page, page_size=page_size)


# ---------- GET ----------

@router.get("/{name}", response_model=TopicDetail, dependencies=[Depends(require_reader)])
def get_topic(name: str) -> TopicDetail:
    info = get_kafka_repo().describe_topic(name)
    meta = topic_metadata_repo.get(name)
    return _to_detail(info, meta)


# ---------- CREATE ----------

@router.post("", response_model=TopicDetail, status_code=201)
def create_topic(req: CreateTopicReq, user: Annotated[CurrentUser, Depends(require_writer)]) -> TopicDetail:
    # Owner must exist in YAML
    valid_owners = list_owner_ids()
    if req.owner not in valid_owners:
        raise InvalidOwner(req.owner, valid_owners)

    # Reject internal-name attempts even if they passed the regex
    if is_internal(req.name):
        raise InternalTopicProtected(req.name)

    # Build kafka configs from the request
    cfgs = {
        "cleanup.policy": req.cleanup_policy,
        "retention.ms": str(req.retention_ms),
        "min.insync.replicas": str(req.min_insync_replicas),
    }

    repo = get_kafka_repo()
    repo.create_topic(req.name, req.partitions, req.replication_factor, cfgs)

    # Persist metadata
    topic_metadata_repo.upsert(
        name=req.name, description=req.description, owner=req.owner,
        user=user.user or "unknown",
    )

    info = _describe_with_retry(repo, req.name)
    meta = topic_metadata_repo.get(req.name)
    return _to_detail(info, meta)


# ---------- UPDATE ----------

@router.patch("/{name}", response_model=TopicDetail)
def update_topic(name: str, req: UpdateTopicReq, user: Annotated[CurrentUser, Depends(require_writer)]) -> TopicDetail:
    if is_internal(name):
        raise InternalTopicProtected(name)

    repo = get_kafka_repo()
    current = repo.describe_topic(name)  # raises 404 if missing

    # Increase partitions only (must be > current)
    if req.partitions is not None and req.partitions != current.partitions:
        if req.partitions < current.partitions:
            raise InvalidPartitions(req.partitions, "partitions can only be increased")
        repo.increase_partitions(name, req.partitions)

    # Alter configs
    cfg_updates: dict[str, str] = {}
    if req.cleanup_policy is not None:
        cfg_updates["cleanup.policy"] = req.cleanup_policy
    if req.retention_ms is not None:
        cfg_updates["retention.ms"] = str(req.retention_ms)
    if req.min_insync_replicas is not None:
        cfg_updates["min.insync.replicas"] = str(req.min_insync_replicas)
    if cfg_updates:
        repo.alter_configs(name, cfg_updates)

    # Update metadata if provided
    if req.description is not None or req.owner is not None:
        existing = topic_metadata_repo.get(name) or {}
        new_desc = req.description or existing.get("description") or ""
        new_owner = req.owner or existing.get("owner") or ""
        if req.owner is not None and req.owner not in list_owner_ids():
            raise InvalidOwner(req.owner, list_owner_ids())
        if not new_desc or len(new_desc) < 10:
            raise InvalidTopicName(name, "description (existing or new) must be ≥ 10 chars")
        topic_metadata_repo.upsert(name, new_desc, new_owner, user.user or "unknown")

    info = repo.describe_topic(name)
    meta = topic_metadata_repo.get(name)
    return _to_detail(info, meta)


# ---------- DELETE ----------

@router.delete("/{name}", status_code=204)
def delete_topic(
    name: str,
    user: Annotated[CurrentUser, Depends(require_writer)],
    x_confirm_resource: Annotated[str | None, Header()] = None,
) -> Response:
    if is_internal(name):
        raise InternalTopicProtected(name)
    if x_confirm_resource != name:
        raise ConfirmationRequired(name)

    repo = get_kafka_repo()
    repo.delete_topic(name)  # raises 404 if missing
    topic_metadata_repo.delete(name)
    return Response(status_code=204)


# ---------- EXPORT (US-9) ----------

@router.get("/{name}/export", dependencies=[Depends(require_writer)])
def export_topic(name: str) -> Response:
    info = get_kafka_repo().describe_topic(name)
    meta = topic_metadata_repo.get(name)
    acls = acl_metadata_repo.list_for_resource("TOPIC", name)
    payload = {
        "topic": _to_detail(info, meta).model_dump(),
        "acl_metadata_associated": acls,
        "schemas_associated": [],
    }
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{name}.json"'},
    )
