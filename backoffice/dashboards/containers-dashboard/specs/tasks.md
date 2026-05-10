# Containers Dashboard — Tasks

> Versión: 0.1.0 · Estado: Approved · Última actualización: 2026-05-10
>
> Plan de implementación. Cada fase tiene **entregables verificables** y **criterio de cierre**. No se cierra una fase sin smoke test pasando + spec actualizado.
>
> Este sub-stack se integra al BackOffice (ya implementado) como segundo dashboard, hermano de `kafka-dashboard`. NO crea sitio nuevo, NO crea login, NO crea roles. Reusa todo y añade tarjeta + ruta `/containers/`.
>
> **Convive con Portainer existente** (`/portainer/`) — no lo reemplaza.

---

## 0. Pre-flight checklist

Antes de empezar **cualquier** fase:

- [ ] BackOffice MVP healthy (`docker ps` muestra gateway, oauth2-proxy, keycloak, home, portainer up).
- [ ] Kafka Dashboard MVP healthy (referencia para reutilizar patrones de audit + nginx).
- [ ] ELK stack healthy (`backoffice-audit-*` index existe en Kibana, audit_source contiene `oauth2-proxy` y `kafka-dashboard-bff`).
- [ ] Specs aprobadas: `CONSTITUTION-addendum.md` v0.1.0, `requirements.md` v0.1.0, `design.md` v0.1.0.
- [ ] `/var/run/docker.sock` accesible desde el host (lo está, el Portainer existente lo usa).

---

## Fase A · Andamiaje (compose include + scaffolding)

**Objetivo**: levantar `containers-dashboard-fe` y `containers-dashboard-bff` vacíos pero accesibles vía `/containers/` desde el BackOffice, con SSO heredado funcionando. **Sin** lógica Docker todavía.

### A.1 — Sub-compose con include desde BackOffice

- [x] **A.1.1** Crear `backoffice/dashboards/containers-dashboard/docker-compose.yml`:
  - `containers-dashboard-fe`: nginx alpine sirviendo `frontend/`.
  - `containers-dashboard-bff`: build local (Dockerfile placeholder), expone `/api/health` con `{"status":"ok"}`.
  - Mount `/var/run/docker.sock:/var/run/docker.sock:rw` en BFF.
  - Mount `backoffice-audit-logs:/var/log/backoffice:rw` en BFF (volumen ya existente, compartido con kafka-dashboard).
  - Volume named `containers-dashboard-data` para SQLite.
  - Healthchecks + memory limits según design §10.
  - Networks: `lg-backoffice` (external).
- [x] **A.1.2** Modificar `backoffice/docker-compose.yml` añadiendo entrada al bloque `include:` apuntando a `dashboards/containers-dashboard/docker-compose.yml`.
- [x] **A.1.3** Crear `.env.example` con vars del design §9.1.
- [x] **A.1.4** Verificar `docker compose -f backoffice/docker-compose.yml up -d` levanta los 2 nuevos servicios sin tocar los demás.

**Criterio de cierre**: `docker ps` muestra `lg-infra-backoffice-containers-dashboard-fe` y `lg-infra-backoffice-containers-dashboard-bff` healthy.

### A.2 — Bloques nginx en gateway

- [x] **A.2.1** Añadir a `backoffice/home/nginx.conf` los upstreams + 3 locations (frontend, exec WS, API REST/SSE) según design §5.1.
- [x] **A.2.2** Implementar authz por método/path. **Empezar con `if`**; si la lógica de combinación falla, refactorizar a `map` (mismo patrón resuelto en kafka-dashboard, ver tasks Fase A.2.2 de kafka). DELETE → admin only; POST → admin|operator; GET → cualquier autenticado.
- [x] **A.2.3** Recargar gateway (`docker compose restart gateway`).

**Criterio de cierre**:
- Como `lglabsadmin`, `GET /containers/` devuelve la home estática (200).
- Como `lglabsviewer`, `POST /containers/api/containers/abc/restart` devuelve 403 antes de tocar el BFF.
- Como `lglabsoperator`, `DELETE /containers/api/containers/abc` devuelve 403 antes de tocar el BFF.
- `GET /containers/api/health` (sin login) devuelve 200.

