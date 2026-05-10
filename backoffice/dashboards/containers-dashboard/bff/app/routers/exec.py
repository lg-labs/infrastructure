"""Exec WebSocket router (Phase E — US-5).

Admin-only interactive shell into a running, non-protected container.

Wire protocol:
  - Client connects to: WS /api/containers/{ref}/exec?shell=sh|bash|ash
  - Client sends: text frames (stdin) and JSON frames {"resize":{"cols","rows"}}
  - Server sends: text frames (stdout+stderr merged because TTY)
  - Idle timeout: 5 minutes without bytes either way -> close 1000 idle_timeout

Security:
  - Gateway already restricted this path to `admin` group via /oauth2/auth.
  - BFF re-checks `X-Auth-Request-Groups` (defense in depth).
  - assert_not_protected(name) -> 423 if denylisted (never reaches docker).
  - shell must be in {sh, bash, ash}; nothing else.
  - audit emits exec_open at success and exec_close on close (NO frame
    contents are persisted — only metadata).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from ..repos.db import tx
from ..repos.docker_repo import get_docker_repo
from ..safety.denylist import is_protected
from ..settings import settings

log = logging.getLogger(__name__)
audit_log = logging.getLogger("containers_dashboard.audit")

router = APIRouter(prefix="/containers", tags=["exec"])

ALLOWED_SHELLS = {"sh", "bash", "ash"}
IDLE_TIMEOUT_SECONDS = 300  # 5 minutes (design §B7)


def _has_admin_group(ws: WebSocket) -> bool:
    raw = ws.headers.get("x-auth-request-groups", "") or ""
    groups = [g.strip() for g in raw.split(",") if g.strip()]
    return "admin" in groups


def _normalize_name(c: Any) -> str:
    name = c.name or ""
    return name[1:] if name.startswith("/") else name


def _audit_event(*, audit_type: str, user: str, groups: list[str], request_id: str,
                 resource_id: str, resource_name: str, status_code: int,
                 detail: dict[str, Any] | None = None, duration_ms: int | None = None) -> None:
    """Emit one row to NDJSON logger + SQLite (no frame content ever)."""
    payload = {
        "audit_source": "containers-dashboard-bff",
        "audit_type": audit_type,
        "user": user or None,
        "groups": groups,
        "method": "WS",
        "path": f"/api/containers/{resource_id}/exec",
        "status": status_code,
        "duration_ms": duration_ms,
        "resource_type": "container",
        "resource_id": resource_id,
        "resource_name": resource_name,
        "request_id": request_id,
        "detail": detail or {},
    }
    audit_log.info(json.dumps(payload, ensure_ascii=False))
    try:
        with tx() as c:
            c.execute(
                "INSERT INTO audit_log "
                "(request_id, audit_source, audit_type, user, groups, method, path, "
                " status, duration_ms, resource_type, resource_id, resource_name, detail) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    request_id,
                    "containers-dashboard-bff",
                    audit_type,
                    user or "anonymous",
                    ",".join(groups),
                    "WS",
                    f"/api/containers/{resource_id}/exec",
                    status_code,
                    duration_ms,
                    "container",
                    resource_id,
                    resource_name,
                    json.dumps(detail or {}, ensure_ascii=False),
                ),
            )
    except Exception as e:  # pragma: no cover
        log.warning("could not persist exec audit row (%s): %s", audit_type, e)


@router.websocket("/{ref}/exec")
async def exec_ws(ws: WebSocket, ref: str, shell: str = Query("sh")) -> None:
    # Best-effort identity from gateway-injected headers
    user = ws.headers.get("x-auth-request-user", "") or ""
    groups_raw = ws.headers.get("x-auth-request-groups", "") or ""
    groups = [g.strip() for g in groups_raw.split(",") if g.strip()]
    request_id = ws.headers.get("x-request-id") or str(uuid.uuid4())

    # ---- Pre-flight (before WS accept): close with policy violation if anything fails.
    # Note: WebSocket handshake must accept first OR reject with HTTP, but FastAPI gives
    # us only the WS object here — we accept then immediately close with code+reason.

    if not _has_admin_group(ws):
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="forbidden")
        _audit_event(
            audit_type="exec_open", user=user, groups=groups, request_id=request_id,
            resource_id=ref, resource_name=ref, status_code=403,
            detail={"close_reason": "forbidden_not_admin"},
        )
        return

    if shell not in ALLOWED_SHELLS:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason=f"invalid_shell:{shell}")
        _audit_event(
            audit_type="exec_open", user=user, groups=groups, request_id=request_id,
            resource_id=ref, resource_name=ref, status_code=400,
            detail={"close_reason": "invalid_shell", "shell": shell},
        )
        return

    # Resolve container -> name
    repo = get_docker_repo()
    try:
        container = repo._get_container_or_404(ref)
    except Exception as e:
        await ws.close(code=status.WS_1011_INTERNAL_ERROR, reason="container_not_found")
        _audit_event(
            audit_type="exec_open", user=user, groups=groups, request_id=request_id,
            resource_id=ref, resource_name=ref, status_code=404,
            detail={"close_reason": "container_not_found", "error": str(e)},
        )
        return

    name = _normalize_name(container)

    if is_protected(name):
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="protected_resource")
        _audit_event(
            audit_type="exec_open", user=user, groups=groups, request_id=request_id,
            resource_id=ref, resource_name=name, status_code=423,
            detail={"close_reason": "protected_resource"},
        )
        return

    # Container must be running for exec to make sense
    container.reload()
    state = (container.attrs.get("State") or {}).get("Status") or container.status
    if state != "running":
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="container_not_running")
        _audit_event(
            audit_type="exec_open", user=user, groups=groups, request_id=request_id,
            resource_id=ref, resource_name=name, status_code=409,
            detail={"close_reason": "container_not_running", "state": state},
        )
        return

    # ---- Create the docker exec instance
    try:
        api = repo.client.api
        exec_id = api.exec_create(
            container.id, cmd=[shell], tty=True, stdin=True, stdout=True, stderr=True,
        )["Id"]
        sock = api.exec_start(exec_id, detach=False, tty=True, stream=False, socket=True)
        # docker-py returns a SocketIO wrapping the raw socket; get the underlying fd
        raw_sock = getattr(sock, "_sock", None) or sock
    except Exception as e:
        await ws.close(code=status.WS_1011_INTERNAL_ERROR, reason="exec_create_failed")
        _audit_event(
            audit_type="exec_open", user=user, groups=groups, request_id=request_id,
            resource_id=ref, resource_name=name, status_code=500,
            detail={"close_reason": "exec_create_failed", "error": str(e)},
        )
        return

    await ws.accept()
    started = time.perf_counter()

    _audit_event(
        audit_type="exec_open", user=user, groups=groups, request_id=request_id,
        resource_id=ref, resource_name=name, status_code=101,
        detail={"shell": shell, "exec_id": exec_id},
    )

    close_reason = "client_disconnect"
    last_activity = time.monotonic()
    loop = asyncio.get_running_loop()

    # Make the raw socket non-blocking so we can use loop.sock_recv/sock_sendall
    try:
        raw_sock.setblocking(False)
    except Exception:
        pass

    async def ws_to_sock() -> None:
        nonlocal close_reason, last_activity
        try:
            while True:
                msg = await ws.receive()
                last_activity = time.monotonic()
                if msg["type"] == "websocket.disconnect":
                    close_reason = "client_disconnect"
                    return
                # Resize control frames are JSON text; data frames are text or bytes.
                if "text" in msg and msg["text"] is not None:
                    txt = msg["text"]
                    if txt.startswith("{") and "resize" in txt[:32]:
                        try:
                            obj = json.loads(txt)
                            r = obj.get("resize") or {}
                            cols = int(r.get("cols", 80))
                            rows = int(r.get("rows", 24))
                            api.exec_resize(exec_id, height=rows, width=cols)
                            continue
                        except Exception:
                            pass  # fall through and write as raw stdin
                    data = txt.encode("utf-8", errors="replace")
                else:
                    data = msg.get("bytes") or b""
                if data:
                    await loop.sock_sendall(raw_sock, data)
        except WebSocketDisconnect:
            close_reason = "client_disconnect"
        except Exception as e:
            close_reason = f"ws_to_sock_error:{type(e).__name__}"
            log.warning("exec ws->sock error: %s", e)

    async def sock_to_ws() -> None:
        nonlocal close_reason, last_activity
        try:
            while True:
                chunk = await loop.sock_recv(raw_sock, 4096)
                if not chunk:
                    close_reason = "exec_exited"
                    return
                last_activity = time.monotonic()
                # TTY merges stdout/stderr. Send as text for xterm.js convenience.
                await ws.send_text(chunk.decode("utf-8", errors="replace"))
        except Exception as e:
            close_reason = f"sock_to_ws_error:{type(e).__name__}"
            log.warning("exec sock->ws error: %s", e)

    async def idle_watchdog() -> None:
        nonlocal close_reason
        while True:
            await asyncio.sleep(15)
            if time.monotonic() - last_activity > IDLE_TIMEOUT_SECONDS:
                close_reason = "idle_timeout"
                return

    t_in = asyncio.create_task(ws_to_sock())
    t_out = asyncio.create_task(sock_to_ws())
    t_idle = asyncio.create_task(idle_watchdog())

    done, pending = await asyncio.wait(
        {t_in, t_out, t_idle}, return_when=asyncio.FIRST_COMPLETED,
    )
    for t in pending:
        t.cancel()
    # Drain cancellations
    for t in pending:
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass

    duration_ms = int((time.perf_counter() - started) * 1000)

    # Best-effort exit code via exec_inspect
    exit_code: int | None = None
    try:
        info = api.exec_inspect(exec_id)
        exit_code = info.get("ExitCode")
    except Exception:
        pass

    # Close socket + websocket cleanly
    try:
        raw_sock.close()
    except Exception:
        pass
    try:
        await ws.close(code=status.WS_1000_NORMAL_CLOSURE, reason=close_reason[:120])
    except Exception:
        pass

    _audit_event(
        audit_type="exec_close", user=user, groups=groups, request_id=request_id,
        resource_id=ref, resource_name=name, status_code=200,
        duration_ms=duration_ms,
        detail={
            "shell": shell,
            "exec_id": exec_id,
            "close_reason": close_reason,
            "exit_code": exit_code,
            "idle_timeout_seconds": IDLE_TIMEOUT_SECONDS,
        },
    )
