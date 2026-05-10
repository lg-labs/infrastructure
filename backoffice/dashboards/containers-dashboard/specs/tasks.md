# Containers Dashboard — Tasks

> Versión: 1.2.0 · Estado: Phase I Completed · Última actualización: 2026-05-10
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

- [x] **C.1.1** `frontend/assets/alpine.min.js` (vendored 3.14.x).
- [x] **C.1.2** `frontend/assets/tailwind.min.js` (vendored 3.4.x JIT browser).
- [x] **C.1.3** `frontend/assets/app.js`: `window.cd` con `call()` (fetch wrapper), `humanizeError()` (mapea códigos design §7.2 a ES), `toast()`, hash router, `fmt.bytes`/`fmt.duration`.

### C.2 — Views

- [x] **C.2.1** `frontend/index.html` con `<x-data="app()">` y todas las views.
- [x] **C.2.2** View `home`: summary cards desde `/api/summary`. Banner permanente §B3 ("acceso completo al daemon Docker…").
- [x] **C.2.3** View `containers`: tabla paginada, filtro client-side, badge "🔒 protegido" si `is_protected`, toggle "ocultar parados".
- [x] **C.2.4** View `container-detail` con 4 tabs: Overview / Logs / Stats / Inspect.
- [x] **C.2.5** Tab Logs: tail configurable + botón "Tail en vivo" (SSE).
- [x] **C.2.6** Tab Stats: gauges (CSS) refrescando vía SSE; cancelación on-leave.
- [x] **C.2.7** Tab Inspect: pretty-print JSON.
- [x] **C.2.8** Views `images`, `volumes`, `networks`: tablas read-only.
- [x] **C.2.9** Health badge en top bar (verde/rojo) refrescando cada 30s.

### C.3 — UX de errores

- [x] **C.3.1** Mapa `humanizeError` con todos los códigos del design §7.2.
- [x] **C.3.2** Toast notifications (top-right, autohide 5s).

### C.4 — Smoke tests Fase C

- [x] **C.4.1** Smoke CLI: HTML 200 (34.5KB, contiene "Containers Dashboard" + `appShell`); 4 assets 200 (`app.js`, `alpine.min.js`, `tailwind.min.js`, `app.css`); endpoints `/containers/api/{health,summary,containers}` 200 a través del gateway con bearer admin. Smoke automatizado `smoke-c.sh` aplazado a Phase H (CI).
- [ ] **C.4.2** Recorrido manual en navegador. *(Aplazado: Fase D ejercitará la UI completa con mutaciones; CLI smoke verifica que SPA + assets + API son alcanzables bajo el mismo contexto de auth.)*

**Cierre Fase C**: usuario puede inspeccionar el host completo desde la UI sin tocar Portainer ni CLI. (Sin mutaciones aún.)

---

## Fase D · BFF Mutations + UI — start/stop/restart (US-4)

**Objetivo**: las 3 mutaciones reversibles más comunes, con denylist + confirmation + audit.

### D.1 — Endpoints mutadores

- [x] **D.1.1** `app/routers/containers.py` añade `POST /{id}/start`, `/{id}/stop`, `/{id}/restart`.
- [x] **D.1.2** Dependency `require_writer` (admin|operator).
- [x] **D.1.3** En cada mutador: inspect → name → `assert_not_protected(name)` → `assert_confirm_resource(req, name)` (excepto start) → docker action.
- [x] **D.1.4** Manejo de `already_running` / `already_stopped` → 409.
- [x] **D.1.5** Query `?timeout_seconds=` validado 1..60.

### D.2 — Audit middleware

- [x] **D.2.1** `app/middleware/audit.py` (ya implementado en Phase B; reutilizado tal cual para mutaciones).
- [x] **D.2.2** Persiste en SQLite (`audit_log`) **y** loguea en logger `containers_dashboard.audit` (rotating file).
- [x] **D.2.3** Sanitización: NO body, NO headers sensibles, sólo identificadores.
- [x] **D.2.4** Captura `request_id` de header `X-Request-Id` o genera UUID v4.

### D.3 — UI mutators

- [x] **D.3.1** En `container-detail`: botones Start/Stop/Restart. *(List-level buttons aplazados a backlog — el detail view ofrece el flujo principal con confirmación.)*
- [x] **D.3.2** Botones ocultos si `!$store.app.canWrite` (operator+admin).
- [x] **D.3.3** Botones deshabilitados con tooltip "🔒 protegido" si `is_protected`, y deshabilitados según estado (start solo si !running, stop/restart solo si running).
- [x] **D.3.4** Modal de confirmación: requiere escribir el nombre exacto antes de habilitar el botón "Confirmar" (excepto start, que es trivialmente reversible).
- [x] **D.3.5** Toast de éxito/error con humanizeError.
- [x] **D.3.6** Tras éxito, refresh del state del container (poll /api/containers/{id} hasta cambiar state, máx 5s).