### A.3 — Tarjeta en home del BackOffice

- [x] **A.3.1** Modificar `backoffice/home/index.html` añadiendo tarjeta "Containers Dashboard" según design §5.2.
- [x] **A.3.2** Visible para los 4 roles.

**Criterio de cierre**: login como cualquier rol → tarjeta visible → click → llega a `/containers/` sin re-login.

### A.4 — Smoke tests Fase A

- [x] **A.4.1** Crear `specs/smoke-tests.md` con sección "Fase A".
- [x] **A.4.2** Ejecutar manualmente con los 4 usuarios; documentar output esperado.

**Cobertura mínima Fase A**:
- Tarjeta visible para los 4 roles.
- `/containers/` sirve placeholder estático con SSO.
- `/containers/api/health` accesible sin auth.
- Authz nginx funciona para POST/DELETE antes de tocar BFF.

**Cierre Fase A**: tasks marcados [x], requirements sin cambios, design actualizado si la authz nginx tuvo que cambiar a `map`.

---

## Fase B · BFF — Read-only (US-1, US-2, US-3, US-7, US-9)

**Objetivo**: BFF funcional con todos los endpoints de **lectura** (containers list+detail+logs+stats+inspect, summary, images/volumes/networks list). **Sin** mutaciones todavía.

### B.1 — BFF skeleton FastAPI

- [x] **B.1.1** `bff/Dockerfile` (Python 3.12-slim).
- [x] **B.1.2** `bff/requirements.txt`: `fastapi[standard]==0.115.*`, `docker==7.*`, `sqlmodel`, `pydantic-settings`, `websockets`.
- [x] **B.1.3** Estructura `bff/app/` según design §2.3.
- [x] **B.1.4** `app/main.py` con FastAPI factory, OpenAPI en `/api/openapi.json`, lifespan con conexión docker-py.
- [x] **B.1.5** `app/deps.py`: `current_user`, `current_groups`, `require_writer`, `require_admin`.
- [x] **B.1.6** `app/settings.py`: vars del design §9.2.

### B.2 — Docker repo

- [x] **B.2.1** `app/repos/docker_repo.py`: wrapper sobre `docker.from_env()` con timeout configurable.
- [x] **B.2.2** Métodos read-only: `list_containers`, `get_container`, `get_logs`, `stream_stats`, `inspect`, `list_images`, `list_volumes`, `list_networks`.
- [x] **B.2.3** Mapeo de exceptions a HTTP según design §7.3 — decorador o middleware.
- [ ] **B.2.4** Reintento con backoff para `ConnectionError` socket. *(Aplazado a Phase D — actualmente un fallo de socket sale como 503 sin retry, suficiente para MVP read-only.)*

### B.3 — Safety modules

- [x] **B.3.1** `app/safety/denylist.py`: set `DENYLIST` hard-coded (§7.1 requirements) + helpers `is_protected(name)` y `assert_not_protected(name)`.
- [x] **B.3.2** `app/safety/redact.py`: `SECRET_RE` + `redact_env(env_dict)` que devuelve nuevo dict con valores redactados.
- [x] **B.3.3** Tests unitarios para ambos (denylist hits, regex casos edge).

### B.4 — Endpoints read-only

- [x] **B.4.1** `app/routers/health.py` con `GET /api/health` (público).
- [x] **B.4.2** `app/routers/summary.py` con `GET /api/summary` (US-9).
- [x] **B.4.3** `app/routers/containers.py` con: list, detail, logs (paged), inspect.
- [x] **B.4.4** `app/routers/containers.py` SSE: `logs/stream` y `stats` con cancelación on-disconnect.
- [x] **B.4.5** `app/routers/images.py`, `volumes.py`, `networks.py` con `GET` list (US-7).
- [x] **B.4.6** Marcar `is_protected` en `ContainerSummary` consultando denylist.
- [x] **B.4.7** Aplicar `redact_env` en detail/inspect.

### B.5 — SQLite migration

- [x] **B.5.1** `app/repos/migrations/001_initial.sql` con DDL design §4.1 (solo audit_log).
- [x] **B.5.2** Runner idempotente al arrancar (mismo patrón kafka-dashboard).

