"""Containers router (Phase B: read-only).

Mutations (start/stop/restart/delete) come in Phase D.
Exec WS comes in Phase E.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from ..deps import require_reader, require_writer
from ..errors import DockerUnavailable
from ..models.domain import ContainerDetail, ContainersPage, LogsResponse
from ..repos.docker_repo import get_docker_repo
from ..safety.confirm import assert_confirm_resource

log = logging.getLogger(__name__)

router = APIRouter(prefix="/containers", tags=["containers"])


@router.get(
    "",
    response_model=ContainersPage,
    dependencies=[Depends(require_reader)],
)
def list_containers(
    include_stopped: bool = Query(True),
    search: str | None = Query(None, max_length=128),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
) -> ContainersPage:
    repo = get_docker_repo()
    items = repo.list_containers(include_stopped=include_stopped, search=search)

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return ContainersPage(items=items[start:end], total=total, page=page, page_size=page_size)


@router.get(
    "/{ref}",
    response_model=ContainerDetail,
    dependencies=[Depends(require_reader)],
)
def get_container(ref: str) -> ContainerDetail:
    return get_docker_repo().get_container(ref)


@router.get(
    "/{ref}/logs",
    response_model=LogsResponse,
    dependencies=[Depends(require_reader)],
)
def get_logs(
    ref: str,
    tail: int = Query(500, ge=1, le=2000),
    since: int | None = Query(None, ge=0),
    timestamps: bool = Query(False),
) -> LogsResponse:
    lines = get_docker_repo().get_logs(ref, tail=tail, since=since, timestamps=timestamps)
    truncated = len(lines) >= tail
    return LogsResponse(lines=lines, tail=tail, truncated=truncated)


@router.get(
    "/{ref}/inspect",
    dependencies=[Depends(require_reader)],
)
def inspect_container(ref: str) -> dict[str, Any]:
    return get_docker_repo().inspect_container(ref)


# ---------- SSE stats stream ----------

def _compute_cpu_percent(prev: dict, cur: dict) -> float:
    """Standard docker-py CPU percent calculation."""
    try:
        cpu_delta = cur["cpu_stats"]["cpu_usage"]["total_usage"] - prev["cpu_stats"]["cpu_usage"]["total_usage"]
        sys_delta = cur["cpu_stats"]["system_cpu_usage"] - prev["cpu_stats"]["system_cpu_usage"]
        online = cur["cpu_stats"].get("online_cpus") or len(
            cur["cpu_stats"]["cpu_usage"].get("percpu_usage") or [1]
        )
        if sys_delta > 0 and cpu_delta > 0:
            return round((cpu_delta / sys_delta) * online * 100.0, 2)
    except Exception:
        pass
    return 0.0


def _stat_to_event(stat: dict, prev: dict | None) -> tuple[dict, dict]:
    cpu_pct = _compute_cpu_percent(prev or stat, stat) if prev else 0.0
    mem_usage = (stat.get("memory_stats") or {}).get("usage") or 0
    mem_limit = (stat.get("memory_stats") or {}).get("limit") or 0

    nets = stat.get("networks") or {}
    rx = sum((n.get("rx_bytes") or 0) for n in nets.values())
    tx = sum((n.get("tx_bytes") or 0) for n in nets.values())

    blkio = (stat.get("blkio_stats") or {}).get("io_service_bytes_recursive") or []
    blk_r = sum((e.get("value") or 0) for e in blkio if (e.get("op") or "").lower() == "read")
    blk_w = sum((e.get("value") or 0) for e in blkio if (e.get("op") or "").lower() == "write")

    event = {
        "cpu_percent": cpu_pct,
        "memory_usage_mb": round(mem_usage / 1024 / 1024, 2),
        "memory_limit_mb": round(mem_limit / 1024 / 1024, 2),
        "net_rx_kbps": round(rx / 1024, 2),
        "net_tx_kbps": round(tx / 1024, 2),
        "block_read_mb": round(blk_r / 1024 / 1024, 2),
        "block_write_mb": round(blk_w / 1024 / 1024, 2),
    }
    return event, stat


@router.get(
    "/{ref}/stats",
    dependencies=[Depends(require_reader)],
)
async def stream_stats(ref: str, request: Request) -> StreamingResponse:
    """SSE stats stream (~1Hz). Closes when client disconnects or container stops."""
    repo = get_docker_repo()
    container, stats_iter = repo.stream_stats(ref)

    state = (container.attrs.get("State") or {}).get("Status") or container.status
    if state != "running":
        async def single_unavailable():
            yield f"data: {json.dumps({'unavailable': True, 'reason': 'container_not_running'})}\n\n"
        return StreamingResponse(single_unavailable(), media_type="text/event-stream")

    async def event_gen():
        prev: dict | None = None
        try:
            for raw in stats_iter:
                if await request.is_disconnected():
                    break
                event, prev = _stat_to_event(raw, prev)
                yield f"data: {json.dumps(event)}\n\n"
                await asyncio.sleep(0)
        except Exception as e:  # pragma: no cover
            log.warning("stats stream error for %s: %s", ref, e)
        finally:
            try:
                stats_iter.close()                # type: ignore[attr-defined]
            except Exception:
                pass

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/{ref}/logs/stream",
    dependencies=[Depends(require_reader)],
)
async def stream_logs(ref: str, request: Request, tail: int = Query(500, ge=0, le=2000)) -> StreamingResponse:
    """SSE logs stream — follows the container."""
    repo = get_docker_repo()
    try:
        c = repo.client.containers.get(ref)
    except Exception as e:
        from ..errors import ContainerNotFound
        raise ContainerNotFound(ref) from e

    log_iter = c.logs(stdout=True, stderr=True, tail=tail, follow=True, stream=True, timestamps=True)

    async def event_gen():
        try:
            for chunk in log_iter:
                if await request.is_disconnected():
                    break
                if not chunk:
                    continue
                line = chunk.decode("utf-8", errors="replace").rstrip("\n")
                yield f"data: {json.dumps({'line': line})}\n\n"
                await asyncio.sleep(0)
        except Exception as e:  # pragma: no cover
            log.warning("logs stream error for %s: %s", ref, e)
        finally:
            try:
                log_iter.close()                  # type: ignore[attr-defined]
            except Exception:
                pass

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------- Mutations (Phase D) ----------
#
# US-4 — start / stop / restart. require_writer (admin|operator).
#   1. resolve container -> get name
#   2. denylist check (raises 423)  [in repo]
#   3. confirm header check (skip for start)  -> 409 if missing/mismatch
#   4. perform docker action  -> 409 if already_running/already_stopped
#   5. return new state. Audit middleware logs everything automatically.


def _resolve_name(ref: str) -> str:
    """Resolve a ref (id/name) to canonical name, raising 404 if missing."""
    c = get_docker_repo()._get_container_or_404(ref)
    name = c.name or ""
    return name[1:] if name.startswith("/") else name


@router.post(
    "/{ref}/start",
    dependencies=[Depends(require_writer)],
)
def start_container(ref: str) -> dict[str, Any]:
    # Start does not require X-Confirm-Resource (design §6.5: start is reversible-trivial).
    return get_docker_repo().start_container(ref)


@router.post(
    "/{ref}/stop",
    dependencies=[Depends(require_writer)],
)
def stop_container(
    ref: str,
    request: Request,
    timeout_seconds: int = Query(10, ge=1, le=60),
) -> dict[str, Any]:
    name = _resolve_name(ref)
    assert_confirm_resource(request, name)
    return get_docker_repo().stop_container(ref, timeout_seconds=timeout_seconds)


@router.post(
    "/{ref}/restart",
    dependencies=[Depends(require_writer)],
)
def restart_container(
    ref: str,
    request: Request,
    timeout_seconds: int = Query(10, ge=1, le=60),
) -> dict[str, Any]:
    name = _resolve_name(ref)
    assert_confirm_resource(request, name)
    return get_docker_repo().restart_container(ref, timeout_seconds=timeout_seconds)
