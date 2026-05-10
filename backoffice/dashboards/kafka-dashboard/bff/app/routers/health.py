"""Health endpoint — public (no auth)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Header
from kafka.errors import NoBrokersAvailable

from ..repos.kafka_repo import get_kafka_repo

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/health")
def health() -> dict:
    kafka_status = "ok"
    try:
        get_kafka_repo().brokers_alive()
    except NoBrokersAvailable:
        kafka_status = "degraded"
    except Exception as e:
        log.warning("kafka health probe failed: %s", e)
        kafka_status = "degraded"

    return {
        "status": "ok" if kafka_status == "ok" else "degraded",
        "kafka": kafka_status,
        "registry": "unknown",   # Phase D will probe
        "sqlite": "ok",          # if we got here, sqlite is fine
    }


@router.get("/whoami")
def whoami(
    x_auth_request_user: Annotated[str | None, Header()] = None,
    x_auth_request_groups: Annotated[str | None, Header()] = None,
) -> dict:
    """Echo identity propagated by oauth2-proxy. Useful for E2E debugging."""
    return {
        "user": x_auth_request_user,
        "groups": x_auth_request_groups,
    }
