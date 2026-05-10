"""Auth dependencies — extract identity from oauth2-proxy headers.

The BFF does NOT authenticate. It TRUSTS the gateway, which is the
only path to reach the BFF (CONSTITUTION-addendum §B3 — defense in depth:
the BFF still validates here for safety in case of misconfiguration).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException


@dataclass(frozen=True)
class CurrentUser:
    user: str          # "lglabsadmin@lglabs.local"  (may be empty in test/bearer)
    groups: list[str]  # ["admin"], ["operator"], ...

    @property
    def is_admin(self) -> bool:
        return "admin" in self.groups

    @property
    def is_writer(self) -> bool:
        """admin or operator can do start/stop/restart."""
        return any(g in self.groups for g in ("admin", "operator"))

    @property
    def is_reader(self) -> bool:
        """Any authenticated role can read (GET endpoints)."""
        return any(g in self.groups for g in ("admin", "operator", "support", "viewer"))


def get_current_user(
    x_auth_request_user: Annotated[str | None, Header()] = None,
    x_auth_request_groups: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """Extract identity from oauth2-proxy headers.

    Gateway already enforced auth+authz; we propagate the identity
    for audit + defence-in-depth checks.
    """
    groups: list[str] = []
    if x_auth_request_groups:
        groups = [g.strip() for g in x_auth_request_groups.split(",") if g.strip()]

    return CurrentUser(user=x_auth_request_user or "", groups=groups)


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


def _forbidden(message: str) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={"error": "forbidden", "message": message, "details": {}},
    )


def require_reader(user: CurrentUserDep) -> CurrentUser:
    if not user.is_reader:
        raise _forbidden("authenticated reader role required")
    return user


def require_writer(user: CurrentUserDep) -> CurrentUser:
    if not user.is_writer:
        raise _forbidden("writer role required (admin or operator)")
    return user


def require_admin(user: CurrentUserDep) -> CurrentUser:
    if not user.is_admin:
        raise _forbidden("admin role required")
    return user