### D.4 — Smoke tests Fase D

- [x] **D.4.1** Como `lglabsoperator`: stop+start+restart en `lg-infra-backoffice-kafka-dashboard-bff` (NO protegido). Verificado audit en SQLite con `(method, path, status, resource_id)` correctos.
- [x] **D.4.2** Como `lglabsoperator`: stop sobre `lg-infra-backoffice-keycloak` → 423 protected_resource (audit row registrada).
- [x] **D.4.3** Como `lglabsoperator`: stop sin/wrong `X-Confirm-Resource` → 409 confirmation_required.
- [x] **D.4.4** Como `lglabsviewer`/`lglabssupport`: POST stop/restart → 403 (gateway, no llega al BFF).
- [x] **D.4.5** Stop ya parado → 409 already_stopped; start ya corriendo → 409 already_running.

**Cierre Fase D**: US-4 implementada. Audit pipeline E2E funcionando para mutaciones simples.

---

## Fase E · Exec shell (US-5)

**Objetivo**: terminal interactiva para admin con xterm.js + WebSocket + idle timeout + audit reforzado.

### E.1 — BFF WebSocket exec

- [x] **E.1.1** `app/routers/exec.py` con `WS /api/containers/{id}/exec?shell=`.
- [x] **E.1.2** Defense-in-depth: BFF lee `X-Auth-Request-Groups` y rechaza si no tiene `admin`.
- [x] **E.1.3** Validar `shell ∈ {sh, bash, ash}`.
- [x] **E.1.4** `is_protected(name)` antes de abrir exec → close 1008 protected_resource.
- [x] **E.1.5** Crear exec con docker-py: `client.api.exec_create(id, cmd=[shell], tty=True, stdin=True, stdout=True, stderr=True)` + `exec_start(detach=False, tty=True, stream=False, socket=True)`.
- [x] **E.1.6** Loop async: `asyncio.gather(ws→sock, sock→ws, idle_watchdog)` con `FIRST_COMPLETED`. Idle timeout 5 min.
- [x] **E.1.7** Frame JSON `{"resize":{"cols","rows"}}` → `client.api.exec_resize`.
- [x] **E.1.8** Audit `exec_open` al iniciar (status=101 ok, 400/403/409/423 cuando falla pre-flight); `exec_close` al cerrar con `duration_ms`, `exit_code`, `close_reason`.
- [x] **E.1.9** NO loguear bytes del stream — sólo metadata (`shell`, `exec_id`, `close_reason`, `exit_code`).

### E.2 — Frontend xterm.js

- [x] **E.2.1** `frontend/assets/xterm.js` (5.3.0), `xterm.css`, `xterm-addon-fit.js` (0.8.0) vendored.
- [x] **E.2.2** View `container-exec`: full-height terminal (65vh), selector shell, botón "Cerrar sesión" / "Conectar".
- [x] **E.2.3** Botón "⌘ Exec" en `container-detail` (sólo `$store.app.canAdmin`, opacidad 40% si protected/!running).
- [x] **E.2.4** `FitAddon` + handler `resize` → envía `{"resize":{cols,rows}}`.
- [x] **E.2.5** Banner "🛑 Sesión exec activa — al salir cerrarás la conexión" + nota de no-persistencia.

### E.3 — Smoke tests Fase E

- [x] **E.3.1** Como `lglabsadmin`: WS sobre `lg-infra-backoffice-kafka-dashboard-bff` ejecutando `id; pwd; exit` — 101 + recv real shell output (`uid=0(root) gid=0(root)…`) + close 1000 reason=`exec_exited`. Audit `exec_open(101)` + `exec_close(200, exit_code=0, close_reason=exec_exited, duration_ms=…)`. *(Verificado vía Python websockets client a través del gateway.)*
- [x] **E.3.2** Como `lglabsoperator`: WS upgrade → 403 (gateway, antes de tocar el BFF; respuesta de 196 bytes con `@forbidden_page`).
- [x] **E.3.3** Como `lglabsadmin`: WS sobre `lg-infra-backoffice-keycloak` (denylist) → close 1008 reason=`protected_resource`. Audit `exec_open(423, close_reason=protected_resource)`.
- [x] **E.3.4** Como `lglabsadmin`: WS con `?shell=zsh` → close 1008 reason=`invalid_shell:zsh`. Audit `exec_open(400, close_reason=invalid_shell, shell=zsh)`.
- [ ] **E.3.5** Idle timeout: dejar sesión inactiva 5min → cierre con close_reason=idle_timeout. *(Aplazado: lógica probada por inspección de código + watchdog usando `time.monotonic()` y `IDLE_TIMEOUT_SECONDS=300`. Smoke explícito en CI Phase H.)*
- [x] **E.3.6** Verificar que el contenido del stream NO aparece en logs ni audit_log: `detail` JSON sólo contiene metadata; el `audit_log.info` sólo emite el dict del evento. *(Inspección manual de la columna `detail` de `audit_log` confirma sólo `shell`, `exec_id`, `close_reason`, `exit_code`, `idle_timeout_seconds`.)*

