# Kafka Dashboard — Tasks

> Versión: 0.1.0 · Estado: Draft · Última actualización: 2026-05-10
>
> Plan de implementación. Cada fase tiene **entregables verificables** y **criterio de cierre**. No se cierra una fase sin smoke test pasando + spec actualizado.
>
> Este sub-stack se integra al BackOffice (ya implementado, commit `cc8554c`). NO crea sitio nuevo, NO crea login, NO crea roles. Reusa todo y añade tarjeta + ruta `/kafka/`.

---

## 0. Pre-flight checklist

Antes de empezar **cualquier** fase:

- [ ] BackOffice MVP healthy (`make backoffice-up && make backoffice-status` muestra todos los servicios verde).
- [ ] Kafka stack healthy (`docker ps | grep kafka` muestra kafka1/2/3 + schema-registry up).
- [ ] ELK stack healthy (`backoffice-audit-*` index existe en Kibana).
- [ ] Specs aprobadas: `CONSTITUTION-addendum.md` v0.1.0, `requirements.md` v0.1.0, `design.md` v0.1.0.

---

## Fase A · Andamiaje (compose include + scaffolding) — **DONE** ✅

**Cierre:** 2026-05-10. Los 7 smoke tests A.1–A.7 pasan. A.8 (no-regresión) verde. Sin re-trabajos en specs.

**Objetivo**: levantar `kafka-dashboard-fe` y `kafka-dashboard-bff` vacíos pero accesibles vía `/kafka/` desde el BackOffice, con SSO heredado funcionando. **Sin** lógica de Kafka todavía.

### A.1 — Sub-compose con include desde BackOffice

- [ ] **A.1.1** Crear `backoffice/dashboards/kafka-dashboard/docker-compose.yml` con:
  - Servicios `kafka-dashboard-fe` (nginx alpine, sirve `frontend/`) y `kafka-dashboard-bff` (placeholder Python con `/api/health` que devuelve `{"status":"ok"}`)
  - Healthchecks + memory limits según design §10
  - Volume named `kafka-dashboard-data`
  - Networks: `lg-infra-backoffice-net` (external) + `lg-infra-kafka_lg-infra-kafka-net` (external, sólo BFF)
- [ ] **A.1.2** Modificar `backoffice/docker-compose.yml` añadiendo bloque `include:` apuntando a `dashboards/kafka-dashboard/docker-compose.yml` (Compose v2.20+, ver design §11).
- [ ] **A.1.3** Crear `backoffice/dashboards/kafka-dashboard/.env.example` con vars del design §9.1.
- [ ] **A.1.4** Verificar `make backoffice-up` levanta los 2 servicios nuevos sin tocar los demás.

**Criterio de cierre**:
- `docker compose -f backoffice/docker-compose.yml ps` muestra `kafka-dashboard-fe` y `kafka-dashboard-bff` healthy.
- Reiniciar el BackOffice (`make backoffice-down && make backoffice-up`) sigue funcionando.

### A.2 — Bloques nginx en gateway

- [ ] **A.2.1** Añadir a `backoffice/home/nginx.conf`:
  - `location /kafka/` → proxy a `kafka-dashboard-fe`
  - `location /kafka/api/` → proxy a `kafka-dashboard-bff`
  - `location = /kafka/api/health { auth_request off; ... }` (override sin auth)
- [ ] **A.2.2** Implementar authz por método/path. **Primer intento con `if`** (design §5.1). Si falla la lógica de combinación, refactorizar a `map` siguiendo patrón BackOffice §13.3 design.
- [ ] **A.2.3** Recargar gateway (`docker compose restart gateway`) y verificar.

**Criterio de cierre**:
- Como `lglabsadmin`, `GET /kafka/` devuelve la home estática (200).
- Como `lglabsviewer`, `POST /kafka/api/topics` devuelve 403 antes de tocar el BFF.
- `GET /kafka/api/health` (sin login) devuelve 200.

