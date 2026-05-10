# Containers Dashboard — Backlog & Retrospective

> Versión: 1.0.0 · Estado: MVP Completed · Última actualización: 2026-05-10

Este documento cierra el ciclo SDD del MVP. Captura:

- **A. Capabilities pospuestas** — qué quedó fuera del MVP por diseño.
- **B. Tech debt** — deuda asumida durante implementación.
- **C. Trazabilidad** — User Stories → Fases → Commits.
- **D. Decisiones → File map** — dónde vive cada decisión arquitectónica.
- **E. Snapshot final** — métricas y artefactos.

---

## A. Capabilities pospuestas (post-MVP)

### A1. Compose stacks editor
- **Por qué fuera del MVP**: scope; Portainer ya lo cubre y coexiste en `/portainer/`.
- **Cuando lo necesitemos**: añadir router `/api/stacks/{create,update,delete}` consumiendo `docker compose` CLI o `docker-py` API; UI nueva sección.
- **Esfuerzo estimado**: 3-5 días.

### A2. Image pull / push / tag / build
- **Por qué fuera del MVP**: privilegio adicional sobre registry; flujos asincrónicos largos (pull events) no encajan con request-response simple.
- **Cuando**: integración con registry corporativo + UI con SSE de progreso.
- **Esfuerzo**: 2-3 días pull/push; 5+ días build (requiere mountar buildkit/buildx).

### A3. Multi-host (Docker Swarm / múltiples daemons)
- **Por qué fuera del MVP**: foco en single-host (un VPS por entorno); aporta complejidad enorme (federation, agg de estados).
- **Cuando**: cuando el lab pase a 2+ hosts.
- **Alternativa**: replicar el sub-stack en cada host con su propio audit_source `containers-dashboard-bff@<host>`.

### A4. Métricas históricas (CPU/MEM time-series)
- **Por qué fuera del MVP**: stats SSE actual es live-only; almacenar series temporales requiere cuestionar el sink (Elasticsearch ≠ TSDB ideal).
- **Cuando**: integrar con un Prometheus existente y exportar via cAdvisor/node-exporter; el dashboard mostraría grafanas embedded.
- **Esfuerzo**: 3-4 días si Prometheus ya está; +5 si hay que levantarlo.

### A5. Notificaciones / webhooks ante eventos
- **Por qué fuera del MVP**: nadie lo pidió en US.
- **Cuando**: si operación quiere alertas en Slack ante stop/restart/remove de containers críticos.
- **Esfuerzo**: 1-2 días (extender audit logger).

### A6. Filtro por compose project / labels
- **Por qué fuera del MVP**: la búsqueda por texto en la lista cubre el caso 80%.
- **Cuando**: si la lista crece > 50 containers en producción.
- **Esfuerzo**: 0.5 día (frontend only).

### A7. Bulk actions (stop/restart varios)
- **Por qué fuera del MVP**: confirmación type-the-name no escala bien a multi-selección.
- **Cuando**: caso real de "parar todo el proyecto X".
- **Esfuerzo**: 1 día con confirmation diferente (e.g. type "STOP 5 containers").

### A8. Test contract (B.6 specs)
- **Por qué fuera del MVP**: deferred a Phase H CI; smoke tests cubren el contrato E2E.
- **Cuando**: cuando se quiera bloquear PRs por contrato (no sólo smoke).
- **Esfuerzo**: 2 días con `schemathesis` o tests Pydantic+TestClient.

### A9. Idle-timeout exec configurable per-user
- **Por qué fuera del MVP**: hard-coded a 5min para simplificar.
- **Cuando**: si admin necesita sesiones largas.
- **Esfuerzo**: 0.5 días (env var + UI).

---

## B. Tech debt

| ID | Deuda | Impacto | Plan |
|---|---|---|---|
| TD1 | `_audit_event()` en exec router duplica la lógica del HTTP middleware | Bajo (WS no pasa por middleware HTTP) | Extraer helper `audit.emit(event_dict)` y usar en ambos sitios |
| TD2 | `delete_image` resuelve referencia de forma laxa (acepta repo:tag, short id, full id) | Bajo (server enforces, UI envía un valor) | Documentar en design.md (hecho) |
| TD3 | Frontend `_listView` y `containersView` duplican lógica de modal Remove | Medio (mantenibilidad) | Extraer componente Alpine x-data `cdDeleteModal` |
| TD4 | No hay tests unitarios de routers (sólo del repo) | Medio | Añadir TestClient + mocks de docker-py en CI |
| TD5 | `bff/Dockerfile` no incluye `sqlite3` CLI | Bajo (usamos python3) | Añadir si runbooks lo necesitan |
| TD6 | Bajo bearer-token oauth2-proxy no propaga `X-Auth-Request-User` | Documentado (L3) | Mismo bug que kafka-dashboard; aceptado |
| TD7 | Logs streaming no ofrece "follow + history merged" | Bajo | Combinar tail+stream en un mismo endpoint si UX lo pide |
| TD8 | Sin rate limiting en endpoints | Bajo (RBAC + audit son la primera línea) | Considerar `slowapi` si abusos detectados |

