"""Self-protection denylist (CONSTITUTION-addendum §B5, requirements §7.1).

This list is HARD-CODED on purpose. It cannot be disabled by env, file or
runtime config — that is a deliberate security tradeoff to prevent the
BackOffice from being used to disable its own gateway, SSO or audit pipeline.

If a future BackOffice service must be added to the denylist, edit this
module and ship a new release.
"""
from __future__ import annotations

from ..errors import ProtectedResource


# Frozen — DO NOT mutate at runtime.
DENYLIST: frozenset[str] = frozenset(
    {
        "lg-infra-backoffice-keycloak",
        "lg-infra-backoffice-gateway",
        "lg-infra-backoffice-proxy",          # oauth2-proxy
        "lg-infra-backoffice-portainer",
        "lg-infra-backoffice-containers-dashboard-bff",
        "lg-infra-backoffice-containers-dashboard-fe",
    }
)


def is_protected(name: str | None) -> bool:
    """Return True if `name` is on the BackOffice self-protection denylist."""
    if not name:
        return False
    return name in DENYLIST


def assert_not_protected(name: str | None) -> None:
    """Raise ProtectedResource (423) if the container name is on the denylist.

    Mutating endpoints (start/stop/restart/delete/exec) MUST call this before
    delegating to docker-py.
    """
    if is_protected(name):
        raise ProtectedResource(name or "")
