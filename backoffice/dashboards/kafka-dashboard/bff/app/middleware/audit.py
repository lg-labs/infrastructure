"""Audit middleware — logs each request as JSON to stdout AND to SQLite.

Schema (design.md §8.3). Sanitization rules (§8.4):
  - never log request bodies
  - never log secret-bearing headers
  - on updates, log only the *keys* that changed, not values
"""

import json
import logging
import time
import uuid
from typing import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..repos.db import tx

audit_log = logging.getLogger("kafka_dashboard.audit")


def _safe_groups(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [g.strip() for g in raw.split(",") if g.strip()]


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        # Skip health to avoid noise
        if request.url.path == "/api/health":
            return await call_next(request)

        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        started = time.perf_counter()

        user = request.headers.get("x-auth-request-user", "")
        groups = _safe_groups(request.headers.get("x-auth-request-groups"))
        original_uri = request.headers.get("x-original-uri", request.url.path)

        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            status = 500
            raise
        finally:
            duration_ms = int((time.perf_counter() - started) * 1000)

            event = {
                "audit_source": "kafka-dashboard-bff",
                "audit_type": "request",
                "user": user or None,
                "groups": groups,
                "method": request.method,
                "path": request.url.path,
                "original_uri": original_uri,
                "status": status,
                "duration_ms": duration_ms,
                "request_id": request_id,
            }
            # 1) stdout (filebeat picks it up — Phase F)
            audit_log.info(json.dumps(event, ensure_ascii=False))

            # 2) SQLite (covers L2 with persistent local copy)
            try:
                resource = _extract_resource(request.url.path)
                with tx() as c:
                    c.execute(
                        "INSERT INTO audit_log "
                        "(user, groups, method, path, status, resource, "
                        " request_id, duration_ms, audit_source, original_uri) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (user or "anonymous", ",".join(groups), request.method,
                         request.url.path, status, resource,
                         request_id, duration_ms, "kafka-dashboard-bff", original_uri),
                    )
            except Exception as e:  # pragma: no cover
                audit_log.warning("could not persist audit row: %s", e)

        # Add request id back for correlation
        response.headers["x-request-id"] = request_id
        return response


def _extract_resource(path: str) -> str | None:
    """Pull the resource id (topic/schema/acl id) from the URL."""
    parts = [p for p in path.split("/") if p]
    # /api/topics/<name>  or  /api/topics/<name>/export
    if len(parts) >= 3 and parts[0] == "api":
        return parts[2]
    return None