---

## C. Trazabilidad: User Stories → Fases → Commits

| US | Descripción | Fases | Commits |
|---|---|---|---|
| US-1 | List containers (read-only) | A, B, C | 16f06c4, b744ce7, 1193560 |
| US-2 | Container detail + logs + stats + inspect | B, C | b744ce7, 1193560 |
| US-3 | List images / volumes / networks | B, C | b744ce7, 1193560 |
| US-4 | Start / Stop / Restart con confirmación | D | 42103f7 |
| US-5 | Exec shell admin con WS | E | 0534606 |
| US-6 | Remove container (admin) | F | 3303ce2 |
| US-7 | Self-protection vía denylist | A, B, D, F | 16f06c4, b744ce7, 42103f7, 3303ce2 |
| US-8 | Remove image / volume / network (admin) | F | 3303ce2 |
| US-9 | Audit en ELK + SQLite | B (sink) + G (pipeline) | b744ce7, 1abcb82 |

| Fase | Commit | Foco |
|---|---|---|
| 0 | `881a7b8` | SDD specs (constitution-addendum, requirements, design, tasks, smoke-tests) |
| A | `16f06c4` | Scaffolding (sub-compose, FE+BFF skeleton, nginx 4 locations) |
| B | `b744ce7` | BFF read-only (containers/images/volumes/networks/summary, env redaction, SSE stats, audit middleware) |
| C | `1193560` | Frontend SPA (Alpine + Tailwind, hash router, 4 detail tabs, EventSource SSE) |
| D | `42103f7` | Mutations: POST start/stop/restart, X-Confirm-Resource, Phase-D modal |
| E | `0534606` | Exec WS shell (admin), xterm.js + FitAddon, idle-timeout 5min, audit exec_open/exec_close |
| F | `3303ce2` | DELETE matrix (containers/images/volumes/networks), 16/16 smoke, force/remove_volumes flags |
| G | `1abcb82` | Filebeat input + Logstash branch, E2E smoke a ES |
| H | (este commit) | Docs ES/EN, README, CI workflow, root README block, backlog, version bump |

---

## D. Decisiones arquitectónicas → File map

| Decisión | File / Archivo |
|---|---|
| Privilegio `docker.sock:rw` aceptado | `backoffice/dashboards/containers-dashboard/docker-compose.yml` |
| Denylist hard-coded (no config) | `bff/app/safety/denylist.py` |
| Confirmación obligatoria header `X-Confirm-Resource` | `bff/app/safety/confirm.py` |
| Builtin networks protegidas | `bff/app/repos/docker_repo.py:delete_network` |
| Env redaction server-side | `bff/app/repos/docker_repo.py:_redact_env` |
| Roles asimétricos (exec+remove admin only) | `bff/app/deps.py` (require_*) + `home/nginx.conf` (gateway filtro) |
| Audit en SQLite local + NDJSON file | `bff/app/middleware/audit.py` + `bff/app/main.py` (RotatingFileHandler) |
| Audit content de exec NO persistido | `bff/app/routers/exec.py` (sólo `_audit_event` con metadata) |
| Idle timeout exec 5min | `bff/app/routers/exec.py` (`EXEC_IDLE_TIMEOUT_S`) + `settings.py` |
| Mismo índice ES `backoffice-audit-*` | `elk/logstash.conf` (branches) |
| Discriminación via `audit_source` | `bff/app/middleware/audit.py` (campo en NDJSON) |
| Defense-in-depth WS exec (gateway + BFF) | `home/nginx.conf` (regex location admin-only) + `bff/app/routers/exec.py` (X-Auth-Request-Groups check) |
| SSE para logs/stats (no polling) | `bff/app/routers/containers.py` + `home/nginx.conf` (proxy_buffering off) |
| Frontend monolítico Alpine + xterm.js vendored | `frontend/index.html` + `frontend/assets/` |

---

## E. Snapshot final

### Métricas

| Métrica | Valor |
|---|---|
| Fases completadas | 9 (0 + A-H) |
| Commits totales | 9 |
| Smoke scripts | 4 (smoke-c, smoke-d, smoke-f, smoke-g) |
| Casos smoke totales | 40 (12+9+13+6) |
| Smoke run final | 40/40 PASS |
| User Stories implementadas | 9/9 |
| Limitaciones declaradas | 9 (L1-L9) |
| Runbooks operativos | 7 (R1-R7) |
| Specs files | 6 (constitution-addendum, requirements, design, tasks, smoke-tests, backlog) |
| Docs files | 3 (README + user-guide.es + user-guide.en) |
| BFF Python LOC (aprox) | ~1900 |
| Frontend HTML+JS LOC | ~1270 |
| CI jobs añadidos | 1 (`containers-dashboard-smoke`) |

