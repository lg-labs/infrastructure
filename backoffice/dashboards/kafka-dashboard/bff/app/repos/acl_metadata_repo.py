"""SQLite repo for `acl_metadata` (design.md §4.1).

ACL-metadata is a SQLite-only annotation. The Kafka cluster does NOT enforce
these entries (design §A6, AC-7.3). The UI must surface a permanent banner.

UNIQUE constraint covers (principal, host, operation, resource_type,
resource_name, pattern_type, permission_type).
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from .db import get_conn, tx

# Whitelists (mirror design §3.5 / §4.1)
OPERATIONS: tuple[str, ...] = (
    "READ", "WRITE", "CREATE", "DELETE", "ALTER", "DESCRIBE", "ALL",
)
RESOURCE_TYPES: tuple[str, ...] = ("TOPIC", "GROUP", "CLUSTER")
PATTERN_TYPES: tuple[str, ...] = ("LITERAL", "PREFIXED")
PERMISSION_TYPES: tuple[str, ...] = ("ALLOW", "DENY")


_COLS = (
    "id", "principal", "host", "operation",
    "resource_type", "resource_name", "pattern_type", "permission_type",
    "note", "created_at", "created_by",
)
_COLS_SQL = ", ".join(_COLS)


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def list_all(
    principal: str | None = None,
    resource_name: str | None = None,
    resource_type: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    """Return paginated rows + total count matching optional filters.

    Filters use case-insensitive substring matching for principal/resource_name
    and exact match for resource_type.
    """
    where: list[str] = []
    params: list[Any] = []
    if principal:
        where.append("LOWER(principal) LIKE ?")
        params.append(f"%{principal.lower()}%")
    if resource_name:
        where.append("LOWER(resource_name) LIKE ?")
        params.append(f"%{resource_name.lower()}%")
    if resource_type:
        where.append("resource_type = ?")
        params.append(resource_type.upper())
    sql_where = (" WHERE " + " AND ".join(where)) if where else ""

    conn = get_conn()
    total = conn.execute(
        f"SELECT COUNT(*) AS n FROM acl_metadata{sql_where}", params
    ).fetchone()["n"]

    offset = (page - 1) * page_size
    rows = conn.execute(
        f"SELECT {_COLS_SQL} FROM acl_metadata{sql_where} "
        f"ORDER BY created_at DESC, id LIMIT ? OFFSET ?",
        [*params, page_size, offset],
    ).fetchall()
    return [dict(r) for r in rows], int(total)


def get(acl_id: str) -> dict[str, Any] | None:
    row = get_conn().execute(
        f"SELECT {_COLS_SQL} FROM acl_metadata WHERE id = ?", (acl_id,)
    ).fetchone()
    return _row_to_dict(row)


def list_for_resource(resource_type: str, resource_name: str) -> list[dict[str, Any]]:
    """ACL entries whose pattern matches a given concrete resource.

    LITERAL: equality on resource_name.
    PREFIXED: stored resource_name is treated as the prefix.
    """
    rows = get_conn().execute(
        f"SELECT {_COLS_SQL} FROM acl_metadata "
        "WHERE resource_type = ? AND ("
        "  (pattern_type = 'LITERAL' AND resource_name = ?) OR "
        "  (pattern_type = 'PREFIXED' AND ? LIKE resource_name || '%')"
        ") ORDER BY created_at DESC, id",
        (resource_type, resource_name, resource_name),
    ).fetchall()
    return [dict(r) for r in rows]


def insert(
    *,
    principal: str,
    host: str,
    operation: str,
    resource_type: str,
    resource_name: str,
    pattern_type: str,
    permission_type: str,
    note: str | None,
    user: str,
) -> dict[str, Any]:
    """Insert a new ACL-metadata row. Raises sqlite3.IntegrityError on UNIQUE."""
    new_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with tx() as c:
        c.execute(
            "INSERT INTO acl_metadata "
            "(id, principal, host, operation, resource_type, resource_name, "
            " pattern_type, permission_type, note, created_at, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (new_id, principal, host, operation, resource_type, resource_name,
             pattern_type, permission_type, note, now, user),
        )
    return get(new_id) or {}


def update(
    acl_id: str,
    *,
    principal: str,
    host: str,
    operation: str,
    resource_type: str,
    resource_name: str,
    pattern_type: str,
    permission_type: str,
    note: str | None,
) -> dict[str, Any] | None:
    """Update everything but `created_at`/`created_by`. Returns the new row, or
    None if the id does not exist. Raises sqlite3.IntegrityError on UNIQUE."""
    if get(acl_id) is None:
        return None
    with tx() as c:
        c.execute(
            "UPDATE acl_metadata SET principal=?, host=?, operation=?, "
            "resource_type=?, resource_name=?, pattern_type=?, "
            "permission_type=?, note=? WHERE id=?",
            (principal, host, operation, resource_type, resource_name,
             pattern_type, permission_type, note, acl_id),
        )
    return get(acl_id)


def delete(acl_id: str) -> bool:
    with tx() as c:
        cur = c.execute("DELETE FROM acl_metadata WHERE id = ?", (acl_id,))
        return cur.rowcount > 0


def count() -> int:
    return int(get_conn().execute(
        "SELECT COUNT(*) AS n FROM acl_metadata"
    ).fetchone()["n"])
