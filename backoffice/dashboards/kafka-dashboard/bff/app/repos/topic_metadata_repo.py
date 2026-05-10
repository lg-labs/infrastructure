"""SQLite repo for topic_metadata."""

from datetime import datetime, timezone
from typing import Any

from .db import get_conn, tx


def upsert(name: str, description: str, owner: str, user: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    with tx() as c:
        existing = c.execute(
            "SELECT name FROM topic_metadata WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            c.execute(
                "UPDATE topic_metadata SET description=?, owner=?, updated_at=?, updated_by=? WHERE name=?",
                (description, owner, now, user, name),
            )
        else:
            c.execute(
                "INSERT INTO topic_metadata (name, description, owner, created_at, created_by, updated_at, updated_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, description, owner, now, user, now, user),
            )
    return get(name) or {}


def get(name: str) -> dict[str, Any] | None:
    row = get_conn().execute(
        "SELECT name, description, owner, created_at, created_by, updated_at, updated_by "
        "FROM topic_metadata WHERE name = ?", (name,)
    ).fetchone()
    return dict(row) if row else None


def get_many(names: list[str]) -> dict[str, dict[str, Any]]:
    if not names:
        return {}
    placeholders = ",".join("?" * len(names))
    rows = get_conn().execute(
        f"SELECT name, description, owner, created_at, created_by, updated_at, updated_by "
        f"FROM topic_metadata WHERE name IN ({placeholders})",
        names,
    ).fetchall()
    return {r["name"]: dict(r) for r in rows}


def delete(name: str) -> None:
    with tx() as c:
        c.execute("DELETE FROM topic_metadata WHERE name = ?", (name,))


def count() -> int:
    return get_conn().execute("SELECT COUNT(*) AS n FROM topic_metadata").fetchone()["n"]