### B.6 — Tests de contrato

- [ ] **B.6.1** `bff/tests/contract/test_read_only.py`: matriz role × endpoint × status para los GETs. *(Aplazado: smoke manual cubre el matrix; añadir CI test en Phase G.)*
- [ ] **B.6.2** Cubre AC-1.1..AC-1.5, AC-2.1..AC-2.4, AC-7.1..AC-7.4, AC-9.1..AC-9.2. *(Mismo motivo que B.6.1.)*

### B.7 — Smoke tests Fase B

- [x] **B.7.1** Añadir sección "Fase B" a `smoke-tests.md`.
- [x] **B.7.2** Listar containers, ver detalle de uno, descargar logs, abrir SSE stats por 5s.
- [x] **B.7.3** Verificar que un container en denylist sale con `is_protected: true`.
- [x] **B.7.4** Verificar `redact_env` con un container que tenga env `*_PASSWORD`.

**Cierre Fase B**: US-1, US-2, US-3, US-7, US-9 marcadas como "Implemented" en `requirements.md`.

---

## Fase C · Frontend — Read-only SPA (US-1, US-2, US-3, US-7, US-9)

**Objetivo**: SPA Alpine.js consumiendo todos los endpoints de Fase B. Sin botones de mutación todavía (o presentes pero deshabilitados con tooltip "Fase D").

### C.1 — Assets base

- [ ] **C.1.1** `frontend/assets/alpine.min.js` (vendored 3.14.x).
- [ ] **C.1.2** `frontend/assets/tailwind.min.js` (vendored 3.4.x JIT browser).
- [ ] **C.1.3** `frontend/assets/app.js`: `window.cd` con `call()` (fetch wrapper), `humanizeError()` (mapea códigos design §7.2 a ES), `toast()`, hash router, `fmt.bytes`/`fmt.duration`.

### C.2 — Views

- [ ] **C.2.1** `frontend/index.html` con `<x-data="app()">` y todas las views.
- [ ] **C.2.2** View `home`: summary cards desde `/api/summary`. Banner permanente §B3 ("acceso completo al daemon Docker…").
- [ ] **C.2.3** View `containers`: tabla paginada, filtro client-side, badge "🔒 protegido" si `is_protected`, toggle "ocultar parados".
- [ ] **C.2.4** View `container-detail` con 4 tabs: Overview / Logs / Stats / Inspect.
- [ ] **C.2.5** Tab Logs: tail configurable + botón "Tail en vivo" (SSE).
- [ ] **C.2.6** Tab Stats: gauges (CSS) refrescando vía SSE; cancelación on-leave.
- [ ] **C.2.7** Tab Inspect: pretty-print JSON.
- [ ] **C.2.8** Views `images`, `volumes`, `networks`: tablas read-only.
- [ ] **C.2.9** Health badge en top bar (verde/rojo) refrescando cada 30s.

### C.3 — UX de errores

- [ ] **C.3.1** Mapa `humanizeError` con todos los códigos del design §7.2.
- [ ] **C.3.2** Toast notifications (top-right, autohide 5s).

### C.4 — Smoke tests Fase C

- [ ] **C.4.1** Smoke automatizado `bff/tests/scripts/smoke-c.sh`: assets, endpoints read-only end-to-end con los 4 usuarios.
- [ ] **C.4.2** Recorrido manual: navegación entre views funciona, F5 mantiene la view, badge protegido visible para containers de la denylist.

**Cierre Fase C**: usuario puede inspeccionar el host completo desde la UI sin tocar Portainer ni CLI. (Sin mutaciones aún.)

---

## Fase D · BFF Mutations + UI — start/stop/restart (US-4)

**Objetivo**: las 3 mutaciones reversibles más comunes, con denylist + confirmation + audit.

### D.1 — Endpoints mutadores

- [ ] **D.1.1** `app/routers/containers.py` añade `POST /{id}/start`, `/{id}/stop`, `/{id}/restart`.
- [ ] **D.1.2** Dependency `require_writer` (admin|operator).
- [ ] **D.1.3** En cada mutador: inspect → name → `assert_not_protected(name)` → `assert_confirm_resource(req, name)` (excepto start) → docker action.
- [ ] **D.1.4** Manejo de `already_running` / `already_stopped` → 409.
- [ ] **D.1.5** Query `?timeout_seconds=` validado 1..60.

