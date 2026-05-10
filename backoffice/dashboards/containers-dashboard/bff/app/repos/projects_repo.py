"""ProjectsRepo (Phase I) — group containers by docker-compose project label.

Read-only. Reuses the `DockerRepo` singleton; no extra docker.sock perms.
See design.md §13 for the full spec.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from requests.exceptions import ConnectionError as ReqConnError, ReadTimeout

from ..errors import DockerUnavailable, ProjectNotFound
from ..models.projects import (
    AggregateStatus,
    GraphEdge,
    GraphNode,
    ProjectDetail,
    ProjectGraph,
    ProjectListItem,
    ProjectNetwork,
    ProjectService,
    ProjectVolume,
)
from ..safety.denylist import is_protected
from .docker_repo import (
    BUILTIN_NETWORKS,
    DockerRepo,
    _COMPOSE_PROJECT_LABEL,
    _COMPOSE_SERVICE_LABEL,
    _normalize_name,
    get_docker_repo,
)

log = logging.getLogger(__name__)

UNMANAGED = "(unmanaged)"
_COMPOSE_DEPENDS_ON_LABEL = "com.docker.compose.depends_on"
# In compose v2 networks default to bridge driver but the *network resource* is
# named like `<project>_default`; only the *real* docker-builtin "bridge" should
# be skipped from edges. Builtins == BUILTIN_NETWORKS.


class ProjectsRepo:
    """Compose-project view of the daemon. Read-only, label-driven."""

    def __init__(self, docker_repo: DockerRepo) -> None:
        self._docker = docker_repo

    # ---------- public ----------

    def list_projects(self, *, include_unmanaged: bool = False) -> list[ProjectListItem]:
        groups = self._group_containers()
        items: list[ProjectListItem] = []
        for project_name, containers in groups.items():
            if project_name == UNMANAGED and not include_unmanaged:
                continue
            items.append(self._summarize_project(project_name, containers))
        # Stable order: real projects A→Z, then (unmanaged)
        items.sort(key=lambda p: (p.is_unmanaged, p.name))
        return items

    def get_project(self, name: str) -> ProjectDetail:
        groups = self._group_containers()
        containers = groups.get(name)
        if not containers:
            raise ProjectNotFound(name)
        return self._build_detail(name, containers)

    # ---------- internals ----------

    def _group_containers(self) -> dict[str, list[Any]]:
        try:
            raw = self._docker.client.containers.list(all=True)
        except (ReqConnError, ReadTimeout) as e:
            raise DockerUnavailable(str(e)) from e

        groups: dict[str, list[Any]] = defaultdict(list)
        for c in raw:
            attrs = c.attrs or {}
            labels = (attrs.get("Config") or {}).get("Labels") or {}
            project = labels.get(_COMPOSE_PROJECT_LABEL) or UNMANAGED
            groups[project].append(c)
        return groups

    def _summarize_project(self, name: str, containers: list[Any]) -> ProjectListItem:
        services: list[str] = []
        networks: set[str] = set()
        volumes: set[str] = set()
        running = 0
        states: list[str] = []
        created_dts: list[datetime] = []

        for c in containers:
            attrs = c.attrs or {}
            cfg = attrs.get("Config") or {}
            labels = cfg.get("Labels") or {}
            state = (attrs.get("State") or {}).get("Status") or c.status or "created"
            states.append(state)
            if state == "running":
                running += 1

            svc = labels.get(_COMPOSE_SERVICE_LABEL) or _normalize_name(c)
            if svc not in services:
                services.append(svc)

            for net_name in ((attrs.get("NetworkSettings") or {}).get("Networks") or {}).keys():
                if net_name in BUILTIN_NETWORKS:
                    continue
                networks.add(net_name)

            for m in (attrs.get("Mounts") or []):
                if m.get("Type") == "volume" and m.get("Name"):
                    volumes.add(m["Name"])

            created = attrs.get("Created")
            if created:
                dt = _parse_iso(created)
                if dt is not None:
                    created_dts.append(dt)

        return ProjectListItem(
            name=name,
            services=services,
            containers_total=len(containers),
            containers_running=running,
            networks=sorted(networks),
            volumes=sorted(volumes),
            aggregate_status=_aggregate(states),
            created_at_min=min(created_dts) if created_dts else None,
            created_at_max=max(created_dts) if created_dts else None,
            is_unmanaged=(name == UNMANAGED),
        )

    def _build_detail(self, name: str, containers: list[Any]) -> ProjectDetail:
        services: list[ProjectService] = []
        networks_map: dict[str, set[str]] = defaultdict(set)
        volumes_map: dict[str, set[str]] = defaultdict(set)
        states: list[str] = []
        # service-name uniquification when replicas have same compose.service
        seen_service_names: dict[str, int] = {}

        # First pass: build services list with normalized unique service names
        for c in containers:
            attrs = c.attrs or {}
            cfg = attrs.get("Config") or {}
            labels = cfg.get("Labels") or {}
            cname = _normalize_name(c)
            raw_svc = labels.get(_COMPOSE_SERVICE_LABEL) or cname
            seen_service_names[raw_svc] = seen_service_names.get(raw_svc, 0) + 1

        # If duplicates → suffix with -N preserving first as -1
        replica_counts = {k: v for k, v in seen_service_names.items() if v > 1}
        used_idx: dict[str, int] = defaultdict(int)

        for c in containers:
            attrs = c.attrs or {}
            cfg = attrs.get("Config") or {}
            labels = cfg.get("Labels") or {}
            cname = _normalize_name(c)
            raw_svc = labels.get(_COMPOSE_SERVICE_LABEL) or cname
            if raw_svc in replica_counts:
                used_idx[raw_svc] += 1
                svc_id = f"{raw_svc}-{used_idx[raw_svc]}"
            else:
                svc_id = raw_svc

            state = (attrs.get("State") or {}).get("Status") or c.status or "created"
            states.append(state)

            depends_on_raw = labels.get(_COMPOSE_DEPENDS_ON_LABEL) or ""
            depends_on = [d.strip() for d in depends_on_raw.split(",") if d.strip()]

            ports = self._fmt_ports(attrs)
            services.append(
                ProjectService(
                    name=svc_id,
                    container=cname,
                    container_id=c.id or "",
                    container_id_short=(c.id or "")[:12],
                    state=state,
                    image=cfg.get("Image") or (c.image.tags[0] if c.image and c.image.tags else "<none>"),
                    ports=ports,
                    depends_on=depends_on,
                    is_protected=is_protected(cname),
                    created=attrs.get("Created"),
                )
            )

            for net_name in ((attrs.get("NetworkSettings") or {}).get("Networks") or {}).keys():
                networks_map[net_name].add(svc_id)
            for m in (attrs.get("Mounts") or []):
                if m.get("Type") == "volume" and m.get("Name"):
                    volumes_map[m["Name"]].add(svc_id)

        # Networks list (include builtins so user sees them, but mark them)
        nets_out = [
            ProjectNetwork(
                name=n,
                services_in=sorted(svcs),
                is_builtin=(n in BUILTIN_NETWORKS),
            )
            for n, svcs in sorted(networks_map.items())
        ]
        vols_out = [
            ProjectVolume(name=v, services_using=sorted(svcs))
            for v, svcs in sorted(volumes_map.items())
        ]

        graph = self._build_graph(services, networks_map, volumes_map)

        return ProjectDetail(
            name=name,
            is_unmanaged=(name == UNMANAGED),
            aggregate_status=_aggregate(states),
            services=services,
            networks=nets_out,
            volumes=vols_out,
            graph=graph,
        )

    def _build_graph(
        self,
        services: list[ProjectService],
        networks_map: dict[str, set[str]],
        volumes_map: dict[str, set[str]],
    ) -> ProjectGraph:
        """Star-pattern edges (design.md AD-13.1)."""
        nodes = [
            GraphNode(id=s.name, label=f"{s.name}\n{s.container}", state=s.state)
            for s in services
        ]
        svc_ids = {s.name for s in services}
        edges: list[GraphEdge] = []
        seen: set[tuple[str, str, str, str]] = set()  # dedupe (frozen pair, type, key)

        # depends_on (directed)
        for s in services:
            for dep in s.depends_on:
                # Resolve dep against either raw service name or replica-suffix; if
                # the dep matches a service id directly, use it. Otherwise drop with warn.
                if dep in svc_ids:
                    target = dep
                elif f"{dep}-1" in svc_ids:
                    target = f"{dep}-1"
                else:
                    log.warning("project graph: depends_on %s -> %s dropped (target not in project)", s.name, dep)
                    continue
                key = (s.name, target, "depends_on", "")
                if key in seen:
                    continue
                seen.add(key)
                edges.append(GraphEdge(**{"from": s.name, "to": target, "type": "depends_on"}))

        # networks (undirected, star)
        for net_name, members_set in networks_map.items():
            if net_name in BUILTIN_NETWORKS:
                continue
            members = sorted(members_set & svc_ids)
            if len(members) < 2:
                continue
            hub = members[0]
            for other in members[1:]:
                a, b = sorted([hub, other])
                key = (a, b, "network", net_name)
                if key in seen:
                    continue
                seen.add(key)
                edges.append(
                    GraphEdge(**{"from": hub, "to": other, "type": "network", "meta": {"network": net_name}})
                )

        # volumes (undirected, star)
        for vol_name, members_set in volumes_map.items():
            members = sorted(members_set & svc_ids)
            if len(members) < 2:
                continue
            hub = members[0]
            for other in members[1:]:
                a, b = sorted([hub, other])
                key = (a, b, "volume", vol_name)
                if key in seen:
                    continue
                seen.add(key)
                edges.append(
                    GraphEdge(**{"from": hub, "to": other, "type": "volume", "meta": {"volume": vol_name}})
                )

        return ProjectGraph(nodes=nodes, edges=edges)

    @staticmethod
    def _fmt_ports(attrs: dict) -> list[str]:
        out: list[str] = []
        raw_ports = (attrs.get("NetworkSettings") or {}).get("Ports") or {}
        for key, bindings in raw_ports.items():
            priv, _, proto = key.partition("/")
            proto = proto or "tcp"
            if not bindings:
                out.append(f"{priv}/{proto}")
                continue
            for b in bindings:
                pub = b.get("HostPort")
                if pub:
                    out.append(f"{pub}->{priv}/{proto}")
                else:
                    out.append(f"{priv}/{proto}")
        return sorted(set(out))


# ---------- helpers ----------


def _aggregate(states: list[str]) -> AggregateStatus:
    if not states:
        return "stopped"
    running = sum(1 for s in states if s == "running")
    total = len(states)
    if running == total:
        return "up"
    if running == 0:
        if any(s in ("dead", "restarting") for s in states):
            return "down"
        return "stopped"
    return "degraded"


def _parse_iso(value: str) -> datetime | None:
    """Docker uses ISO 8601 with nanosecond precision; truncate to microseconds."""
    if not value:
        return None
    try:
        # 2026-05-10T12:34:56.123456789Z → strip ns + Z
        v = value.rstrip("Z")
        if "." in v:
            head, frac = v.split(".", 1)
            v = f"{head}.{frac[:6]}"
        return datetime.fromisoformat(v).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


# ---------- singleton ----------


_repo: ProjectsRepo | None = None


def get_projects_repo() -> ProjectsRepo:
    global _repo
    if _repo is None:
        _repo = ProjectsRepo(get_docker_repo())
    return _repo
