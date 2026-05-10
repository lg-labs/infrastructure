# Kafka Dashboard — Backlog & SDD Retrospective

> Versión: 1.0.0 · Estado: MVP Closed · Última actualización: 2026-05-10
>
> Cierre del ciclo SDD del MVP del Kafka Dashboard. Captura **lo que NO entró**, **mejoras técnicas pendientes**, y **trazabilidad inversa** US ↔ fases/commits.

---

## A. Capabilities pospuestas (out-of-scope MVP)

> Funcionalidades conscientemente excluidas del MVP. Cada item indica el motivo y el disparador esperado para retomarlo.

| # | Capability | Motivo de exclusión | Disparador para retomar |
|---|---|---|---|
| **A1** | **Producir / consumir mensajes desde la UI** | Delegado a AKHQ (`/akhq/`) que ya está integrado en BackOffice. Replicarlo sería duplicar capacidad sin valor incremental. Mantener el dashboard **declarativo**. | Que AKHQ deje de mantenerse o que necesidad de browse/replay tenga requisitos específicos (filtros por owner, redacción de PII) que AKHQ no cubra. |
| **A2** | **Métricas (lag de consumer groups, throughput, etc.)** | Fuera del scope declarativo. Existen herramientas dedicadas (Burrow, JMX→Prom→Grafana). | Demanda repetida de "ver lag desde la misma UI" + Prometheus/Grafana no integrados aún en BackOffice. |
| **A3** | **Multi-cluster** | El MVP asume un único cluster Kafka (el de `lg-labs`). Multi-tenancy aumenta complejidad de auth y de export. | Que `lg-labs` añada un segundo cluster (staging vs prod) y se necesite gestionar ambos desde la misma UI. |
| **A4** | **Kafka Connect (connectors, status, restart)** | Connect tiene su propia API + UI (Connect UI, AKHQ ya muestra connectors). | Que se monte Connect en `lg-labs` sin UI satisfactoria. |
| **A5** | **kSQL / ksqlDB streams catalog** | Igual que A4: ámbito propio, herramientas dedicadas. | Adopción interna de ksqlDB. |
| **A6** | **Owners gestionados desde la UI (CRUD `owners.yaml`)** | Decisión §requirements US-1 — owners son catálogo controlado, cambian vía PR para auditabilidad. | Demanda real de owners frecuentes (más de 1/mes) que sature el flujo de PR. |
| **A7** | **Browse mensajes individuales en SQLite (audit_log)** | El audit log se consulta desde Kibana (`backoffice-audit-*`); replicarlo en la UI duplica funcionalidad. | Necesidad de auditoría sin Kibana disponible. |

---

## B. Mejoras técnicas pendientes (technical debt)

> Items técnicos identificados durante implementación que NO bloquean el MVP pero merecen atención en futuras iteraciones.

### B1. ACLs reales en el cluster (resolver Limitación L1)

**Estado actual**: ACL-metadata son anotaciones SQLite, banner permanente en UI lo deja claro.

**Trabajo**:
- Habilitar `KafkaAuthorizer` (o `StandardAuthorizer` con KRaft) en los brokers.
- Dual-write desde el BFF: `acl_metadata` table + `AdminClient.create_acls()`.
- Modo migración: import desde `kafka-acls --list` → SQLite (snapshot inicial).
- UI: cambiar banner de "anotación" a "anotación + enforcement activo"; añadir columna "synced".
- Reconciliación periódica: tarea en BFF que compare SQLite vs cluster y reporte drift.

**Disparador**: decisión organizativa de activar autenticación SASL/SCRAM o mTLS en brokers.

### B2. Refactor nginx `if` → `map` en gateway (RBAC)

**Estado actual**: `backoffice/home/nginx.conf` usa `if ($http_x_auth_request_groups !~ ...)` para enforcement por ruta.