### A.3 — Tarjeta en home del BackOffice

- [ ] **A.3.1** Modificar `backoffice/home/index.html` añadiendo tarjeta "Kafka Dashboard" según design §5.2.
- [ ] **A.3.2** Visibilidad: los 4 roles la ven (la authz fina está aguas abajo).

**Criterio de cierre**:
- Login en `http://localhost:8080` con cualquier rol → tarjeta visible → click → llega a `/kafka/` sin re-login.

### A.4 — Smoke tests Fase A

- [ ] **A.4.1** Crear `backoffice/dashboards/kafka-dashboard/specs/smoke-tests.md` con sección "Fase A".
- [ ] **A.4.2** Ejecutar manualmente con los 4 usuarios de prueba; documentar output esperado.

**Cobertura mínima Fase A**:
- Tarjeta visible en home para los 4 roles.
- `/kafka/` sirve placeholder estático con SSO.
- `/kafka/api/health` accesible sin auth.
- `POST /kafka/api/topics` devuelve 403 para support/viewer (sin BFF, lo bloquea el gateway).

**Cierre Fase A**: tasks.md → A marcado [DONE], requirements.md sin cambios, design.md actualizado si la authz nginx tuvo que cambiar de `if` a `map`.

---

## Fase B · BFF — Topics CRUD (US-1, US-2, US-3, US-4)

**Objetivo**: BFF funcional con todos los endpoints de topics, validaciones, audit, SQLite.

### B.1 — BFF skeleton FastAPI

- [x] **B.1.1** `bff/Dockerfile` (Python 3.12-slim, multi-stage si reduce tamaño).
- [x] **B.1.2** `bff/requirements.txt`: `fastapi[standard]==0.115.*`, `kafka-python==2.0.*`, `httpx`, `sqlmodel`, `pydantic-settings`, `pyyaml`.
- [x] **B.1.3** Estructura `bff/app/` según design §2.3.
- [x] **B.1.4** `app/main.py` con FastAPI factory, OpenAPI en `/api/openapi.json`.
- [x] **B.1.5** `app/deps.py`: dep que extrae `X-Auth-Request-User` y `X-Auth-Request-Groups`, expone `current_user` y `current_groups`.
- [x] **B.1.6** `app/settings.py`: vars del design §9.3, validación al arrancar.

### B.2 — owners.yaml loader

- [x] **B.2.1** `app/owners.py`: carga + valida YAML al arrancar (fail-fast si malformado).
- [x] **B.2.2** Endpoint interno `GET /api/_owners` que lista los owners (lo usa el frontend para el dropdown).
- [x] **B.2.3** Crear `bff/config/owners.yaml` con 3-4 owners de ejemplo (ver requirements §7.2).

### B.3 — SQLite migrations

- [x] **B.3.1** `app/repos/migrations/001_initial.sql` con DDL design §4.1.
- [x] **B.3.2** Runner idempotente al arrancar (lee `_schema_version`).
- [x] **B.3.3** Verificar que el volume `kafka-dashboard-data` persiste tras restart.

### B.4 — Kafka repo

- [x] **B.4.1** `app/repos/kafka_repo.py`: wrapper sobre `KafkaAdminClient`.
- [x] **B.4.2** Métodos: `list_topics`, `describe_topic`, `create_topic`, `alter_configs`, `create_partitions`, `delete_topic`.
- [x] **B.4.3** Mapeo de exceptions a HTTP según design §7.3 — implementado como decorador o middleware.
- [x] **B.4.4** Reintentos con backoff para `KafkaTimeoutError` / `NoBrokersAvailable`.

### B.5 — Endpoints topics

