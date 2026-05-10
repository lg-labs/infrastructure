"""Audit middleware — emit each request as JSON to stdout AND SQLite (design §8).

Sanitization (§8.4):
  - never log request bodies
  - never log secret-bearing headers
  - log only identifiers (resource_id, resource_name)
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..repos.db import tx

audit_log = logging.getLogger("containers_dashboard.audit")


def _safe_groups(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [g.strip() for g in raw.split(",") if g.strip()]


def _extract_resource(path: str) -> tuple[str | None, str | None]:
    """Return (resource_type, resource_id) inferred from URL path.

    Examples:
      /api/containers/abc123/restart  -> ('container', 'abc123')
      /api/images/sha256:foo          -> ('image', 'sha256:foo')
      /api/volumes/myvol              -> ('volume', 'myvol')
      /api/networks/lg-backoffice     -> ('network', 'lg-backoffice')
      /api/health, /api/summary       -> (None, None)
    """
    parts = [p for p in path.split("/") if p]
    if len(parts) < 3 or parts[0] != "api":
        return None, None
    section = parts[1]
    rid = parts[2]
    mapping = {
        "containers": "container",
        "images": "image",
        "volumes": "volume",
        "networks": "network",
    }
    return mapping.get(section), rid


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Skip health/docs/openapi to avoid noise (and health is public anyway)
        if request.url.path in ("/api/health", "/api/docs", "/api/openapi.json"):
            return await call_next(request)

        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        started = time.perf_counter()

        user = request.headers.get("x-auth-request-user", "")
        groups = _safe_groups(request.headers.get("x-auth-request-groups"))
        original_uri = request.headers.get("x-original-uri", request.url.path)

        response: Response | None = None
        status: int = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        except Exception:
            status = 500
            raise
        finally:
            duration_ms = int((time.perf_counter() - started) * 1000)
            resource_type, resource_id = _extract_resource(request.url.path)

            event = {
                "audit_source": "containers-dashboard-bff",
                "audit_type": "request",
                "user": user or None,
                "groups": groups,
                "method": request.method,
                "path": request.url.path,
                "original_uri": original_uri,
                "status": status,
                "duration_ms": duration_ms,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "request_id": request_id,
            }

            # 1) NDJSON to stdout / rotating file (Filebeat tails it)
            audit_log.info(json.dumps(event, ensure_ascii=False))

            # 2) SQLite (durable local copy)
            try:
                with tx() as c:
                    c.execute(
                        "INSERT INTO audit_log "
                        "(request_id, audit_source, audit_type, user, groups, "
                        " method, path, original_uri, status, duration_ms, "
                        " resource_type, resource_id) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            request_id,
                            "containers-dashboard-bff",
                            "request",
                            user or "anonymous",
                            ",".join(groups),
                            request.method,
                            request.url.path,
                            original_uri,
                            status,
                            duration_ms,
                            resource_type,
                            resource_id,
                        ),
                    )
            except Exception as e:  # pragma: no cover
                audit_log.warning("could not persist audit row: %s", e)

            if response is not None:
                response.headers["x-request-id"] = request_id