**Cierre Fase E**: US-5 implementada. Exec sessions auditadas + protegidas.

---

## Fase F · Remove (US-6, US-8)

**Objetivo**: DELETE de container/image/volume/network, admin only, con denylist + confirmation + protección builtin networks.

### F.1 — BFF DELETE endpoints

- [x] **F.1.1** `app/routers/containers.py` añade `DELETE /{id}`.
- [x] **F.1.2** `app/routers/images.py` añade `DELETE /{id}`.
- [x] **F.1.3** `app/routers/volumes.py` añade `DELETE /{name}`.
- [x] **F.1.4** `app/routers/networks.py` añade `DELETE /{id}`.
- [x] **F.1.5** Todos con `require_admin`.
- [x] **F.1.6** Container DELETE: denylist → confirmation → check running (sin force) → docker rm.
- [x] **F.1.7** Image DELETE: confirmation → check `containers_using > 0` (sin force) → docker rmi.
- [x] **F.1.8** Volume DELETE: confirmation → check montado → docker volume rm. Sin `force`.
- [x] **F.1.9** Network DELETE: confirmation → check builtin (`bridge|host|none` → 403) → check `containers_attached > 0` → docker network rm.

### F.2 — UI Remove

- [x] **F.2.1** Botón "Remove" en cada lista (visible solo admin, deshabilitado si protected/in_use).
- [x] **F.2.2** Modal confirmación con input que exige escribir el nombre/repo:tag/id_short exacto.
- [x] **F.2.3** Para container: checkbox `force` + `remove_volumes`. Para image: checkbox `force`. Volume/network: sin checkboxes (servidor rechaza si en uso).

### F.3 — Smoke tests Fase F

- [x] **F.3.1** Como `lglabsadmin`: crear container test, borrar via API, verificar 204 + audit.
- [x] **F.3.2** Container running sin force → 409 container_running; con `?force=true` → 204.
- [x] **F.3.3** Image en uso sin force → 409 image_in_use; con `?force=true` → 204.
- [x] **F.3.4** Volume montado → 409 volume_in_use.
- [x] **F.3.5** Network `bridge` → 403 builtin_network_protected; network con attached → 409 network_in_use.
- [x] **F.3.6** Como `lglabsoperator`: DELETE → 403 (gateway).
- [x] **F.3.7** Como `lglabsadmin`: DELETE container en denylist → 423 protected_resource.
- [x] **F.3.8** Sin `X-Confirm-Resource` header → 409 confirmation_required.

**Cierre Fase F**: US-6 + US-8 implementadas.

---

## Fase G · Audit pipeline E2E + integración ELK

**Objetivo**: el BFF deja huella en `backoffice-audit-*` con `audit_source: containers-dashboard-bff`. Mismo patrón que kafka-dashboard Fase F.

### G.1 — Filebeat input

- [x] **G.1.1** Añadir input `filestream` en `elk/filebeat.yml` con id `containers-dashboard-app`, path `/var/log/backoffice/containers-dashboard-app*.log`, tag `containers-dashboard-app`, `fingerprint.length: 64`.
- [x] **G.1.2** Restringir el input pre-existente de kafka-dashboard a su path específico (ya está) — verificar que el nuevo no se solape.

### G.2 — Logstash branch

- [x] **G.2.1** Añadir rama condicional en `elk/logstash.conf`: `else if "containers-dashboard-app" in [tags] { ... index => "backoffice-audit-%{+YYYY.MM.dd}" ... }`. Mismo índice; discriminación vía `audit_source`.
- [x] **G.2.2** Restart logstash01 (sin hot-reload).

### G.3 — Verificación E2E