### Artefactos

- **API**: 6 routers (containers, images, volumes, networks, summary, health, exec) bajo `/containers/api/*`
- **WS**: `/containers/api/containers/{ref}/exec` (admin only, 5min idle timeout)
- **SSE**: `/logs/stream` y `/stats` per-container
- **Persistencia**: 1 volumen SQLite (`backoffice-containers-dashboard-data`) con tabla `audit_log`
- **Audit sink dual**: SQLite + NDJSON → ES (`backoffice-audit-*`, `audit_source=containers-dashboard-bff`)
- **Roles**: 4 roles BackOffice, mapping documentado en docs §1.2
- **Container names**: `lg-infra-backoffice-containers-dashboard-{fe,bff}`
- **CI**: workflow_dispatch + schedule, dump logs en fallo, cleanup garantizado

### Coexistencia

- **Portainer** sigue accesible en `/portainer/` — no reemplazado.
- **Kafka Dashboard** comparte índice ES; verificado no-regresión (780 docs kafka-dashboard coexisten en `backoffice-audit-2026.05.10`).

### Próximas iteraciones sugeridas (orden de valor/esfuerzo)

1. **A8** — contract tests automatizados (gating PRs).
2. **A6** — filtros adicionales por compose project (UX rápido).
3. **A1** — compose stacks editor (cubre a Portainer en SSO+audit).
4. **A2** — pull/push imágenes (común en flujos de deploy).
5. Resto según demanda.

---

> _SDD cycle closed for Containers Dashboard MVP._

---

## Phase I — Projects view + topology (entregada)

**Branch / commit:** `feat(containers-dashboard): phase I — projects view + topology`

**Capability**: `C-P` · **User Story**: US-10 · 11 ACs (10.1..10.11) · 9 tareas (I.0..I.5) · 9 smoke cases (I.1..I.8 + I.1.schema).

### Resumen

- **BFF**: nuevo `ProjectsRepo` (descubre projects vía label `com.docker.compose.project`); endpoints read-only `GET /api/projects` (+ `?include_unmanaged=true`) y `GET /api/projects/{name}` (404 si no existe). Star-pattern para co-network/co-volume edges (O(n)). Reusa RBAC (`require_reader`) y audit middleware existentes.
- **Frontend**: Mermaid 10.9.4 vendored (3.3 MB en `frontend/assets/`). Nueva landing `#/` (Projects), tab top-level "Projects". Detalle `#/projects/<name>` con 4 tabs: **Overview** (tabla services), **Topology** (Mermaid con 3 tipos de edges + checkboxes filtro), **Networks** (accordion), **Volumes** (accordion). Click en nodo → detail container. >20 services: warning + "Render anyway".
- **Tests**: smoke-i.sh con 9 casos. 49/49 totales (40 previos + 9 nuevos), 0 regresiones.
- **Docs**: `user-guide.{es,en}.md` §1.4 nuevo + runbook R8. `README.md` (sub-stack y root) actualizan feature matrix con C-P.
- **CI**: `.github/workflows/test-dotfiles.yml` añade step "Smoke I — Projects view".
- **Coexistencia**: Portainer y Kafka Dashboard no afectados (smoke G muestra 845 docs kafka-dashboard intactos).

### Decisiones (AD-13.x, ver design.md §13)

- **AD-13.1**: Star pattern (no clique) para co-edges → escalable.
- **AD-13.2**: Mermaid client-side, sin Node en runtime.
- **AD-13.3**: `(unmanaged)` opt-in.
- **AD-13.4**: `/api/projects/*` read-only; mutaciones reusan routers existentes.
- **AD-13.5**: Projects = landing `#/`; daemon summary movido a `#/home`.
- **AD-13.6**: Aggregate state desde list-level (sin extra inspect) → p95 < 1s.
- **AD-13.7**: `bridge` (default) omitida del grafo.

### Próximas iteraciones sugeridas tras Phase I

1. **Persistir filtros de edges en localStorage** (UX, esfuerzo bajo).
2. **Health checks**: si un service tiene healthcheck configurado, mostrar 🩺 healthy/unhealthy en cards y nodos.
3. **Mini-grafo en card**: thumbnail Mermaid en cada project card (esfuerzo medio).
4. **Drill-down a logs agregados** del proyecto (todos los containers concatenados/intercalados).
