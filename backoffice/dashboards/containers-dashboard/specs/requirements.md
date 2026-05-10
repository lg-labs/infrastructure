# Containers Dashboard — Requirements

> Versión: 0.2.0 · Estado: MVP Implemented · Última actualización: 2026-05-10
>
> Este documento captura **qué** debe hacer el Containers Dashboard. El **cómo** está en `design.md`. Las decisiones inmutables están en `CONSTITUTION-addendum.md` (que hereda `backoffice/CONSTITUTION.md`).
>
> Tracking: cada US tiene ID estable, prioridad MoSCoW y criterios de aceptación verificables (Given/When/Then).

---

## 1. Contexto

El BackOffice de `lg-labs` corre ~16 containers Docker repartidos entre 4 stacks (backoffice, kafka, elk, lab interno). Hoy se gestionan:

- **Portainer CE** (`/portainer/`): UI completa de OSS, pero genérica — no usa nuestro SSO (tiene login propio), no audita en `backoffice-audit-*`, no aplica nuestra matriz de roles, y no tiene "self-protection" sobre containers críticos del propio BackOffice (un admin distraído puede parar el gateway).
- **Docker CLI directo**: requiere acceso al host, sin trazabilidad por usuario.

Falta una **consola integrada al BackOffice** que (a) reuse SSO + 4 roles, (b) audite en `backoffice-audit-*`, (c) proteja containers críticos del BackOffice contra auto-DoS, y (d) ofrezca exec/logs/restart en una experiencia minimalista para el día a día del lab.

> **Coexistencia con Portainer**: Portainer sigue disponible en `/portainer/` para casos avanzados (stacks, templates, registries). Containers Dashboard cubre el 80% del día a día (ver/reiniciar/inspect/logs) con la integración del BackOffice.

## 2. Stakeholders y roles

| Rol | Necesidad principal |
|---|---|
| **admin** | Ver y modificar todo. Exec shell. Remove containers/images/volumes. |
| **operator** | Restart/stop/start containers en su día a día. NO exec, NO remove. |
| **support** | Inspeccionar containers y leer logs para diagnosticar incidentes. NO modifica. |
| **viewer** | Lectura pura para reporting y onboarding. |

Matriz completa en `CONSTITUTION-addendum.md` §B6.

## 3. Capacidades en scope (MVP v0.1)

| ID | Capability | Prioridad |
|---|---|---|
| C-C | Containers: listar, ver, logs, inspect, stats | Must |
| C-O | Containers ops: start/stop/restart | Must |
| C-X | Containers: exec shell (admin only) | Must |
| C-R | Containers: remove (admin only) | Must |
| C-I | Inventario read-only: imágenes, volumes, networks | Must |
| C-IR | Inventario remove: imágenes, volumes, networks (admin only) | Must |
| C-H | Home con resumen del daemon (counts + estado) | Should |

Fuera de scope MVP (ver `backlog.md` cuando se cree):
- Compose stacks (start/down un compose project) → lo cubre Portainer
- Pull/push imágenes
- Build de imágenes
- Edición de variables de entorno o mounts en runtime (requiere recreate)
- Multi-host (Swarm/K8s)
- Métricas históricas (lo cubre Prometheus/Grafana en futuro)

---

## 4. User Stories

### US-1 · Listar containers del host (C-C)

**Como** cualquier usuario autenticado
**quiero** ver la lista de containers del daemon con su estado
**para** entender qué corre y diagnosticar.

**Prioridad:** Must
**Roles:** admin, operator, support, viewer (todos)

**Criterios de aceptación:**

- AC-1.1 · Given un usuario autenticado, when entra a `/containers/`, then ve una tabla con columnas `name`, `image`, `state` (running|exited|paused|created|restarting), `status` (texto Docker, ej. "Up 9 hours (healthy)"), `compose_project` (label `com.docker.compose.project` si existe), `ports`, `created`.
- AC-1.2 · Given más de 50 containers, when carga la lista, then se pagina (50 por página) y se puede filtrar client-side por substring del nombre o image.
- AC-1.3 · Given un container que está en la denylist (ver §B5), when carga la lista, then aparece con un **badge "🔒 protegido"** y los botones de mutación quedan deshabilitados.
- AC-1.4 · Given un usuario `viewer`, when entra a la lista, then no ve botones de "Start/Stop/Restart/Exec/Remove".
- AC-1.5 · Given containers parados (state=exited), when carga la lista, then aparecen — no se ocultan por defecto. Hay toggle "ocultar parados".