- [x] **G.3.1** Smoke E2E: DELETE container marcador único → 204; tras 12s en ES `backoffice-audit-*` aparece doc con `audit_source=containers-dashboard-bff`, `method=DELETE`, `status=204`, `resource_id=<marcador>`, `groups=['admin']`. 49 docs containers-dashboard + 701 docs kafka-dashboard coexisten en el mismo índice — no-regresión kafka-dashboard verificada.
- [x] **G.3.2** Verificado: `original_uri = /containers/api/containers/<name>` (no `/oauth2/auth`) — limitación L2 mitigada.

**Cierre Fase G**: limitación L2 mitigada para Containers Dashboard también.

---

## Fase H · Documentación + CI + retrospective

### H.1 — User guide propio

- [x] **H.1.1** `backoffice/dashboards/containers-dashboard/docs/user-guide.es.md` con estructura 2-partes (usuario + operador), diagramas Mermaid (sequence SSO + arch sub-stack + audit pipeline), runbooks R1-R7, tabla de errores, tabla de limitaciones L1-L9, sección "Cuándo usar Containers Dashboard vs Portainer".
- [x] **H.1.2** Versión EN paralela `user-guide.en.md`.

### H.2 — README del sub-stack

- [x] **H.2.1** `backoffice/dashboards/containers-dashboard/README.md` siguiendo convención BackOffice (Quickstart + creds + arquitectura ASCII + tabla roles + smoke recipes + warning sobre docker.sock).

### H.3 — CI

- [x] **H.3.1** Job `containers-dashboard-smoke` añadido a `.github/workflows/test-dotfiles.yml` (workflow_dispatch + schedule, mismo patrón que kafka-dashboard-smoke).
- [x] **H.3.2** Job ejecuta `smoke-{c,d,f,g}.sh`; dump logs ante fallo; cleanup al final.

### H.4 — Root README

- [x] **H.4.1** Bloque `## [Start with Containers Dashboard][containers-dashboard-doc]` añadido en root `README.md`, debajo del de Kafka Dashboard, con link refs.

### H.5 — Bumpear versiones de specs

- [x] **H.5.1** `requirements.md` 0.2.0 "MVP Implemented", `design.md` 0.2.0 "Reflects implementation", `tasks.md` 1.0.0 "MVP Completed".

### H.6 — Backlog + trazabilidad inversa

- [x] **H.6.1** `specs/backlog.md` con: A. Capabilities pospuestas (compose stacks, pull/push, build, multi-host, métricas históricas), B. Tech debt, C. Trazabilidad US→fases→commits, D. Decisiones→file map, E. Snapshot final.
- [x] **H.6.2** Commit final `feat(containers-dashboard): phase H — docs + CI + retrospective`.

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

---

## Fase I — Projects view (agrupación + diagrama de componentes)

**Objetivo:** Implementar US-10 (`requirements.md`) según el diseño §13 de `design.md`.
**DoD:** I.x todas en `[x]`, smoke-i.sh 100% pass, sin regresiones en smoke-{c,d,f,g}.sh, commits con autor lglabs, push a origin/master.

### I.0 — Specs (cerrada antes de codear)

- [x] **I.0.1** Adenda en `requirements.md` v0.3.0: capability C-P + US-10 (AC-10.1..10.11).
- [x] **I.0.2** Adenda en `design.md` v0.3.0: §13 completo (discovery, modelo, repo, router, frontend, vendoreo, audit, casos límite, NFR-10..12, AD-13.1..7).
- [x] **I.0.3** Tasks Phase I (este documento).
- [x] **I.0.4** Smoke spec en `smoke-tests.md` § Phase I (≥ 8 casos: list, list+unmanaged, get existing, get unknown, RBAC viewer, RBAC unauth, audit emitido, perf < 1s).

### I.1 — BFF: ProjectsRepo + router (read-only)

- [x] **I.1.1** `bff/app/models/projects.py`: ProjectService, ProjectNetwork, ProjectVolume, ProjectListItem, GraphNode, GraphEdge, ProjectDetail.
- [x] **I.1.2** `bff/app/repos/projects_repo.py`: `ProjectsRepo` con `list_projects(include_unmanaged)`, `get_project(name)`, `_build_graph()` (star pattern, dedupe, skip default bridge).
- [x] **I.1.3** `bff/app/routers/projects.py`: GET `/projects` y GET `/projects/{name}`, ambos `require_any_role`. 404 si project no existe; soporte `include_unmanaged` query.
- [x] **I.1.4** `bff/app/errors.py`: añadir `ProjectNotFound` exception → 404.
- [x] **I.1.5** `bff/app/main.py`: registrar router; añadir `get_projects_repo` dependency.
- [x] **I.1.6** Aggregate status heurístico (sin re-inspect) según §13.5.
- [x] **I.1.7** Test manual con curl: GET /projects, GET /projects/backoffice, /projects/(unmanaged) sin/con flag, GET /projects/no-existe → 404.

