"""SQLite connection + idempotent migration runner."""

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from ..settings import settings

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _connect() -> sqlite3.Connection:
    Path(settings.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.sqlite_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


# Single connection reused; SQLite + WAL handles concurrency well for our load
_conn: sqlite3.Connection | None = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = _connect()
    return _conn


@contextmanager
def tx():
    """Transaction context manager."""
    c = get_conn()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    try:
        rows = conn.execute("SELECT version FROM _schema_version").fetchall()
        return {r["version"] for r in rows}
    except sqlite3.OperationalError:
        return set()


def run_migrations() -> None:
    conn = get_conn()
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        log.warning("no migration files found at %s", MIGRATIONS_DIR)
        return

    applied = applied_versions(conn)

    for path in files:
        try:
            version = int(path.stem.split("_", 1)[0])
        except ValueError:
            log.error("skipping %s: filename must start with NNN_", path.name)
            continue

        if version in applied:
            log.debug("migration %s already applied", path.name)
            continue

        log.info("applying migration %s", path.name)
        sql = path.read_text(encoding="utf-8")
        with tx() as c:
            c.executescript(sql)
            # _schema_version is created by 001; insert is safe afterwards
            c.execute(
                "INSERT OR IGNORE INTO _schema_version (version) VALUES (?)",
                (version,),
            )
        log.info("migration %s applied", path.name)
