-- 002_audit_log_extend.sql — Phase F.3
--
-- Extiende `audit_log` (creada en 001) con los campos que el AuditMiddleware
-- ya calcula pero no persistía en SQLite:
--   - request_id     correlación BFF↔gateway↔ELK (echoed en X-Request-Id)
--   - duration_ms    latencia del endpoint
--   - audit_source   discriminador para queries multi-emisor (kafka-dashboard-bff)
--   - original_uri   URI completa del gateway (cubre limitación L2: BFF ve la
--                    ruta original, no /oauth2/auth)
--
-- SQLite NO soporta IF NOT EXISTS en ALTER TABLE; el runner se basa en
-- `_schema_version` para evitar re-aplicación. Si manualmente se intenta
-- re-ejecutar, fallará con "duplicate column" (síntoma esperado).

ALTER TABLE audit_log ADD COLUMN request_id   TEXT;
ALTER TABLE audit_log ADD COLUMN duration_ms  INTEGER;
ALTER TABLE audit_log ADD COLUMN audit_source TEXT NOT NULL DEFAULT 'kafka-dashboard-bff';
ALTER TABLE audit_log ADD COLUMN original_uri TEXT;

CREATE INDEX IF NOT EXISTS idx_audit_request_id ON audit_log(request_id);
CREATE INDEX IF NOT EXISTS idx_audit_source     ON audit_log(audit_source);
