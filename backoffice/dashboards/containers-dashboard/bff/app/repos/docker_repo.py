"""docker-py wrapper: typed helpers + exception mapping (design §7.3).

Why a wrapper?
- Map docker-py exceptions to our DomainError envelope.
- Centralize timeouts and retries (transient socket errors).
- Translate raw docker-py objects into our pydantic models with
  denylist/redaction applied.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Iterable

import docker
from docker.errors import APIError, ImageNotFound as DockerImageNotFound, NotFound
from requests.exceptions import ConnectionError as ReqConnError, ReadTimeout

from ..errors import (
    ContainerNotFound,
    DockerUnavailable,
    ImageNotFound,
    NetworkNotFound,
    VolumeNotFound,
)
from ..models.domain import (
    ContainerDetail,
    ContainerSummary,
    ContainersByState,
    HealthInfo,
    ImageSummary,
    MountInfo,
    NetworkAttachment,
    NetworkSummary,
    PortMapping,
    RestartPolicy,
    VolumeSummary,
)
from ..safety.denylist import is_protected
from ..safety.redact import redact_env_list
from ..settings import settings

log = logging.getLogger(__name__)

# Docker builtin networks (cannot be removed; design §3.6)
BUILTIN_NETWORKS = frozenset({"bridge", "host", "none"})

_LGLABS_LABEL_PREFIX = "lglabs."
_COMPOSE_PROJECT_LABEL = "com.docker.compose.project"
_COMPOSE_SERVICE_LABEL = "com.docker.compose.service"


# ---------- Client lifecycle ----------


class DockerRepo:
    """Lazy singleton docker-py client wrapper."""

    def __init__(self) -> None:
        self._client: docker.DockerClient | None = None

    @property
    def client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.DockerClient(
                base_url=settings.docker_host,
                timeout=settings.docker_api_timeout_s,
            )
        return self._client

    def ping(self) -> bool:
        """Best-effort ping; returns False on any error."""
        try:
            return bool(self.client.ping())
        except Exception as e:  # pragma: no cover
            log.warning("docker ping failed: %s", e)
            return False

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # pragma: no cover
                pass
            self._client = None

    # ---------- containers ----------

    def list_containers(self, *, include_stopped: bool = True, search: str | None = None) -> list[ContainerSummary]:
        try:
            raw = self.client.containers.list(all=include_stopped)
        except (ReqConnError, ReadTimeout) as e:
            raise DockerUnavailable(str(e)) from e

        items: list[ContainerSummary] = []
        for c in raw:
            try:
                s = _container_to_summary(c)
            except Exception as e:  # pragma: no cover - defensive
                log.warning("could not summarize container %s: %s", getattr(c, "id", "?"), e)
                continue
            if search:
                needle = search.lower()
                hay = " ".join([s.name or "", s.image or "", s.id_short or ""]).lower()
                if needle not in hay:
                    continue
            items.append(s)
        return items

    def get_container(self, ref: str) -> ContainerDetail:
        try:
            c = self.client.containers.get(ref)
        except NotFound as e:
            raise ContainerNotFound(ref) from e
        except (ReqConnError, ReadTimeout) as e:
            raise DockerUnavailable(str(e)) from e
        return _container_to_detail(c)

    def get_logs(self, ref: str, *, tail: int = 500, since: int | None = None, timestamps: bool = False) -> list[str]:
        try:
            c = self.client.containers.get(ref)
        except NotFound as e:
            raise ContainerNotFound(ref) from e
        except (ReqConnError, ReadTimeout) as e:
            raise DockerUnavailable(str(e)) from e

        try:
            data: bytes = c.logs(
                stdout=True,
                stderr=True,
                tail=tail,
                since=since,
                timestamps=timestamps,
                stream=False,
            )
        except (ReqConnError, ReadTimeout) as e:
            raise DockerUnavailable(str(e)) from e

        text = data.decode("utf-8", errors="replace") if data else ""
        return text.splitlines()

    def inspect_container(self, ref: str) -> dict[str, Any]:
        """Raw inspect output with env redacted."""
        try:
            c = self.client.containers.get(ref)
        except NotFound as e:
            raise ContainerNotFound(ref) from e
        except (ReqConnError, ReadTimeout) as e:
            raise DockerUnavailable(str(e)) from e

        attrs = dict(c.attrs)
        # Redact env in Config.Env
        cfg = attrs.get("Config") or {}
        env_list = cfg.get("Env") or []
        cfg["Env"] = [
            f"{e['key']}={e['value']}" for e in redact_env_list(env_list)
        ]
        attrs["Config"] = cfg
        return attrs

    def stream_stats(self, ref: str):
        """Return a docker-py stats generator (raw dicts ~1Hz)."""
        try:
            c = self.client.containers.get(ref)
        except NotFound as e:
            raise ContainerNotFound(ref) from e
        return c, c.stats(stream=True, decode=True)

    # ---------- images ----------

    def list_images(self) -> list[ImageSummary]:
        try:
            raw = self.client.images.list(all=False)
            containers = self.client.containers.list(all=True)
        except (ReqConnError, ReadTimeout) as e:
            raise DockerUnavailable(str(e)) from e

        # Count usage by image id
        usage: dict[str, int] = {}
        for c in containers:
            iid = (c.attrs.get("Image") or "")
            if iid:
                usage[iid] = usage.get(iid, 0) + 1

        items: list[ImageSummary] = []
        for img in raw:
            tags = img.tags or []
            if tags:
                for t in tags:
                    repo, _, tag = t.rpartition(":")
                    items.append(_image_to_summary(img, repo or t, tag or "<none>", usage))
            else:
                items.append(_image_to_summary(img, "<none>", "<none>", usage))
        return items

    # ---------- volumes ----------

    def list_volumes(self) -> list[VolumeSummary]:
        try:
            raw = self.client.volumes.list()
            containers = self.client.containers.list(all=True)
        except (ReqConnError, ReadTimeout) as e:
            raise DockerUnavailable(str(e)) from e

        usage: dict[str, int] = {}
        for c in containers:
            for m in (c.attrs.get("Mounts") or []):
                if m.get("Type") == "volume":
                    name = m.get("Name") or ""
                    if name:
                        usage[name] = usage.get(name, 0) + 1

        items: list[VolumeSummary] = []
        for v in raw:
            attrs = v.attrs or {}
            items.append(
                VolumeSummary(
                    name=v.name or "",
                    driver=attrs.get("Driver", "local"),
                    mountpoint=attrs.get("Mountpoint"),
                    created=attrs.get("CreatedAt"),
                    size_mb=None,
                    containers_using=usage.get(v.name or "", 0),
                )
            )
        return items

    # ---------- networks ----------

    def list_networks(self) -> list[NetworkSummary]:
        try:
            raw = self.client.networks.list()
        except (ReqConnError, ReadTimeout) as e:
            raise DockerUnavailable(str(e)) from e

        items: list[NetworkSummary] = []
        for n in raw:
            a = n.attrs or {}
            name = n.name or a.get("Name", "")
            attached = a.get("Containers") or {}
            items.append(
                NetworkSummary(
                    id=n.id or "",
                    id_short=(n.id or "")[:12],
                    name=name,
                    driver=a.get("Driver", "bridge"),
                    scope=a.get("Scope", "local"),
                    internal=bool(a.get("Internal", False)),
                    is_builtin=name in BUILTIN_NETWORKS,
                    containers_attached=len(attached),
                )
            )
        return items

    # ---------- summary ----------

    def get_summary(self) -> dict[str, Any]:
        try:
            info = self.client.info()
            version = self.client.version()
            containers = self.client.containers.list(all=True)
            images = self.client.images.list(all=False)
            volumes = self.client.volumes.list()
            networks = self.client.networks.list()
        except (ReqConnError, ReadTimeout) as e:
            raise DockerUnavailable(str(e)) from e

        by_state = ContainersByState(total=len(containers))
        for c in containers:
            st = (c.attrs.get("State") or {}).get("Status") or c.status or "created"
            if hasattr(by_state, st):
                setattr(by_state, st, getattr(by_state, st) + 1)

        # Sum image sizes (bytes) → MB.
        total_size = 0
        for img in images:
            sz = (img.attrs or {}).get("Size") or 0
            total_size += int(sz)

        return {
            "containers": by_state,
            "images_total": len(images),
            "volumes_total": len(volumes),
            "networks_total": len(networks),
            "daemon_version": version.get("Version"),
            "daemon_api_version": version.get("ApiVersion"),
            "images_size_mb": round(total_size / 1024 / 1024, 1),
        }


# ---------- helpers ----------


def _normalize_name(c: Any) -> str:
    name = c.name or ""
    if name.startswith("/"):
        name = name[1:]
    return name


def _container_to_summary(c: Any) -> ContainerSummary:
    attrs = c.attrs or {}
    cfg = attrs.get("Config") or {}
    state_obj = attrs.get("State") or {}
    name = _normalize_name(c)

    # Ports (NetworkSettings.Ports)
    ports: list[PortMapping] = []
    raw_ports = (attrs.get("NetworkSettings") or {}).get("Ports") or {}
    for key, bindings in raw_ports.items():
        # key like "5601/tcp"
        try:
            priv_str, _, proto = key.partition("/")
            priv = int(priv_str)
        except ValueError:
            continue
        if not bindings:
            ports.append(PortMapping(private=priv, public=None, type=proto or "tcp"))
            continue
        for b in bindings:
            try:
                pub = int(b.get("HostPort") or 0) or None
            except ValueError:
                pub = None
            ports.append(
                PortMapping(
                    private=priv,
                    public=pub,
                    type=proto or "tcp",
                    ip=b.get("HostIp") or None,
                )
            )

    labels = cfg.get("Labels") or {}
    labels_lglabs = {k: v for k, v in labels.items() if k.startswith(_LGLABS_LABEL_PREFIX)}

    return ContainerSummary(
        id=c.id or "",
        id_short=(c.id or "")[:12],
        name=name,
        image=(cfg.get("Image") or (c.image.tags[0] if c.image and c.image.tags else "<none>")),
        image_id=attrs.get("Image"),
        state=state_obj.get("Status") or c.status or "created",
        status=state_obj.get("Status") or c.status or "",
        compose_project=labels.get(_COMPOSE_PROJECT_LABEL),
        compose_service=labels.get(_COMPOSE_SERVICE_LABEL),
        ports=ports,
        labels_lglabs=labels_lglabs,
        is_protected=is_protected(name),
        created=attrs.get("Created"),
    )


def _container_to_detail(c: Any) -> ContainerDetail:
    base = _container_to_summary(c).model_dump()
    attrs = c.attrs or {}
    cfg = attrs.get("Config") or {}
    host_cfg = attrs.get("HostConfig") or {}
    state_obj = attrs.get("State") or {}

    # Env (redacted)
    env_redacted = redact_env_list(cfg.get("Env") or [])
    env = [{"key": e["key"], "value": e["value"]} for e in env_redacted]

    # Command
    cmd = cfg.get("Cmd") or []
    if isinstance(cmd, str):
        cmd = [cmd]

    # Mounts
    mounts: list[dict[str, Any]] = []
    for m in attrs.get("Mounts") or []:
        mounts.append(
            {
                "type": m.get("Type", ""),
                "source": m.get("Source", "") or m.get("Name", ""),
                "target": m.get("Destination", ""),
                "mode": m.get("Mode", ""),
            }
        )

    # Networks
    nets: list[dict[str, Any]] = []
    for net_name, net in ((attrs.get("NetworkSettings") or {}).get("Networks") or {}).items():
        nets.append(
            {
                "name": net_name,
                "ip": net.get("IPAddress") or None,
                "mac": net.get("MacAddress") or None,
            }
        )

    rp = host_cfg.get("RestartPolicy") or {}

    health = None
    h = state_obj.get("Health") or {}
    if h:
        health = {
            "status": h.get("Status"),
            "failing_streak": int(h.get("FailingStreak") or 0),
        }

    base.update(
        {
            "image_digest": (attrs.get("Image") or None),
            "command": [str(x) for x in cmd],
            "env": env,
            "mounts": mounts,
            "networks": nets,
            "labels": cfg.get("Labels") or {},
            "restart_policy": {
                "name": rp.get("Name") or "no",
                "max_retries": int(rp.get("MaximumRetryCount") or 0),
            },
            "health": health,
        }
    )
    return ContainerDetail.model_validate(base)


def _image_to_summary(img: Any, repo: str, tag: str, usage: dict[str, int]) -> ImageSummary:
    iid = img.id or ""
    sz = (img.attrs or {}).get("Size") or 0
    created = (img.attrs or {}).get("Created")
    return ImageSummary(
        id=iid,
        id_short=(iid.split(":", 1)[-1])[:12],
        repository=repo,
        tag=tag,
        size_mb=round(int(sz) / 1024 / 1024, 1),
        created=created,
        containers_using=usage.get(iid, 0),
    )


# Singleton
_repo: DockerRepo | None = None


def get_docker_repo() -> DockerRepo:
    global _repo
    if _repo is None:
        _repo = DockerRepo()
    return _repo