### D.2 — Audit middleware

- [ ] **D.2.1** `app/middleware/audit.py` (copiar patrón de kafka-dashboard, adaptar `audit_source` y schema).
- [ ] **D.2.2** Persiste en SQLite (`audit_repo`) **y** loguea en logger `containers_dashboard.audit` (rotating file).
- [ ] **D.2.3** Sanitización: NO body, NO headers sensibles, sólo identificadores.
- [ ] **D.2.4** Captura `request_id` de header `X-Request-Id` o genera UUID v4.

### D.3 — UI mutators

- [ ] **D.3.1** En `container-detail` y `containers` list: botones Start/Stop/Restart.
- [ ] **D.3.2** Botones ocultos si `!user.is_writer` (operator+admin).
- [ ] **D.3.3** Botones deshabilitados con tooltip "🔒 protegido" si `is_protected`.
- [ ] **D.3.4** Modal de confirmación: requiere escribir el nombre exacto antes de habilitar el botón "Confirmar".
- [ ] **D.3.5** Toast de éxito/error con humanizeError.
- [ ] **D.3.6** Tras éxito, refresh del state del container (poll /api/containers/{id} hasta que cambie state, máx 5s).

### D.4 — Smoke tests Fase D

- [ ] **D.4.1** Como `lglabsoperator`: stop+start+restart en un container NO protegido (ej. `metricbeat01` o un container de test). Verificar audit en SQLite y en `backoffice-audit-*` (Kibana).
- [ ] **D.4.2** Como `lglabsoperator`: intentar stop sobre `lg-infra-backoffice-keycloak` → 423 Locked.
- [ ] **D.4.3** Como `lglabsoperator`: stop sin `X-Confirm-Resource` → 409 confirmation_required.
- [ ] **D.4.4** Como `lglabssupport`/`lglabsviewer`: cualquier POST → 403 (gateway).

**Cierre Fase D**: US-4 implementada. Audit pipeline E2E funcionando para mutaciones simples.

---

## Fase E · Exec shell (US-5)

**Objetivo**: terminal interactiva para admin con xterm.js + WebSocket + idle timeout + audit reforzado.

### E.1 — BFF WebSocket exec

- [ ] **E.1.1** `app/routers/exec.py` con `WS /api/containers/{id}/exec?shell=`.
- [ ] **E.1.2** Dependency `require_admin` (defense in depth).
- [ ] **E.1.3** Validar `shell ∈ {sh, bash, ash}`.
- [ ] **E.1.4** `assert_not_protected(name)` antes de abrir exec.
- [ ] **E.1.5** Crear exec con docker-py: `client.api.exec_create(id, cmd=[shell], tty=True, stdin=True)` + `exec_start(detach=False, tty=True, stream=True, demux=False, socket=True)`.
- [ ] **E.1.6** Loop async: `asyncio.gather(ws→sock, sock→ws)` con `asyncio.wait_for` para idle timeout 5min.
- [ ] **E.1.7** Frame JSON `{"resize": {"cols", "rows"}}` → `client.api.exec_resize`.
- [ ] **E.1.8** Audit `exec_open` al iniciar; `exec_close` al cerrar (con `duration_ms`, `exit_code` de `exec_inspect`, `close_reason`).
- [ ] **E.1.9** NO loguear bytes del stream.

### E.2 — Frontend xterm.js

- [ ] **E.2.1** `frontend/assets/xterm.js`, `xterm.css`, `xterm-addon-fit.js` vendored.
- [ ] **E.2.2** View `container-exec`: full-height terminal, selector shell, botón "Cerrar".
- [ ] **E.2.3** Botón "Exec" en `container-detail` (solo admin, no en denylist).
- [ ] **E.2.4** Resize handler envía `{"resize":{cols,rows}}`.
- [ ] **E.2.5** Banner "🛑 Sesión exec activa — cerrarás conexión al salir de esta vista".

### E.3 — Smoke tests Fase E