### US-2 · Ver detalle + logs en vivo (C-C)

**Como** cualquier usuario autenticado
**quiero** ver inspect + tail de logs de un container
**para** diagnosticar sin SSH al host.

**Prioridad:** Must
**Roles:** todos

**Criterios de aceptación:**

- AC-2.1 · Given un container, when entra a `/containers/<id>/`, then ve metadata (image digest, networks, mounts, env keys -no values-, labels), tail de logs configurable (100/500/2000 líneas, default 500).
- AC-2.2 · Given el detalle abierto, when pulsa "Tail en vivo", then los logs se actualizan vía SSE (Server-Sent Events).
- AC-2.3 · Given pulsa "Inspect raw JSON", then ve el output completo de `docker inspect` formateado.
- AC-2.4 · Env vars cuyo nombre matchea regex `(?i)(password|secret|token|key|credential)` se renderizan como `<redacted>` en cliente y servidor (defensa en profundidad).

### US-3 · Stats en vivo (C-C)

**Como** cualquier usuario autenticado
**quiero** ver CPU/MEM/Network/IO en vivo de un container
**para** detectar picos.

**Prioridad:** Should
**Roles:** todos

**Criterios de aceptación:**

- AC-3.1 · Given el detalle, when abre la pestaña "Stats", then ve gauges de `cpu_percent`, `memory_usage_mb / memory_limit_mb`, `net_rx_kbps`, `net_tx_kbps`, `block_read_mb`, `block_write_mb`. Stream SSE refrescando cada 1s.
- AC-3.2 · Given se cierra la pestaña, then el stream se cancela en cliente y servidor (no leak de cpu en BFF).
- AC-3.3 · Given un container `state != running`, when abre Stats, then la pestaña muestra "Stats no disponibles para containers no-running" sin error.

### US-4 · Start / Stop / Restart (C-O)

**Como** admin u operator
**quiero** controlar el ciclo de vida de containers
**para** restablecer servicios sin SSH.

**Prioridad:** Must
**Roles:** admin, operator

**Criterios de aceptación:**

- AC-4.1 · Given un admin/operator, when pulsa "Restart" en un container, then la UI exige escribir el nombre exacto en un input (mismo patrón que kafka-dashboard delete).
- AC-4.2 · Given confirmación correcta, when envía, then la UI manda `POST /containers/api/containers/<id>/restart` con header `X-Confirm-Resource: <name>`.
- AC-4.3 · Given el header `X-Confirm-Resource` ausente o no coincidente con el container name, when llega al BFF, then responde `409 Conflict` con `{"error":"confirmation_required"}` y NO toca el daemon.
- AC-4.4 · Given el container está en la denylist (§B5), when intenta cualquier mutación, then el BFF responde `423 Locked` con `{"error":"protected_resource", "message":"This container belongs to BackOffice critical infrastructure. Use Portainer or CLI."}`.
- AC-4.5 · Given un usuario `support`/`viewer`, when intenta `POST /containers/api/containers/<id>/{start,stop,restart}`, then nginx responde `403` antes de tocar el BFF.
- AC-4.6 · Given Stop, hay parámetro opcional `?timeout_seconds=N` (default 10, max 60). El BFF lo pasa a `docker stop --time N`.
- AC-4.7 · Given Start NO requiere `X-Confirm-Resource` (no es destructivo).

### US-5 · Exec shell en container (C-X)

**Como** admin
**quiero** abrir una shell interactiva en un container
**para** debugging avanzado sin SSH al host.

**Prioridad:** Must
**Roles:** admin (exclusivo)

**Criterios de aceptación:**

- AC-5.1 · Given un admin, when pulsa "Exec" en un container `state=running` y NO en denylist, then se abre una vista con xterm.js conectado vía WebSocket a `/containers/api/containers/<id>/exec`.
- AC-5.2 · La UI ofrece selector de shell `["sh", "bash", "ash"]` con default `sh` (más portable). Detección automática NO se hace en MVP.
- AC-5.3 · Given un usuario `operator`/`support`/`viewer`, when intenta WS upgrade en `/containers/api/containers/<id>/exec`, then nginx responde `403`.
- AC-5.4 · Given el container está en denylist (§B5), when intenta exec (cualquier rol), then responde `423 Locked`.
- AC-5.5 · Given una sesión exec abierta, when no hay input/output durante 5 minutos, then el BFF cierra el WS con código `1001 going_away` y mensaje "idle timeout".
- AC-5.6 · Audit emite evento `audit_type=exec_open` al iniciar y `audit_type=exec_close` al cerrar (§B7).
- AC-5.7 · El contenido del stream NO se persiste en logs (§B7) — solo metadata de la sesión.