- [x] **B.5.1** `app/routers/topics.py` con 6 endpoints (design §3.3).
- [x] **B.5.2** Validaciones server-side completas (regex `lglabs.*`, owner ∈ YAML, RF ≤ brokers, etc.).
- [x] **B.5.3** Header `X-Confirm-Resource` en DELETE.
- [x] **B.5.4** Audit logger (stdout JSON) en cada mutación.
- [x] **B.5.5** `app/routers/summary.py` con `GET /api/summary` (US-8).
- [x] **B.5.6** `app/routers/export.py` con `GET /api/topics/{name}/export`.

### B.6 — Tests de contrato

- [x] **B.6.1** `bff/tests/contract/test_topics.py`: matriz role × endpoint × status (design §6).
- [x] **B.6.2** Cubre AC-1.1..AC-4.5 (de US-1 a US-4) y AC-9.1.
- [ ] **B.6.3** Run en CI (añadir job a `.github/workflows/test-dotfiles.yml`).

### B.7 — Smoke tests Fase B

- [x] **B.7.1** Añadir sección "Fase B" a `smoke-tests.md` propio.
- [x] **B.7.2** Crear topic `lglabs.smoke.test`, listar, editar retención, borrar con confirmación. Como `lglabsadmin` y `lglabsoperator`.
- [x] **B.7.3** Verificar 403s correctos para `lglabssupport` y `lglabsviewer`.
- [ ] **B.7.4** Verificar entrada en `backoffice-audit-*` con `audit_source: kafka-dashboard-bff`.

**Cierre Fase B**: 
- US-1, US-2, US-3, US-4, US-8, US-9 marcadas como "Implemented" en `requirements.md`.
- Trazabilidad inversa en `requirements.md §8` y `design.md §12` actualizadas.

---

## Fase C · Frontend — Topics UI (US-1, US-2, US-3, US-4, US-8)

**Objetivo**: UI Alpine.js consumiendo los endpoints de Fase B. Sin schemas ni ACLs todavía.

> **Decisión de fase ratificada en SDD**: Single-page app con hash router (`#/`, `#/topics`, `#/topics/<name>`) en un solo `index.html`. Tailwind 3.4 JIT (browser build) + Alpine 3.14 vendorados, sin paso de build. Scope: Topics. Schemas y ACL-metadata se incorporan en Fases D y E.

### C.1 — Assets base

- [x] **C.1.1** `frontend/assets/alpine.min.js` (vendored 3.14.1, no CDN para offline).
- [x] **C.1.2** `frontend/assets/tailwind.min.js` (vendored 3.4.16 JIT browser build — preferido sobre `.css` por permitir clases dinámicas sin build).
- [x] **C.1.3** `frontend/assets/app.js`: `window.kd` con `call()` (fetch wrapper que parsea envelope `{error, message, details}`), `humanizeError()` (mapea 17 códigos de design §7.2 a mensajes en español), `toast()`, hash router (`parseHash`/`navigate`), `fmt.ms`/`fmt.date`.

### C.2 — Páginas

- [x] **C.2.1** `frontend/index.html` view `home`: summary cards desde `GET /api/summary` y composición.
- [x] **C.2.2** `frontend/index.html` view `topics`: lista paginada + filtro client-side + botón "Crear" (oculto via `x-show="user.is_writer"`).
- [x] **C.2.3** Modal "Crear topic" con form validado client-side (regex `^lglabs\.[a-z0-9._-]+$` prefilled, dropdown owners desde `GET /api/_owners`, descripción ≥10 chars).
- [x] **C.2.4** `frontend/index.html` view `topic-detail`: metadatos + configs + particiones + modal `Editar` + modal `Borrar` con confirmación por nombre exacto (envía header `X-Confirm-Resource`).
- [x] **C.2.5** Botón `Exportar JSON` (US-9): descarga `<nombre>.json` via `Blob` + `URL.createObjectURL`.
- [x] **C.2.6** Badge de salud en top bar (verde/amarillo/rojo según `/api/health`); refresca cada 30s. (No banner full-width: el badge cumple la función con menor ruido visual.)

### C.3 — UX de errores