**Riesgo**: nginx oficialmente desaconseja `if` en `location` ([if is evil](https://www.nginx.com/resources/wiki/start/topics/depth/ifisevil/)). Funciona pero penaliza mantenibilidad.

**Trabajo**:
- Promover a `map $http_x_auth_request_groups $is_admin { ... }` global.
- Probar con todos los smokes (B7, C, F) y los del BackOffice.

**Disparador**: cualquier nuevo dashboard que añada otra capa de RBAC en el gateway (ya seríamos 3+ usos del patrón).

### B3. Cache de cluster metadata en BFF

**Estado actual**: cada `GET /api/topics` invoca `AdminClient.list_topics()` + `describe_configs()`. Para 50+ topics y SQLite + ES en el camino, no es problema. Para 500+ podría serlo.

**Trabajo**:
- TTL cache (60s) sobre cluster metadata.
- Invalidación selectiva en POST/PATCH/DELETE de topics.
- Métrica de cache hit ratio en `/api/health`.

**Disparador**: latencia de `/api/topics` > 1s sostenido o cluster con 200+ topics.

### B4. i18n del frontend

**Estado actual**: textos en castellano hardcoded (`index.html`, `assets/app.js`). Docs ES/EN sí están bien separadas.

**Trabajo**:
- Extraer strings a `assets/i18n/{es,en}.json`.
- Detector simple: `<html lang>` + cookie de preferencia.
- BFF emite `Content-Language` apropiado en exports.

**Disparador**: cualquier usuario non-ES en el equipo de `lg-labs` (hoy 0).

### B5. Promover `request_id`, `audit_source`, `original_uri` a `keyword` en ES

**Estado actual**: dynamic mapping → `text` con sub-field `.keyword`. Filtros exactos requieren `.keyword`; búsquedas tipo "todos los `phase-f-*`" requieren `match_phrase_prefix`, no `prefix`.

**Trabajo**:
- Añadir/actualizar index template `backoffice-audit-*` con mappings explícitos.
- Reindex (o esperar a rolling).
- Documentar en `elk/README.md`.

**Disparador**: queries en Kibana que requieran filtrado por estos campos como facets (panel discoverable).

### B6. Audit middleware reutilizable para próximos dashboards

**Estado actual**: el middleware vive en `bff/app/middleware/audit.py`, específico del Kafka Dashboard. Sería trivial hacerlo paquete pip-installable interno.

**Trabajo**:
- Extraer a `backoffice/shared/python/audit-middleware/` con `pyproject.toml`.
- Parametrizar `audit_source`, `db_path`, `log_path`.
- Cada dashboard nuevo `pip install -e ../shared/...`.

**Disparador**: segundo sub-dashboard con FastAPI (ya documentado en backlog del BackOffice).

### B7. Pytest dentro del container (CI local)

**Estado actual**: pytest no está en la imagen runtime; para correr unit tests dentro del container hay que `pip install pytest pytest-asyncio` + `docker cp` (patrón ad-hoc). Los smoke tests (`bash scripts/smoke-*.sh`) sí están listos para CI.

**Trabajo**:
- Añadir target `test` multi-stage al Dockerfile (con pytest en stage `test`, no incluido en `runtime`).
- Job `kafka-dashboard-unit` en GH Actions opcional.

**Disparador**: PRs frecuentes que rompan unit tests sin tocar smokes (hoy 0).

---

## C. Trazabilidad inversa

### C.1 — User Stories ↔ Fases ↔ Commits

> Cada User Story del MVP enlaza con la(s) fase(s) que la implementan y el commit de cierre. Permite auditar "¿quién implementó US-X y cuándo?".

| US | Título | Fases | Commit principal |
|---|---|---|---|
| US-1 | Listar topics del cluster (C-T) | A, B, C | `dd40df0` (A), `896a6f9` (B), `7305679` (C) |
| US-2 | Crear topic (C-T) | B (BFF) + C (UI) | `896a6f9`, `7305679` |
| US-3 | Editar configuración de topic (C-T) | B + C | `896a6f9`, `7305679` |
| US-4 | Borrar topic con confirmación explícita (C-T) | B + C | `896a6f9`, `7305679` |
| US-5 | Listar y ver schemas (C-S) | D | `9c38aad` |
| US-6 | Registrar y evolucionar schemas (C-S) | D | `9c38aad` |
| US-7 | Gestionar ACL-metadata (C-A) | E | `c9e586e` |
| US-8 | Home del dashboard con resumen (C-H) | A + C (summary endpoint en B) | `dd40df0`, `896a6f9`, `7305679` |
| US-9 | Exportar topic / schema a JSON (C-X) | B (topic + acl_metadata_associated) + D (schemas) | `896a6f9`, `9c38aad` |
| Audit / NFR | Audit log unificado en ELK | F | `0056d3f` |
| Docs / NFR | User guide + CI | G | `a3ed5b6` |
| SDD closure | Retrospective + backlog | H | _este commit_ |

### C.2 — Decisiones técnicas ↔ Archivo donde viven

> Mapa de "¿dónde está documentada la decisión X?" para futuros mantenedores.

| Decisión | Archivo | Sección/línea |
|---|---|---|
| Sub-stack del BackOffice (no nuevo sitio/login/roles) | `specs/CONSTITUTION-addendum.md` | C-1, C-2 |
| Convención `lglabs.<domain>.<entity>` para topics | `specs/requirements.md` | US-2 AC + `bff/app/services/topics.py` regex |
| Owners desde `owners.yaml` (no UI CRUD) | `specs/requirements.md` US-1 + backlog A6 | — |
| ACL-metadata sólo en SQLite (no enforcement) | `specs/design.md` | §A6 + permanent UI banner + backlog B1 |
| Particiones sólo se incrementan | `specs/design.md` | §3.2 (limitación de Kafka) |
| Schema Registry errors emitidos verbatim | `specs/design.md` | §A5 + `bff/app/routers/schemas.py` |
| Audit a `backoffice-audit-*` (mismo índice que oauth2-proxy, discriminado por `audit_source`) | `specs/design.md` §A6 + `elk/logstash.conf` | branch `kafka-dashboard-app` |
| Filebeat fingerprint length=64 (vs default 1024) | `elk/filebeat.yml` | input `kafka-dashboard-app` (Phase F) |
| Audit volume compartido `backoffice-audit-logs` (no autodiscover) | `backoffice/dashboards/kafka-dashboard/docker-compose.yml` | volumes section |
| `original_uri` capturado para resolver L2 (audit traceability) | `bff/app/middleware/audit.py` + `docs/user-guide.{es,en}.md` §2.4 | — |
| `X-Confirm-Resource` requerido en DELETE (topics + ACL-metadata) | `bff/app/dependencies/confirmation.py` | + smoke E.6 |
| RBAC en dos capas (gateway + BFF dependencies) | `backoffice/home/nginx.conf` (gateway) + `bff/app/dependencies/auth.py` | defense-in-depth |
| Sólo `admin` muta ACL-metadata (gateway + BFF) | `backoffice/home/nginx.conf:181` + `bff/app/routers/acl_metadata.py` (`require_admin`) | — |
| No hay `make kafka-dashboard-up` (sub-stack via `include:`) | `specs/tasks.md` G.4 + `docs/user-guide.{es,en}.md` §2.2 | decisión registrada |
| Backup/restore = receta manual (no Makefile target) | `docs/user-guide.{es,en}.md` runbook R5 | — |
| UNIQUE constraint ACL-metadata composite key | `bff/app/repos/migrations/001_init.sql` | — |
| Migraciones idempotentes vía `_schema_version` | `bff/app/repos/migrations/__init__.py` (loader) | — |
| Owners cargados sólo en `lifespan` (cambio = restart) | `bff/app/main.py` lifespan + `docs/user-guide.{es,en}.md` §2.5 (tabla) | — |

---

## D. Cierre del ciclo SDD

### D.1 — Snapshot final

| Métrica | Valor |
|---|---|
| Fases ejecutadas | A, B, C, D, E, F, G, H |
| Commits dedicados | 8 (`dd40df0`, `896a6f9`, `7305679`, `9c38aad`, `c9e586e`, `0056d3f`, `a3ed5b6`, este) |
| Unit tests | 83/83 PASS |
| Smoke tests live | 9/9 (smoke-b7) + 12/12 (smoke-c) + 9/9 (smoke-f) PASS |
| Líneas de código (aprox) | ~3.150 (BFF + FE + tests + docs + specs) |
| Limitaciones documentadas | 5 (L1–L5) — L2 resuelta para Kafka Dashboard |
| Backlog items | 7 capabilities (A1–A7) + 7 mejoras técnicas (B1–B7) |
| Versión specs | requirements 0.2.0, design 0.2.0, tasks 1.0.0, backlog 1.0.0 |

### D.2 — Lecciones aprendidas (para próximos dashboards)

1. **El `include:` de docker-compose es la forma correcta de componer sub-stacks** del BackOffice — evita duplicar variables de entorno y networks; el sub-stack hereda el ciclo de vida del padre. Si el sub-stack tuviera que ser opt-in, mover a un compose file independiente y target Makefile dedicado.
2. **El audit middleware merece extraerse como librería compartida** (B6) — lo descubriremos definitivamente cuando llegue el segundo dashboard. Hoy es prematuro.
3. **`fingerprint.length` de Filebeat es un foot-gun**: el default (1024) bloquea silenciosamente la ingesta cuando el log es pequeño. Usar `length: 64` por defecto en cualquier input nuevo donde el archivo pueda estar vacío al arranque.
4. **Smoke scripts > unit tests para validar integración real**: los 30 smoke cases reales detectaron 3 bugs que los 83 unit tests (con mocks) no veían: (a) `path` vs `original_uri` invertidos, (b) duplicate handling en ACL-metadata, (c) Filebeat fingerprint blocking ingesta.
5. **El SDD spec-anchored es coste/beneficio óptimo aquí**: 4 specs, ~1.500 líneas, permitieron 6 fases de implementación sin retrabajo significativo. Ningún spec se reescribió en mitad del camino — sólo bumps de versión al cierre.
6. **`X-Confirm-Resource` como header > body field** para confirmaciones destructivas: trivial de añadir desde UI, imposible de "olvidar accidentalmente" con un curl mal copiado, fácil de testar en CI sin parsing de JSON.
7. **Defense-in-depth en RBAC paga**: el gateway filtra por header (rápido, fail-fast), el BFF revalida con dependencies (a prueba de gateway mal configurado). 0 incidentes de bypass durante todos los smokes.

### D.3 — Estado final

✅ MVP **closed**.
✅ Documentación **completa** (4 specs + 1 backlog + 2 user guides + 1 README + entrada root README + CI job).
✅ Audit pipeline **end-to-end** funcionando (BFF → file → Filebeat → Logstash → ES, query desde Kibana).
✅ 4 roles funcionando con segregación correcta (admin/operator/support/viewer).
✅ 0 regresiones en BackOffice MVP (smokes B7 + C + F + backoffice-smoke green).

→ Listo para announce a usuarios `lg-labs`.