### US-6 · Remove container (C-R)

**Como** admin
**quiero** borrar un container parado
**para** limpiar el host.

**Prioridad:** Must
**Roles:** admin (exclusivo)

**Criterios de aceptación:**

- AC-6.1 · Given un admin, when pulsa "Remove" en un container, then la UI exige escribir el nombre exacto.
- AC-6.2 · Given confirmación correcta, when envía, then la UI manda `DELETE /containers/api/containers/<id>` con header `X-Confirm-Resource: <name>`.
- AC-6.3 · Given el container está running, when intenta DELETE sin `?force=true`, then el BFF responde `409 Conflict` con `{"error":"container_running", "message":"Stop the container first or use force=true"}`.
- AC-6.4 · Given `?force=true`, when envía, then el BFF llama `docker rm -f` (equivalente a stop+rm).
- AC-6.5 · Given el container está en denylist (§B5), when intenta DELETE, then responde `423 Locked` (ANTES de checks de running/force).
- AC-6.6 · Given un usuario non-admin, when intenta DELETE, then nginx responde `403`.

### US-7 · Inventario imágenes/volumes/networks (C-I)

**Como** cualquier usuario autenticado
**quiero** ver imágenes, volúmenes y redes del daemon
**para** entender el inventario.

**Prioridad:** Must
**Roles:** todos

**Criterios de aceptación:**

- AC-7.1 · Given un usuario autenticado, when entra a `/containers/#/images`, then ve tabla con `repository:tag`, `id` (corto), `created`, `size_mb`, `containers_using` (count).
- AC-7.2 · Given un usuario autenticado, when entra a `/containers/#/volumes`, then ve tabla con `name`, `driver`, `mountpoint`, `created`, `containers_using`.
- AC-7.3 · Given un usuario autenticado, when entra a `/containers/#/networks`, then ve tabla con `name`, `driver`, `scope`, `internal`, `containers_attached`.
- AC-7.4 · Listas paginadas + filtro client-side. No hay create/edit en MVP — solo read + remove (US-8).

### US-8 · Remove image / volume / network (C-IR)

**Como** admin
**quiero** borrar imágenes huérfanas, volúmenes sin uso, networks vacías
**para** liberar disco.

**Prioridad:** Must
**Roles:** admin (exclusivo)

**Criterios de aceptación:**

- AC-8.1 · Given un admin, when pulsa "Remove" sobre image/volume/network, then la UI exige confirmación con nombre/id exacto.
- AC-8.2 · Given una image en uso por containers (running o exited), when intenta DELETE sin `?force=true`, then el BFF responde `409 Conflict` con `{"error":"image_in_use"}`.
- AC-8.3 · Given un volume montado por algún container (cualquier estado), when intenta DELETE, then `409 Conflict` con `{"error":"volume_in_use"}`. NO hay `force=true` para volumes (sería destructivo silencioso).
- AC-8.4 · Given una network con containers conectados, when intenta DELETE, then `409 Conflict` con `{"error":"network_in_use"}`.
- AC-8.5 · Given una network builtin (`bridge`, `host`, `none`), when intenta DELETE, then `403 Forbidden` con `{"error":"builtin_network_protected"}` independientemente del rol.
- AC-8.6 · Audit emite evento con `resource_type` ∈ `image|volume|network` y el id/name correspondiente.

### US-9 · Home / Summary del daemon (C-H)

**Como** cualquier usuario autenticado
**quiero** ver un resumen del daemon al entrar
**para** orientarme rápido.

**Prioridad:** Should
**Roles:** todos

**Criterios de aceptación:**

- AC-9.1 · La home `/containers/` muestra: containers totales (con breakdown running/exited/paused), imágenes totales, volumes totales, networks totales, versión del daemon (`docker version`), uso de disco aproximado (suma de sizes de imágenes), y links rápidos a las 4 secciones.
- AC-9.2 · Si el daemon no responde (timeout 5s), la home muestra banner rojo "Docker daemon unavailable" sin tirar el resto de la UI.

---

## 5. Requisitos no funcionales

