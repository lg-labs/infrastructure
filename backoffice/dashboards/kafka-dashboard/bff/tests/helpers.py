"""Test helpers (importable without relative imports)."""


def headers_for(role: str | None) -> dict[str, str]:
    """Build oauth2-proxy-style headers for a given role.

    `deps.get_current_user` looks for literal role tokens in groups
    (admin/operator/support/viewer) — see app/deps.py.
    """
    if role is None:
        return {}
    return {
        "X-Auth-Request-User": f"lglabs{role}",
        "X-Auth-Request-Groups": role,
        "X-Original-Uri": "/kafka/api/test",
    }