- [x] **C.3.1** Tabla `error code → mensaje localizado` en español (mapa `humanizeError` en `app.js`, 17 entradas alineadas con design §7.2).
- [x] **C.3.2** Toast notifications para éxito/error (top-right, autohide 5s, función global `kd.toast()`).

### C.4 — Smoke tests Fase C

- [x] **C.4.1** Smoke automatizado `bff/tests/scripts/smoke-c.sh` (C.1–C.6 en `specs/smoke-tests.md`): assets, endpoints, matriz de roles, confirmación destructiva, regresión BackOffice — todo PASS.
- [x] **C.4.2** Matriz role × método verificada vía API (gateway): `support`/`viewer` reciben 403 en POST/DELETE/EXPORT; admin/operator reciben 201/204/200. La SPA usa `x-show="user.is_writer"` para ocultar los botones (consistente con la enforcement del gateway+BFF).
- [x] **C.4.3** Confirmación destructiva end-to-end: BFF devuelve 409 sin/con header `X-Confirm-Resource` incorrecto, 204 al confirmar; la SPA exige escribir el nombre exacto antes de habilitar el botón "Borrar".

> **Pendiente de operación manual** (no bloquea cierre de fase, queda como checklist en `specs/smoke-tests.md` §C.7): recorrido visual de la SPA en navegador con cada uno de los 4 usuarios para validar UX (modales, toasts, descarga del JSON).

**Cierre Fase C**: User puede gestionar topics 100% desde la UI sin tocar AKHQ ni CLI.

---

## Fase D · Schemas (US-5, US-6, C-S)

**Objetivo**: gestión de schemas vía Schema Registry, proxy fino sin reescritura.

### D.1 — Registry repo

- [x] **D.1.1** `app/repos/registry_repo.py`: cliente HTTP con httpx contra `SCHEMA_REGISTRY_URL`.
- [x] **D.1.2** Métodos: `list_subjects`, `get_versions`, `get_version`, `register_schema`, `set_compatibility`.
- [x] **D.1.3** Re-emisión transparente del 409 incompatible (design §A5).

### D.2 — Endpoints schemas

- [x] **D.2.1** `app/routers/schemas.py` con 5 endpoints (design §3.4).
- [x] **D.2.2** `GET /api/schemas/{subject}/export` (US-9 para schemas).

### D.3 — Frontend schemas

- [x] **D.3.1** `frontend/schemas.html`: lista subjects. _(implementado como vista `#/schemas` en SPA, no archivo separado)_
- [x] **D.3.2** `frontend/schema-detail.html`: versiones + diff + form de nueva versión. _(implementado como vista `#/schemas/<subject>` en SPA)_
- [x] **D.3.3** Selector de `compatibility_level` (admin/operator).

### D.4 — Smoke tests Fase D

- [x] **D.4.1** Registrar schema AVRO simple, evolucionar compatible, intentar incompatible (debe fallar limpio con 409).
- [x] **D.4.2** Cambiar compatibility level y verificar.

**Cierre Fase D**: US-5, US-6 implementadas. AKHQ y la nueva UI muestran los mismos subjects.

---

## Fase E · ACL-metadata (US-7, C-A)

**Objetivo**: CRUD de ACL-metadata en SQLite con banner permanente sobre no-enforcement.

### E.1 — ACL repo

- [ ] **E.1.1** `app/repos/acl_metadata_repo.py`: CRUD sobre `acl_metadata` con UNIQUE constraint enforcement.
- [ ] **E.1.2** Validación de `principal` (debe empezar por `User:` o `Group:`), pattern_type, etc.

### E.2 — Endpoints ACL

- [ ] **E.2.1** `app/routers/acl_metadata.py` con 4 endpoints (design §3.5).
- [ ] **E.2.2** Confirmación con `X-Confirm-Resource: <id>` en DELETE.
- [ ] **E.2.3** Authz: solo admin puede mutar (verificable en gateway, redoblado en BFF como defensa en profundidad).

### E.3 — Frontend ACL