| ID | Requisito | Métrica |
|---|---|---|
| NFR-1 | Listado de containers responde en < 1.5s para hosts con hasta 100 containers | p95 |
| NFR-2 | Stop/Restart confirma y propaga al daemon en < 3s (sin contar el stop timeout) | p95 |
| NFR-3 | Toda mutación produce un evento en `backoffice-audit-*` en < 10s | p95 |
| NFR-4 | El BFF tolera reinicios del daemon: reintenta socket con backoff y la UI degrada con banner | — |
| NFR-5 | El BFF respeta los memory limits del BackOffice (default `256m`, configurable vía `.env`) | hard limit |
| NFR-6 | La UI funciona sin JS framework de build — sólo Alpine.js + xterm.js servido por nginx | sin Node en runtime |
| NFR-7 | Cero secretos en imagen ni en repo; env values nunca se loguean (NFR cruza con AC-2.4 redaction) | grep `(?i)(password\|secret\|token)` en audit logs = 0 hits |
| NFR-8 | Stats SSE tolera hasta 5 streams concurrentes en el BFF sin pasar de 80% memory limit | observed |
| NFR-9 | Exec WebSocket escala a 3 sesiones admin concurrentes sin degradar latencia (< 100ms p95 ida-vuelta) | observed |

## 6. Out of scope (con razón)

| Item | Razón |
|---|---|
| Crear/editar containers desde UI | Compose + Portainer ya lo hacen mejor; recrear container sin compose pierde la spec |
| Compose stacks (up/down un proyecto) | Lo cubre Portainer; añadir aquí duplica esfuerzo |
| Pull/push imágenes desde registry | Operación lenta, mejor en CI; en lab `docker pull` directo |
| Build de imágenes | Requiere context tarball, fuera de scope UI |
| Editar env / mounts en runtime | Docker no permite hot-edit, requiere recreate (out of scope §previo) |
| Multi-host / Swarm / K8s | YAGNI — un solo host de lab |
| Métricas históricas | Prometheus/Grafana lo harán bien cuando se añadan |
| Grabar contenido de exec sessions | Decisión de seguridad (§B7) — guardar comandos + output sería un compromiso |

## 7. Convenciones del equipo

### 7.1. Denylist hard-coded

La denylist (§B5) NO es configurable vía YAML ni env. Vive en `app/safety/denylist.py` y se modifica vía PR. Razón:

- Cambiarla via env es un foot-gun: alguien podría sobrescribirla con `[]` en un `.env` local y romper la self-protection.
- Cambiarla vía UI sería peor: el dashboard se "rompería" si se quita su propia entrada.
- Las 6 entradas son nombres exactos de containers; si se renombra alguno, se actualiza la denylist en el mismo PR.

Lista canónica:

```python
DENYLIST = {
    "lg-infra-backoffice-keycloak",
    "lg-infra-backoffice-gateway",
    "lg-infra-backoffice-proxy",
    "lg-infra-backoffice-portainer",
    "lg-infra-backoffice-containers-dashboard-bff",
    "lg-infra-backoffice-containers-dashboard-fe",
}
```

> **NOT** en la denylist: keycloak DB (si existiera), elastic/kibana, kafka brokers, akhq, schema-registry. Razón: son útiles de poder reiniciar; su caída no impide volver al dashboard.

### 7.2. Sin filtro de scope (mostrar todos los containers)

A diferencia de kafka-dashboard (que filtra topics por convención `lglabs.*`), Containers Dashboard muestra **todo** lo que el daemon reporta. Razón:

- Un dashboard de containers que oculte cosas confunde más de lo que ayuda.
- La denylist (§7.1) cubre el riesgo principal: protección contra mutaciones.
- Si en el futuro se quiere filtrar (ej. por label `lglabs.environment=lab`), se añade en backlog como query param opcional `?scope=lglabs`.

### 7.3. Env vars sensibles redacted

Cualquier env var cuyo **nombre** matchea `(?i)(password|secret|token|key|credential)` se devuelve como `"<redacted>"` desde el BFF. La regex es server-side; el cliente NO recibe el valor real. Razón: defensa en profundidad — aunque el role tenga acceso al inspect, no debe ver secrets accidentalmente expuestos en compose files.

## 8. Trazabilidad inversa

(Se completará cuando exista `tasks.md`. Cada US referenciará las tareas que la implementan; cada tarea referenciará la US que satisface.)
