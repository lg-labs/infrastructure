"""Summary router (US-8, C-H)."""

import logging

from fastapi import APIRouter, Depends
from kafka.errors import NoBrokersAvailable

from ..deps import require_reader
from ..models.domain import SummaryResp
from ..repos import topic_metadata_repo
from ..repos.kafka_repo import get_kafka_repo, is_internal
from ..repos.registry_repo import get_registry_repo

router = APIRouter(tags=["summary"])
log = logging.getLogger(__name__)


@router.get("/summary", response_model=SummaryResp, dependencies=[Depends(require_reader)])
def summary() -> SummaryResp:
    components = {"kafka": "ok", "registry": "ok", "sqlite": "ok"}
    brokers = 0
    topics_total = 0
    topics_internal_hidden = 0

    repo = get_kafka_repo()

    try:
        brokers = repo.brokers_alive()
        names = repo.list_topics()
        internal_names = [n for n in names if is_internal(n)]
        topics_total = len(names) - len(internal_names)
        topics_internal_hidden = len(internal_names)
    except NoBrokersAvailable:
        components["kafka"] = "degraded"
    except Exception as e:
        log.warning("summary: kafka error: %s", e)
        components["kafka"] = "degraded"

    # Schemas count via SR
    schemas_total = 0
    try:
        schemas_total = len(get_registry_repo().list_subjects())
    except Exception as e:
        log.warning("summary: registry error: %s", e)
        components["registry"] = "degraded"

    # ACL count — table exists from Phase B migrations even if router lands in Phase E
    try:
        from ..repos.db import get_conn
        with get_conn() as c:
            row = c.execute("SELECT COUNT(*) AS n FROM acl_metadata").fetchone()
            acl_total = row["n"] if row else 0
    except Exception:
        acl_total = 0

    return SummaryResp(
        brokers_alive=brokers,
        topics_total=topics_total,
        topics_internal_hidden=topics_internal_hidden,
        schemas_total=schemas_total,
        acl_metadata_total=acl_total,
        components=components,
    )