- [ ] **E.3.1** Como `lglabsadmin`: abrir exec en un container running NO protegido, ejecutar `id; pwd; exit` — verificar audit_open + audit_close en SQLite/ELK.
- [ ] **E.3.2** Como `lglabsoperator`: WS upgrade → 403 (gateway).
- [ ] **E.3.3** Como `lglabsadmin`: exec sobre container en denylist → 423.
- [ ] **E.3.4** Idle timeout: dejar sesión inactiva 5min → cierre con close_reason=idle_timeout.
- [ ] **E.3.5** Verificar que el contenido del stream NO aparece en logs (grep absurdo).

**Cierre Fase E**: US-5 implementada. Exec sessions auditadas + protegidas.

---

## Fase F · Remove (US-6, US-8)

**Objetivo**: DELETE de container/image/volume/network, admin only, con denylist + confirmation + protección builtin networks.

### F.1 — BFF DELETE endpoints

- [ ] **F.1.1** `app/routers/containers.py` añade `DELETE /{id}`.
- [ ] **F.1.2** `app/routers/images.py` añade `DELETE /{id}`.
- [ ] **F.1.3** `app/routers/volumes.py` añade `DELETE /{name}`.
- [ ] **F.1.4** `app/routers/networks.py` añade `DELETE /{id}`.
- [ ] **F.1.5** Todos con `require_admin`.
- [ ] **F.1.6** Container DELETE: denylist → confirmation → check running (sin force) → docker rm.
- [ ] **F.1.7** Image DELETE: confirmation → check `containers_using > 0` (sin force) → docker rmi.
- [ ] **F.1.8** Volume DELETE: confirmation → check montado → docker volume rm. Sin `force`.
- [ ] **F.1.9** Network DELETE: confirmation → check builtin (`bridge|host|none` → 403) → check `containers_attached > 0` → docker network rm.

### F.2 — UI Remove

- [ ] **F.2.1** Botón "Remove" en cada lista (visible solo admin, deshabilitado si protected/in_use).
- [ ] **F.2.2** Modal confirmación con input que exige escribir el nombre/repo:tag/id_short exacto.
- [ ] **F.2.3** Para container: checkbox `force` (si running). Para image: checkbox `force` + `prune_children`. Volume/network: sin checkboxes.

### F.3 — Smoke tests Fase F

- [ ] **F.3.1** Como `lglabsadmin`: crear container test (`docker run -d --name cd-smoke alpine sleep 60`), borrar via UI, verificar 204 + audit.
- [ ] **F.3.2** Container running sin force → 409 container_running.
- [ ] **F.3.3** Image en uso sin force → 409 image_in_use.
- [ ] **F.3.4** Volume montado → 409 volume_in_use.
- [ ] **F.3.5** Network `bridge` → 403 builtin_network_protected.
- [ ] **F.3.6** Como `lglabsoperator`: DELETE → 403 (gateway).
- [ ] **F.3.7** Como `lglabsadmin`: DELETE container en denylist → 423 protected_resource.

**Cierre Fase F**: US-6 + US-8 implementadas.

---

## Fase G · Audit pipeline E2E + integración ELK

**Objetivo**: el BFF deja huella en `backoffice-audit-*` con `audit_source: containers-dashboard-bff`. Mismo patrón que kafka-dashboard Fase F.

### G.1 — Filebeat input

- [ ] **G.1.1** Añadir input `filestream` en `elk/filebeat.yml` con id `containers-dashboard-app`, path `/var/log/backoffice/containers-dashboard-app*.log`, tag `containers-dashboard-app`, `fingerprint.length: 64`.
- [ ] **G.1.2** Restringir el input pre-existente de kafka-dashboard a su path específico (ya está) — verificar que el nuevo no se solape.

### G.2 — Logstash branch

- [ ] **G.2.1** Añadir rama condicional en `elk/logstash.conf`: `else if "containers-dashboard-app" in [tags] { ... index => "backoffice-audit-%{+YYYY.MM.dd}" ... }`. Mismo índice; discriminación vía `audit_source`.
- [ ] **G.2.2** Restart logstash01 (sin hot-reload).

