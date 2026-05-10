"""Projects view models (Phase I) — design.md §13.2.

Compose-project grouping with topology graph.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# ---------- Items ----------


class ProjectService(BaseModel):
    """A single service entry within a project."""
    name: str                       # com.docker.compose.service (or container name if missing)
    container: str                  # container name (no leading /)
    container_id: str
    container_id_short: str
    state: str                      # running | exited | paused | created | restarting | dead | removing
    image: str
    ports: list[str] = Field(default_factory=list)   # "8080:80/tcp" format
    depends_on: list[str] = Field(default_factory=list)
    is_protected: bool = False
    created: str | None = None      # ISO 8601


class ProjectNetwork(BaseModel):
    name: str
    services_in: list[str] = Field(default_factory=list)
    is_builtin: bool = False        # bridge / host / none


class ProjectVolume(BaseModel):
    name: str                        # docker volume name (anon volumes get their hash)
    services_using: list[str] = Field(default_factory=list)


# ---------- Graph ----------


class GraphNode(BaseModel):
    id: str                          # service name (unique within project)
    label: str                       # "service\ncontainer"
    state: str


class GraphEdge(BaseModel):
    from_: str = Field(alias="from")
    to: str
    type: Literal["depends_on", "network", "volume"]
    meta: dict = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class ProjectGraph(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


# ---------- Top-level shapes ----------


AggregateStatus = Literal["up", "degraded", "down", "stopped"]


class ProjectListItem(BaseModel):
    """Card-friendly summary for list view."""
    name: str
    services: list[str] = Field(default_factory=list)        # service names
    containers_total: int = 0
    containers_running: int = 0
    networks: list[str] = Field(default_factory=list)
    volumes: list[str] = Field(default_factory=list)
    aggregate_status: AggregateStatus = "stopped"
    created_at_min: datetime | None = None
    created_at_max: datetime | None = None
    is_unmanaged: bool = False


class ProjectDetail(BaseModel):
    """Full detail for a single project: services, networks, volumes, graph."""
    name: str
    is_unmanaged: bool = False
    aggregate_status: AggregateStatus = "stopped"
    services: list[ProjectService] = Field(default_factory=list)
    networks: list[ProjectNetwork] = Field(default_factory=list)
    volumes: list[ProjectVolume] = Field(default_factory=list)
    graph: ProjectGraph = Field(default_factory=ProjectGraph)
