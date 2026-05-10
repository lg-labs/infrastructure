"""Domain models (Pydantic v2) — design.md §3."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------- Containers ----------


class PortMapping(BaseModel):
    private: int
    public: int | None = None
    type: str = "tcp"
    ip: str | None = None


class ContainerSummary(BaseModel):
    id: str
    id_short: str
    name: str
    image: str
    image_id: str | None = None
    state: str                              # running|exited|paused|restarting|created|dead|removing
    status: str                             # human-readable
    compose_project: str | None = None
    compose_service: str | None = None
    ports: list[PortMapping] = Field(default_factory=list)
    labels_lglabs: dict[str, str] = Field(default_factory=dict)
    is_protected: bool = False
    created: str | None = None              # ISO 8601


class EnvVar(BaseModel):
    key: str
    value: str


class MountInfo(BaseModel):
    type: str = ""
    source: str = ""
    target: str = ""
    mode: str = ""


class NetworkAttachment(BaseModel):
    name: str
    ip: str | None = None
    mac: str | None = None


class RestartPolicy(BaseModel):
    name: str = "no"
    max_retries: int = 0


class HealthInfo(BaseModel):
    status: str | None = None
    failing_streak: int = 0


class ContainerDetail(ContainerSummary):
    image_digest: str | None = None
    command: list[str] = Field(default_factory=list)
    env: list[EnvVar] = Field(default_factory=list)
    mounts: list[MountInfo] = Field(default_factory=list)
    networks: list[NetworkAttachment] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    restart_policy: RestartPolicy = Field(default_factory=RestartPolicy)
    health: HealthInfo | None = None


class ContainersPage(BaseModel):
    items: list[ContainerSummary]
    total: int
    page: int
    page_size: int


class LogsResponse(BaseModel):
    lines: list[str]
    tail: int
    truncated: bool = False


# ---------- Summary ----------


class ContainersByState(BaseModel):
    total: int = 0
    running: int = 0
    exited: int = 0
    paused: int = 0
    restarting: int = 0
    created: int = 0


class ComponentsHealth(BaseModel):
    docker: Literal["ok", "degraded", "unavailable"] = "ok"
    sqlite: Literal["ok", "unavailable"] = "ok"


class SummaryResponse(BaseModel):
    containers: ContainersByState
    images_total: int
    volumes_total: int
    networks_total: int
    daemon_version: str | None = None
    daemon_api_version: str | None = None
    images_size_mb: float = 0.0
    components: ComponentsHealth


# ---------- Health ----------


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"] = "ok"
    docker: Literal["ok", "degraded", "unavailable"] = "ok"
    sqlite: Literal["ok", "unavailable"] = "ok"


# ---------- Images ----------


class ImageSummary(BaseModel):
    id: str
    id_short: str
    repository: str | None = None
    tag: str | None = None
    size_mb: float = 0.0
    created: str | None = None
    containers_using: int = 0


class ImagesPage(BaseModel):
    items: list[ImageSummary]
    total: int
    page: int
    page_size: int


# ---------- Volumes ----------


class VolumeSummary(BaseModel):
    name: str
    driver: str = "local"
    mountpoint: str | None = None
    created: str | None = None
    size_mb: float | None = None      # may be None (size compute is expensive)
    containers_using: int = 0


class VolumesPage(BaseModel):
    items: list[VolumeSummary]
    total: int
    page: int
    page_size: int


# ---------- Networks ----------


class NetworkSummary(BaseModel):
    id: str
    id_short: str
    name: str
    driver: str = "bridge"
    scope: str = "local"
    internal: bool = False
    is_builtin: bool = False
    containers_attached: int = 0


class NetworksPage(BaseModel):
    items: list[NetworkSummary]
    total: int
    page: int
    page_size: int