### G.3 — Verificación E2E

- [ ] **G.3.1** Smoke `bff/tests/scripts/smoke-g.sh` (~10 casos): mount + filebeat input + logstash branch + 50 requests con `X-Request-Id` distinto + verificación en fichero/SQLite/ES + no-regresión kafka-dashboard + no-regresión oauth2-proxy.
- [ ] **G.3.2** Verificar `original_uri = /containers/api/...` (no `/oauth2/auth`).

**Cierre Fase G**: limitación L2 mitigada para Containers Dashboard también.

---

## Fase H · Documentación + CI + retrospective

### H.1 — User guide propio

- [ ] **H.1.1** `backoffice/dashboards/containers-dashboard/docs/user-guide.es.md` con estructura 2-partes (usuario + operador), diagramas Mermaid (sequence SSO + arch sub-stack + audit pipeline), runbooks, tabla de errores, tabla de limitaciones. Incluir sección "Cuándo usar Containers Dashboard vs Portainer".
- [ ] **H.1.2** Versión EN paralela `user-guide.en.md`.

### H.2 — README del sub-stack

- [ ] **H.2.1** `backoffice/dashboards/containers-dashboard/README.md` siguiendo convención BackOffice (Quickstart + creds + arquitectura ASCII + tabla roles + smoke recipes + warning sobre docker.sock).

### H.3 — CI

- [ ] **H.3.1** Añadir job `containers-dashboard-smoke` a `.github/workflows/test-dotfiles.yml` (workflow_dispatch + schedule, mismo patrón que kafka-dashboard-smoke).
- [ ] **H.3.2** Job ejecuta `smoke-c.sh` + `smoke-g.sh`; dump logs ante fallo; cleanup al final.

### H.4 — Root README

- [ ] **H.4.1** Bloque `## [Start with Containers Dashboard][containers-dashboard-doc]` en root `README.md`, debajo del de Kafka Dashboard.

### H.5 — Bumpear versiones de specs

- [ ] **H.5.1** `requirements.md` 0.2.0 "MVP Implemented", `design.md` 0.2.0 "Reflects implementation", `tasks.md` 1.0.0 "MVP Completed".

### H.6 — Backlog + trazabilidad inversa

- [ ] **H.6.1** `specs/backlog.md` con: A. Capabilities pospuestas (compose stacks, pull/push, build, multi-host, métricas históricas), B. Tech debt, C. Trazabilidad US→fases→commits, D. Decisiones→file map, E. Snapshot final.
- [ ] **H.6.2** Commit final `feat(containers-dashboard): phase H — SDD retrospective + backlog`.

**Cierre Fase H**: ciclo SDD cerrado.

---

## Resumen de fases

| Fase | Entregable | LOC estimado | Dependencias |
|---|---|---|---|
| A | Andamiaje + nginx + tarjeta | ~150 | BackOffice MVP |
| B | BFF read-only + safety + tests | ~900 | A |
| C | Frontend SPA read-only | ~700 | B |
| D | BFF mutations + UI start/stop/restart | ~400 | B |
| E | Exec shell (BFF + xterm.js) | ~500 | D |
| F | Remove (BFF + UI) | ~400 | D |
| G | Audit pipeline E2E | ~150 | D (al menos un mutador) |
| H | Docs + CI + retrospective | ~700 (docs) | C, D, E, F, G |

**Total estimado MVP**: ~3.900 LOC (tests + docs).

> Las fases B-C pueden hacerse parcialmente en paralelo entre BFF y FE. D-E-F deben ser secuenciales para validar audit pipeline y compartir dependencias UI.

---

## Convención de "Definition of Done" por fase

Una fase **no se cierra** sin:

1. Todas sus tareas marcadas `[x]`.
2. Smoke test correspondiente pasando con los 4 usuarios.
3. Spec actualizado si la implementación reveló algo (raro pero posible).
4. Sin regresiones en BackOffice MVP ni Kafka Dashboard MVP (smoke-c.sh + smoke-f.sh de kafka).
5. Commit dedicado a la fase con mensaje `feat(containers-dashboard): phase X — <título>` y autor `lglabs <105936384+lglabs@users.noreply.github.com>`.
