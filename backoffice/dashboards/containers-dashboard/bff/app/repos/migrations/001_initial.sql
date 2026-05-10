CREATE TABLE IF NOT EXISTS _schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL DEFAULT (datetime('now')),
    request_id    TEXT,
    audit_source  TEXT NOT NULL DEFAULT 'containers-dashboard-bff',
    audit_type    TEXT NOT NULL,
    user          TEXT NOT NULL,
    groups        TEXT,
    method        TEXT,
    path          TEXT,
    original_uri  TEXT,
    status        INTEGER,
    duration_ms   INTEGER,
    resource_type TEXT,
    resource_id   TEXT,
    resource_name TEXT,
    detail        TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_ts          ON audit_log(ts);
CREATE INDEX IF NOT EXISTS idx_audit_user        ON audit_log(user);
CREATE INDEX IF NOT EXISTS idx_audit_request_id  ON audit_log(request_id);
CREATE INDEX IF NOT EXISTS idx_audit_audit_type  ON audit_log(audit_type);
