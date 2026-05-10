"""Domain exceptions and HTTP error envelope (design.md §7).

Envelope:  {"error": "<code>", "message": "<human>", "details": {...}}
"""
from __future__ import annotations

from fastapi import HTTPException


class DomainError(HTTPException):
    """Base domain exception that serializes to the error envelope."""

    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        super().__init__(
            status_code=status_code,
            detail={"error": code, "message": message, "details": details or {}},
        )


# ---------- 400 ----------
class InvalidQuery(DomainError):
    def __init__(self, message: str, **details):
        super().__init__(400, "invalid_query", message, details)


class InvalidShell(DomainError):
    def __init__(self, shell: str):
        super().__init__(
            400, "invalid_shell",
            "shell must be one of: sh, bash, ash",
            {"given": shell, "allowed": ["sh", "bash", "ash"]},
        )


# ---------- 403 ----------
class BuiltinNetworkProtected(DomainError):
    def __init__(self, name: str):
        super().__init__(
            403, "builtin_network_protected",
            f"network {name!r} is a Docker builtin and cannot be removed",
            {"name": name},
        )


# ---------- 404 ----------
class ContainerNotFound(DomainError):
    def __init__(self, ref: str):
        super().__init__(404, "container_not_found", f"container {ref!r} not found", {"ref": ref})


class ImageNotFound(DomainError):
    def __init__(self, ref: str):
        super().__init__(404, "image_not_found", f"image {ref!r} not found", {"ref": ref})


class VolumeNotFound(DomainError):
    def __init__(self, name: str):
        super().__init__(404, "volume_not_found", f"volume {name!r} not found", {"name": name})


class NetworkNotFound(DomainError):
    def __init__(self, ref: str):
        super().__init__(404, "network_not_found", f"network {ref!r} not found", {"ref": ref})


# ---------- 409 ----------
class ConfirmationRequired(DomainError):
    def __init__(self, expected: str):
        super().__init__(
            409, "confirmation_required",
            "X-Confirm-Resource header missing or does not match the resource name",
            {"expected": expected},
        )


class ContainerRunning(DomainError):
    def __init__(self, name: str):
        super().__init__(
            409, "container_running",
            "container is running; stop it first or use ?force=true",
            {"name": name},
        )


class AlreadyRunning(DomainError):
    def __init__(self, name: str):
        super().__init__(409, "already_running", "container is already running", {"name": name})


class AlreadyStopped(DomainError):
    def __init__(self, name: str):
        super().__init__(409, "already_stopped", "container is already stopped", {"name": name})


class ImageInUse(DomainError):
    def __init__(self, ref: str, used_by: list[str] | None = None):
        super().__init__(
            409, "image_in_use",
            "image is in use by one or more containers",
            {"ref": ref, "used_by": used_by or []},
        )


class VolumeInUse(DomainError):
    def __init__(self, name: str):
        super().__init__(409, "volume_in_use", "volume is mounted by a container", {"name": name})


class NetworkInUse(DomainError):
    def __init__(self, name: str, attached: list[str] | None = None):
        super().__init__(
            409, "network_in_use",
            "network has containers attached",
            {"name": name, "attached": attached or []},
        )


# ---------- 423 ----------
class ProtectedResource(DomainError):
    def __init__(self, name: str, reason: str = "container is in the BackOffice denylist (self-protection)"):
        super().__init__(423, "protected_resource", reason, {"name": name})


# ---------- 503 ----------
class DockerUnavailable(DomainError):
    def __init__(self, reason: str = "docker daemon is not reachable"):
        super().__init__(503, "docker_unavailable", reason)