- [ ] **E.3.1** `frontend/acl-metadata.html`: lista filtrable + form de creación (admin only).
- [ ] **E.3.2** **Banner permanente** "⚠ ACL-metadata informativas — el cluster no las aplica" (design §A6, AC-7.3).
- [ ] **E.3.3** Botón "Export ACL-as-AdminClient JSON" para futuro path de migración.

### E.4 — Smoke tests Fase E

- [ ] **E.4.1** Como admin: crear, editar, borrar ACL-metadata. Verificar UNIQUE constraint.
- [ ] **E.4.2** Como operator: verificar 403 en POST/PUT/DELETE.
- [ ] **E.4.3** Verificar audit en `backoffice-audit-*`.

**Cierre Fase E**: US-7 implementada.

---

## Fase F · Audit pipeline + integración ELK

**Objetivo**: el BFF deja huella en `backoffice-audit-*` además de oauth2-proxy. Cubre limitación L2 con URI original.

### F.1 — Filebeat input

- [ ] **F.1.1** Añadir input `filestream` a `elk/filebeat.yml` para los logs de `kafka-dashboard-bff` (path: `/var/lib/docker/containers/*/...` filtrado por container name, o un volumen de logs si lo separamos — ver §F.1.3).
- [ ] **F.1.2** Tags: `["kafka-dashboard", "kafka-dashboard-app"]`.
- [ ] **F.1.3** **Decisión a tomar**: ¿logueamos a stdout (filebeat lee de docker logs) o a un volumen compartido (como hace oauth2-proxy)? Recomendado: stdout + filebeat autodiscover por container label, alineado con el resto del stack ELK (ya filebeat lee logs de containers por defecto).

### F.2 — Logstash branch

- [ ] **F.2.1** Añadir condicional en `elk/logstash.conf`:
  ```
  } else if "kafka-dashboard-app" in [tags] {
      elasticsearch {
          ...
          index => "backoffice-audit-%{+YYYY.MM.dd}"
      }
  }
  ```
- [ ] **F.2.2** Restart explícito de logstash (no hot-reload).

### F.3 — Audit logger en BFF

- [ ] **F.3.1** `app/audit.py`: middleware FastAPI que loguea cada request en formato design §8.3.
- [ ] **F.3.2** Sanitización (no body, no valores en diff — design §8.4).
- [ ] **F.3.3** Persistir tabla `audit_log` en SQLite **además** del stdout (cubre L2 con persistencia local).

### F.4 — Verificación E2E

- [ ] **F.4.1** Crear topic como `lglabsoperator` → buscar en Kibana doc con `audit_source: kafka-dashboard-bff`, `path: /kafka/api/topics`, `status: 201`.
- [ ] **F.4.2** Verificar que el `path` es la URI original (no `/oauth2/auth`).

**Cierre Fase F**: limitación L2 documentada como **mitigada** para Kafka Dashboard (no resuelta a nivel global del BackOffice; se queda en backlog para extender el patrón).

---

## Fase G · Documentación + CI

**Objetivo**: usuario operator puede usar el dashboard sin preguntar; PRs futuras tienen smoke check.

### G.1 — User guide propio

- [ ] **G.1.1** Crear `backoffice/dashboards/kafka-dashboard/docs/user-guide.es.md` con:
  - Introducción y vista general
  - Cómo entrar (vía BackOffice)
  - Crear topic (incluyendo convención `lglabs.*` y owners)
  - Editar/borrar topic
  - Gestionar schemas (registrar, evolucionar)
  - Gestionar ACL-metadata + banner explicativo
  - Export JSON
  - Diagramas Mermaid (flujo crear topic, arquitectura del sub-stack)
  - Runbooks K1–K5 (Kafka caído, Registry caído, SQLite corrupto, owners.yaml malformado, restore desde backup)