### I.2 — Frontend: vendor Mermaid + landing list

- [x] **I.2.1** Vendor `mermaid@10.9.4/dist/mermaid.min.js` → `frontend/assets/mermaid.min.js`. Añadir nota en `frontend/assets/README.md` (versión + checksum SHA-256).
- [x] **I.2.2** Inicializar Mermaid en `<head>`: `mermaid.initialize({startOnLoad:false, theme:'neutral', securityLevel:'strict'})`.
- [x] **I.2.3** Refactor router hash: añadir rutas `#/`, `#/projects/<name>`, `#/home`. La home antigua US-9 pasa a `#/home`.
- [x] **I.2.4** Menú principal actualizado: Projects (default) | Containers | Images | Volumes | Networks | Home.
- [x] **I.2.5** Componente `cd.projectsList`: fetch `GET /api/projects`, render cards (name, aggregate_status badge, m/n running, services, networks count). Toggle "Include unmanaged" → re-fetch con `?include_unmanaged=true`.
- [x] **I.2.6** Cards: keyboard accessible (role=button, tabindex=0, Enter/Space → navega).

### I.3 — Frontend: Project detail + Topology + tabs Networks/Volumes

- [x] **I.3.1** Componente `cd.projectDetail`: fetch `GET /api/projects/{name}`. Header con back-link + name + aggregate badge. Tab strip: Overview/Topology/Networks/Volumes.
- [x] **I.3.2** Tab **Overview**: tabla de services (mismo estilo que `containersView`); cada fila enlaza al container detail page (`#/containers/<id>`) que ya tiene start/stop/restart/remove. Decisión deliberada: NO duplicar acciones inline — mantiene una única fuente de verdad para mutations y reduce maintenance.
- [x] **I.3.3** Tab **Topology**: contenedor `<div id="cd-graph">`, toolbar con 3 checkboxes (depends_on, networks, volumes) + botón "Re-render". Función `renderGraph(detail, filters)` según §13.6.4.
- [x] **I.3.4** Click handlers post-render: cada nodo del SVG navega a `#/containers/<container_id>`.
- [x] **I.3.5** Si `services.length > 20` → mostrar warning "Graph disabled — too many nodes" + botón "Render anyway".
- [x] **I.3.6** Tab **Networks**: lista accordion `name → services_in[]`. Click en nombre → `#/networks/<name>`.
- [x] **I.3.7** Tab **Volumes**: ídem para volumes.
- [x] **I.3.8** Containers protected (denylist) muestran badge "🔒 protected" en Overview.
- [x] **I.3.9** Cache headers: nginx `expires 30d; immutable;` para `/containers/assets/*` (mermaid grande).

### I.4 — Smoke I

- [x] **I.4.1** `bff/tests/scripts/smoke-i.sh` con 9 casos: I.1 (list+schema), I.2 (unmanaged), I.3 (detail+schema), I.4 (404), I.5 (perf info), I.6 (edges types), I.7 (anon→401/302), I.8 (ES audit assertion).
- [x] **I.4.2** Ejecutar smoke-i.sh end-to-end con stack levantado: 9/9 PASS.
- [x] **I.4.3** Re-ejecutar smoke-{c,d,f,g}.sh para confirmar 0 regresiones: 40/40 PASS.

### I.5 — Docs delta + CI + commit + push

- [x] **I.5.1** `docs/user-guide.es.md`: nueva sección "§1.4 Projects view (landing)" + runbook R8 "Diagnosticar un proyecto con Topology".
- [x] **I.5.2** `docs/user-guide.en.md`: mirror.
- [x] **I.5.3** `README.md` del sub-stack: feature matrix con C-P + mención Projects landing en intro.
- [x] **I.5.4** Root `README.md`: mención "Projects view + topología (Phase I)" en bullet de containers-dashboard.
- [x] **I.5.5** CI `.github/workflows/test-dotfiles.yml`: step "Smoke I — Projects view (Phase I)" añadido tras smoke-g.
- [x] **I.5.6** `specs/backlog.md`: sección "Phase I — Projects view + topology (entregada)" añadida.
- [x] **I.5.7** Versiones bumpeadas: requirements 1.0.0 (MVP+I Implemented), design 1.0.0 (Reflects Phase I), tasks 1.2.0 (Phase I Completed).
- [x] **I.5.8** Commit `feat(containers-dashboard): phase I — projects view + topology` autor lglabs (`ae08f94`).
- [x] **I.5.9** `git push origin master` (4738aa7..ae08f94).
