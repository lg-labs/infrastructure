-- Kafka Dashboard — initial schema (design.md §4.1)
-- Idempotent: all CREATE statements use IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS _schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS topic_metadata (
    name        TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    owner       TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    created_by  TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_by  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_topic_metadata_owner ON topic_metadata(owner);

CREATE TABLE IF NOT EXISTS acl_metadata (
    id              TEXT PRIMARY KEY,
    principal       TEXT NOT NULL,
    host            TEXT NOT NULL DEFAULT '*',
    operation       TEXT NOT NULL,
    resource_type   TEXT NOT NULL,
    resource_name   TEXT NOT NULL,
    pattern_type    TEXT NOT NULL,
    permission_type TEXT NOT NULL,
    note            TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    created_by      TEXT NOT NULL,
    UNIQUE (principal, host, operation, resource_type, resource_name, pattern_type, permission_type)
);
CREATE INDEX IF NOT EXISTS idx_acl_principal     ON acl_metadata(principal);
CREATE INDEX IF NOT EXISTS idx_acl_resource_name ON acl_metadata(resource_name);

CREATE TABLE IF NOT EXISTS audit_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       TEXT    NOT NULL DEFAULT (datetime('now')),
    user     TEXT    NOT NULL,
    groups   TEXT,
    method   TEXT    NOT NULL,
    path     TEXT    NOT NULL,
    status   INTEGER NOT NULL,
    resource TEXT,
    detail   TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts   ON audit_log(ts);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user);