- [ ] **G.1.2** Versión EN paralela: `user-guide.en.md`.
- [ ] **G.1.3** Linkear desde `backoffice/docs/user-guide.{es,en}.md` (sección "Sub-dashboards").

### G.2 — README del sub-stack

- [ ] **G.2.1** Actualizar `backoffice/dashboards/kafka-dashboard/README.md` con índice final, links a todo, badges de estado.

### G.3 — CI

- [ ] **G.3.1** Añadir job `kafka-dashboard-smoke` a `.github/workflows/test-dotfiles.yml` (opt-in via workflow_dispatch + schedule, igual que `backoffice-smoke`).
- [ ] **G.3.2** El job ejecuta el smoke-tests del kafka-dashboard.

### G.4 — Makefile targets

- [ ] **G.4.1** Añadir a `Makefile` raíz:
  - `kafka-dashboard-up`, `kafka-dashboard-down`, `kafka-dashboard-logs`, `kafka-dashboard-status`
  - `kafka-dashboard-backup` (tar del volume)
  - `kafka-dashboard-restore FILE=...`
- [ ] **G.4.2** Documentar en `Makefile help`.

### G.5 — Root README

- [ ] **G.5.1** Mencionar el Kafka Dashboard en la sección "Start with BackOffice" del root `README.md`.

**Cierre Fase G**: documentación completa, CI verde, MVP del Kafka Dashboard listo para anuncio.

---

## Fase H · SDD retrospective

**Objetivo**: cerrar el ciclo SDD con backlog y trazabilidad inversa.

- [ ] **H.1** Bumpar versiones: `requirements.md` → 0.2.0 "MVP Implemented", `design.md` → 0.2.0 "Reflects implementation", `tasks.md` → 1.0.0 "MVP Completed".
- [ ] **H.2** Crear `backoffice/dashboards/kafka-dashboard/specs/backlog.md` con:
  - **A. Capabilities pospuestas**: producir/consumir mensajes desde UI (delegado a AKHQ), métricas, multi-cluster, Connect.
  - **B. Mejoras técnicas**: ACLs reales (cuando authorizer activo, ver §A6), refactor nginx `if`→`map` si quedó pendiente, cache de cluster metadata si latencia molesta, multi-language i18n.
  - **C. Trazabilidad inversa**: cada US del MVP → fases/tasks que la implementan; cada decisión técnica → archivo donde vive.
- [ ] **H.3** Commit final `feat(kafka-dashboard): add MVP for topic/schema/ACL-metadata management`.

**Cierre Fase H**: ciclo SDD cerrado.

---

## Resumen de fases

| Fase | Entregable | LOC estimado | Dependencias |
|---|---|---|---|
| A | Andamiaje + nginx + tarjeta | ~150 | BackOffice MVP |
| B | BFF topics CRUD + tests | ~800 | A |
| C | Frontend topics + summary | ~600 | B |
| D | Schemas (BFF + UI) | ~400 | B |
| E | ACL-metadata (BFF + UI) | ~350 | B |
| F | Audit pipeline | ~100 | B (al menos un endpoint mutador) |
| G | Docs + CI + Makefile | ~600 (docs) | C, D, E |
| H | Retrospectiva SDD | ~150 | G |

**Total estimado MVP**: ~3.150 LOC (incluyendo tests y docs).

> Las fases B-E pueden hacerse en paralelo entre BFF y FE si hubiera dos personas, pero el orden secuencial recomendado es A → B → C → D → E → F → G → H para mantener cohesión y permitir validación incremental tras cada fase.

---

## Convención de "Definition of Done" por fase

Una fase **no se cierra** sin:

1. Todas sus tareas marcadas `[x]`.
2. Smoke test correspondiente pasando manualmente con los 4 usuarios.
3. Spec actualizado si la implementación reveló algo (raro pero posible).
4. Sin regresiones en el BackOffice MVP (ejecutar `backoffice-smoke` también).
5. Commit dedicado a la fase con mensaje `feat(kafka-dashboard): phase X — <título>`.
