# Containers Dashboard — Design

> Versión: 0.3.0 · Estado: Phase I (Projects view) approved · Última actualización: 2026-05-10
>
> Este documento define **cómo** se construye el Containers Dashboard. El **qué** está en `requirements.md`. Las decisiones inmutables están en `CONSTITUTION-addendum.md` (que hereda `backoffice/CONSTITUTION.md`).
>
> Cada sección de diseño debe ser verificable: o se mapea a código/config, o se mapea a un test en `smoke-tests.md`.

---

## 1. Arquitectura

### 1.1. Posición en el ecosistema

```mermaid
flowchart LR
    User([Usuario navegador])
    KC[Keycloak<br/>OIDC IdP]
    OP[oauth2-proxy<br/>SSO + roles]
    GW[nginx-gateway<br/>routing + authz]
    HOME[backoffice-home<br/>tarjetas]
    CD_FE[containers-dashboard-fe<br/>nginx + Alpine.js + xterm.js]
    CD_BFF[containers-dashboard-bff<br/>FastAPI + docker-py]
    SOCK[(/var/run/docker.sock)]
    SQLITE[(SQLite volume<br/>containers-dashboard-data)]
    ELK[(ELK<br/>backoffice-audit-*)]

    User -->|HTTPS| GW
    GW -->|/oauth2/*| OP
    OP -->|OIDC| KC
    GW -->|/| HOME
    GW -->|/containers/| CD_FE
    GW -->|/containers/api/| CD_BFF
    GW -.WS upgrade.-> CD_BFF
    CD_FE -.fetch+SSE+WS.-> GW
    CD_BFF --> SOCK
    CD_BFF --> SQLITE
    CD_BFF -->|file rotating| ELK
    OP -->|audit log| ELK
```

### 1.2. Flujo de una request mutadora (restart container)

```mermaid
sequenceDiagram
    participant U as Usuario (operator)
    participant GW as nginx-gateway
    participant OP as oauth2-proxy
    participant BFF as containers-dashboard-bff
    participant D as Docker daemon
    participant DB as SQLite (audit)

    U->>GW: POST /containers/api/containers/abc123/restart<br/>X-Confirm-Resource: lg-infra-elk-kibana-1
    GW->>OP: subreq /oauth2/auth
    OP-->>GW: 202 + X-Auth-Request-Groups: operator
    GW->>GW: authz: operator ∈ {admin,operator} ∧ method=POST → OK
    GW->>BFF: POST /api/containers/abc123/restart + headers
    BFF->>BFF: require_writer (defense in depth)
    BFF->>D: inspect abc123 → name, labels
    BFF->>BFF: assert name ∉ DENYLIST → OK
    BFF->>BFF: assert X-Confirm-Resource == name → OK
    BFF->>D: container.restart()
    D-->>BFF: ok
    BFF->>DB: INSERT audit_log
    BFF-->>GW: 202 Accepted {state:"restarting"}
    GW-->>U: 202
    Note over BFF: rotating file → Filebeat → ELK
```

### 1.3. Flujo de una sesión exec (admin only)

```mermaid
sequenceDiagram
    participant U as Usuario (admin)
    participant GW as nginx-gateway
    participant OP as oauth2-proxy
    participant BFF as containers-dashboard-bff
    participant D as Docker daemon

    U->>GW: GET /containers/api/containers/abc/exec?shell=sh<br/>Upgrade: websocket
    GW->>OP: subreq /oauth2/auth
    OP-->>GW: 202 + X-Auth-Request-Groups: admin
    GW->>GW: authz: admin only → OK + WS upgrade
    GW->>BFF: WS upgrade
    BFF->>BFF: require_admin
    BFF->>D: inspect abc → name
    BFF->>BFF: assert name ∉ DENYLIST
    BFF->>D: exec_create(cmd=["sh"], tty=true, stdin=true)
    BFF->>D: exec_start(stream=true, demux=false)
    BFF-->>U: WS connected, audit_open emitted
    loop while not idle 5min
        U->>BFF: stdin bytes
        BFF->>D: write to exec
        D->>BFF: stdout bytes
        BFF->>U: WS frame
    end
    BFF->>D: exec_inspect → exit_code
    BFF-->>U: WS close 1001
    Note over BFF: audit_close emitted with duration_ms + exit_code
```

### 1.4. Decisiones arquitectónicas clave

| ID | Decisión | Razón |
|---|---|---|
| AD-1 | **Frontend separado del BFF** (dos contenedores) | nginx ya está como base estable; BFF puede reiniciarse sin tirar la UI estática. Mismo patrón que kafka-dashboard. |
| AD-2 | **BFF con FastAPI** (no Flask, no Django) | OpenAPI gratis; pydantic ya valida lo del frontend; soporta WebSocket nativo (necesario para exec). Mismo stack que kafka-dashboard. |
| AD-3 | **docker-py** (`docker` PyPI), no Docker Engine API HTTP raw ni `docker` CLI subprocess | Cliente oficial Python, mantiene compatibilidad con versiones, expone WS para exec sin reinventar. |
| AD-4 | **SQLite local en volumen**, no Postgres compartido | Coherente con kafka-dashboard §A2; el único estado del BFF es el audit log local (rotado a fichero también). |
| AD-5 | **Authz en nginx**, no en BFF | Coherente con el resto del BackOffice. El BFF redobla con `require_admin`/`require_writer` como defense-in-depth (§B3). |
| AD-6 | **Audit doble**: oauth2-proxy (SSO subreq) + BFF (URI original + recurso) | Igual que kafka-dashboard §A8. Cubre limitación L2 del BackOffice. |
| AD-7 | **xterm.js vendored para exec** | UX terminal aceptable sin build step. Versión 5.x. WS bidireccional sin librería extra. |
| AD-8 | **Denylist hard-coded en código** (no env, no YAML) | Self-protection no debe poder desactivarse por config (§B5, §7.1 requirements). |
| AD-9 | **Stats vía SSE, no polling** | Stream natural de docker-py `stats(stream=True)`. Cliente abre/cierra; servidor cancela el iterator al desconectar. |
| AD-10 | **No autodetección de shell en exec** | Selector explícito `[sh, bash, ash]`. Detección automática requiere probe → complejidad sin valor en lab. |

---

## 2. Componentes

### 2.1. Mapa de servicios docker-compose

| Servicio | Imagen | Puerto host | Networks | Volumes |
|---|---|---|---|---|
| `containers-dashboard-fe` | `nginx:1.27-alpine` | — (interno) | `lg-backoffice` | `./frontend:/usr/share/nginx/html:ro` |
| `containers-dashboard-bff` | build local (Dockerfile) | — (interno) | `lg-backoffice` | `containers-dashboard-data:/data`, **`/var/run/docker.sock:/var/run/docker.sock:rw`**, `backoffice-audit-logs:/var/log/backoffice:rw` |

> Nombres reales de containers: `lg-infra-backoffice-containers-dashboard-fe` y `lg-infra-backoffice-containers-dashboard-bff` (siguiendo convención del BackOffice).
>
> ⚠️ **Privilegio**: el BFF monta `docker.sock` en modo `rw`. Esto da acceso root al host por diseño (igual que el container `portainer` existente). Mitigaciones obligatorias en §B3 + §B5 del addendum.

### 2.2. Frontend (`containers-dashboard-fe`)

- **Stack**: HTML estático + Alpine.js 3.14 (vendored) + Tailwind CSS 3.4 JIT browser (vendored) + xterm.js 5.x (vendored) — sin build.
- **Ruta servida**: el gateway proxea `/containers/` → `containers-dashboard-fe:80/`. La UI usa rutas relativas.
- **SPA single-page con hash router** (igual patrón final de kafka-dashboard): `index.html` + `assets/`.

```
frontend/
├── index.html              # SPA con todas las views
├── assets/
│   ├── alpine.min.js       # vendored 3.14.x
│   ├── tailwind.min.js     # vendored 3.4.x JIT browser
│   ├── xterm.js            # vendored 5.x
│   ├── xterm-addon-fit.js  # vendored
│   ├── xterm.css
│   └── app.js              # helpers: kd.call, humanizeError, hash router, fmt, toast
└── nginx.conf              # solo expone /, no proxy
```

**Views del hash router:**

| Hash | View | Descripción |
|---|---|---|
| `#/` | home | Summary cards: counts, daemon version, links |
| `#/containers` | containers-list | Tabla paginada con filtro |
| `#/containers/<id>` | container-detail | Tabs: Overview / Logs / Stats / Inspect |
| `#/containers/<id>/exec` | container-exec | xterm.js terminal (admin only) |
| `#/images` | images-list | Tabla read-only + remove (admin) |
| `#/volumes` | volumes-list | Tabla read-only + remove (admin) |
| `#/networks` | networks-list | Tabla read-only + remove (admin) |

### 2.3. BFF (`containers-dashboard-bff`)

- **Stack**: Python 3.12 + FastAPI 0.115 + `docker` (docker-py) 7.x + sqlmodel + pydantic 2 + websockets.
- **Estructura `bff/`**:

```
bff/
├── Dockerfile
├── requirements.txt
├── pyproject.toml
├── app/
│   ├── main.py                   # FastAPI factory + lifespan
│   ├── deps.py                   # auth deps (extrae headers oauth2-proxy)
│   ├── settings.py               # pydantic-settings
│   ├── errors.py                 # excepciones + handlers (envelope)
│   ├── safety/
│   │   ├── denylist.py           # DENYLIST set + assert_not_protected()
│   │   └── redact.py             # regex SECRET_RE + redact_env()
│   ├── middleware/
│   │   ├── audit.py              # request → audit_log row + rotating file (igual a kafka-dashboard)
│   │   └── timing.py             # request_id + duration_ms
│   ├── routers/
│   │   ├── health.py             # GET /api/health
│   │   ├── summary.py            # GET /api/summary
│   │   ├── containers.py         # CRUD + logs + stats SSE
│   │   ├── exec.py               # WS /api/containers/{id}/exec
│   │   ├── images.py
│   │   ├── volumes.py
│   │   └── networks.py
│   ├── repos/
│   │   ├── docker_repo.py        # docker-py wrapper + retry/timeout
│   │   ├── audit_repo.py         # SQLite writes (idempotente como kafka-dashboard)
│   │   └── migrations/
│   │       └── 001_initial.sql   # audit_log table
│   └── models/
│       ├── domain.py             # pydantic domain models
│       └── db.py                 # sqlmodel tables
└── tests/
    ├── unit/
    └── contract/
```

- **Endpoint base**: el BFF se monta en `/api` internamente; el gateway añade `/containers/api/` → `bff:8000/api/`.

### 2.4. Persistencia (`containers-dashboard-data` volume)

- Volumen Docker named, NO bind mount.
- Contiene `app.db` (SQLite, sólo audit_log).
- Backup: documentado como receta manual en runbook (no Makefile target — coherente con kafka-dashboard fase G.4).

### 2.5. Logs y rotación

- **Stdout** (uvicorn access + app logs) → `docker logs` para troubleshooting normal.
- **Audit dedicado** (`logger="containers_dashboard.audit"`) → `RotatingFileHandler` 50 MiB × 3 backups → `/var/log/backoffice/containers-dashboard-app.log` (volumen `backoffice-audit-logs` compartido con kafka-dashboard).
- **Filebeat** (existente en stack ELK) tendrá un nuevo input que tail-ea ese path con tag `containers-dashboard-app`.

---

## 3. Contratos API

> Todos los endpoints viven bajo `/containers/api/` desde fuera, `/api/` dentro del BFF. Todos devuelven JSON salvo SSE/WS. Errores siguen el envelope §7.

### 3.1. Health

#### `GET /api/health`

| Campo | Detalle |
|---|---|
| Auth | público (no pasa por oauth2-proxy auth_request) |
| Response 200 | `{"status":"ok","docker":"ok\|degraded","sqlite":"ok"}` |
| Response 503 | mismo schema con `status:"degraded"` |

### 3.2. Summary (US-9)

#### `GET /api/summary`

| Campo | Detalle |
|---|---|
| Auth | requerido (todos los roles) |
| Response 200 | ver schema abajo |

```json
{
  "containers": {"total": 17, "running": 14, "exited": 3, "paused": 0, "restarting": 0, "created": 0},
  "images_total": 32,
  "volumes_total": 12,
  "networks_total": 7,
  "daemon_version": "27.3.1",
  "daemon_api_version": "1.47",
  "images_size_mb": 4123.4,
  "components": {"docker":"ok", "sqlite":"ok"}
}
```

### 3.3. Containers (US-1..US-6)

#### `GET /api/containers`

| Campo | Detalle |
|---|---|
| Auth | requerido (todos) |
| Query | `?include_stopped=true&search=&page=1&page_size=50` |
| Response 200 | `{items: ContainerSummary[], total, page, page_size}` |

`ContainerSummary`:
```json
{
  "id": "abc123def456",
  "id_short": "abc123def456"[:12],
  "name": "lg-infra-elk-kibana-1",
  "image": "kibana:8.13.0",
  "image_id": "sha256:...",
  "state": "running",
  "status": "Up 9 hours (healthy)",
  "compose_project": "lg-infra-elk",
  "compose_service": "kibana",
  "ports": [{"private": 5601, "public": 5601, "type": "tcp", "ip": "0.0.0.0"}],
  "labels_lglabs": {"lglabs.tier": "monitoring"},
  "is_protected": false,
  "created": "2026-05-10T03:00:00Z"
}
```

#### `GET /api/containers/{id}`

| Campo | Detalle |
|---|---|
| Auth | requerido (todos) |
| Response 200 | `ContainerDetail` |
| Response 404 | si no existe |

`ContainerDetail` extiende `ContainerSummary` con:
```json
{
  "image_digest": "sha256:...",
  "command": ["./entrypoint.sh"],
  "env": [{"key": "NODE_ENV", "value": "production"}, {"key": "DB_PASSWORD", "value": "<redacted>"}],
  "mounts": [{"type": "bind", "source": "...", "target": "...", "mode": "rw"}],
  "networks": [{"name": "lg-backoffice", "ip": "172.20.0.5", "mac": "..."}],
  "labels": {"...all labels..."},
  "restart_policy": {"name": "unless-stopped", "max_retries": 0},
  "health": {"status": "healthy", "failing_streak": 0}
}
```

#### `GET /api/containers/{id}/logs`

| Campo | Detalle |
|---|---|
| Auth | requerido (todos) |
| Query | `?tail=500&since=&timestamps=false` |
| Response 200 | `{"lines": ["...", ...], "tail": 500, "truncated": false}` |

`tail`: 1..2000 (default 500).

#### `GET /api/containers/{id}/logs/stream`

SSE stream. Cliente hace `EventSource`. Cada evento `data:` contiene una línea JSON `{"line":"...","ts":"..."}`.

#### `GET /api/containers/{id}/stats`

SSE stream. Cada evento (~1s) `data:` contiene:
```json
{"cpu_percent": 12.4, "memory_usage_mb": 256, "memory_limit_mb": 512, "net_rx_kbps": 0.5, "net_tx_kbps": 0.2, "block_read_mb": 0.1, "block_write_mb": 0.0}
```

Si `state != running`, responde `200` con un único evento `{"unavailable": true, "reason": "container_not_running"}` y cierra.

#### `GET /api/containers/{id}/inspect`

| Campo | Detalle |
|---|---|
| Auth | requerido (todos) |
| Response 200 | output crudo de `docker inspect` con env redactado |

#### `POST /api/containers/{id}/start`

| Campo | Detalle |
|---|---|
| Auth | admin, operator |
| Headers | (ninguno extra) |
| Response 202 | `{"id": "...", "state": "running"}` |
| Response 423 | `protected_resource` si en denylist |
| Response 409 | `already_running` |

#### `POST /api/containers/{id}/stop`

| Campo | Detalle |
|---|---|
| Auth | admin, operator |
| Query | `?timeout_seconds=10` (1..60) |
| Headers | `X-Confirm-Resource: <name>` |
| Response 202 | `{"id": "...", "state": "exited"}` |
| Response 409 | `confirmation_required` o `already_stopped` |
| Response 423 | `protected_resource` |

#### `POST /api/containers/{id}/restart`

| Campo | Detalle |
|---|---|
| Auth | admin, operator |
| Query | `?timeout_seconds=10` |
| Headers | `X-Confirm-Resource: <name>` |
| Response 202 | `{"id": "...", "state": "restarting"}` |
| Response 409 | `confirmation_required` |
| Response 423 | `protected_resource` |

#### `DELETE /api/containers/{id}`

| Campo | Detalle |
|---|---|
| Auth | **admin only** |
| Query | `?force=false&remove_volumes=false` |
| Headers | `X-Confirm-Resource: <name>` |
| Response 204 | éxito |
| Response 409 | `container_running` (sin force), `confirmation_required` |
| Response 423 | `protected_resource` |

#### `WS /api/containers/{id}/exec`

| Campo | Detalle |
|---|---|
| Auth | **admin only** |
| Query | `?shell=sh` (enum: sh, bash, ash) |
| Frames cliente → servidor | bytes UTF-8 (stdin) o JSON `{"resize": {"cols": 80, "rows": 24}}` |
| Frames servidor → cliente | bytes UTF-8 (stdout/stderr mux) |
| Close codes | `1000` normal, `1001` idle timeout, `1011` daemon error |
| Idle timeout | 5 min (configurable env `EXEC_IDLE_TIMEOUT_S=300`) |

Audit:
- Al abrir: `audit_type=exec_open`, `resource_type=container`, `resource_name=<name>`, `details={shell, command_id}`.
- Al cerrar: `audit_type=exec_close`, `details={duration_ms, exit_code, close_reason}`.
- Stream content: NO se persiste.

### 3.4. Images (US-7, US-8)

#### `GET /api/images`

`{items: [{id, repository, tag, size_mb, created, containers_using}], total, page, page_size}`.

#### `DELETE /api/images/{id}`

| Auth | **admin only** |
|---|---|
| Query | `?force=false&prune_children=false` |
| Headers | `X-Confirm-Resource: <repository:tag>` o `<id_short>` |
| Response 204 | éxito |
| Response 409 | `image_in_use` (sin force) |

### 3.5. Volumes (US-7, US-8)

#### `GET /api/volumes`

`{items: [{name, driver, mountpoint, created, size_mb, containers_using}], total, page, page_size}`.

> `size_mb` se calcula con `docker system df -v` style; cacheado 60s para no tirar el daemon.

#### `DELETE /api/volumes/{name}`

| Auth | **admin only** |
|---|---|
| Headers | `X-Confirm-Resource: <name>` |
| Response 204 | éxito |
| Response 409 | `volume_in_use` (sin force, NO existe force aquí — §AC-8.3) |

### 3.6. Networks (US-7, US-8)

#### `GET /api/networks`

`{items: [{id, name, driver, scope, internal, containers_attached, is_builtin}], total, page, page_size}`.

#### `DELETE /api/networks/{id}`

| Auth | **admin only** |
|---|---|
| Headers | `X-Confirm-Resource: <name>` |
| Response 204 | éxito |
| Response 403 | `builtin_network_protected` (bridge/host/none) |
| Response 409 | `network_in_use` |

---

## 4. Modelo SQLite

### 4.1. DDL

```sql
CREATE TABLE IF NOT EXISTS _schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL DEFAULT (datetime('now')),
    request_id    TEXT,
    audit_source  TEXT NOT NULL DEFAULT 'containers-dashboard-bff',
    audit_type    TEXT NOT NULL,             -- request|exec_open|exec_close
    user          TEXT NOT NULL,
    groups        TEXT,
    method        TEXT,
    path          TEXT,                      -- BFF path (/api/...)
    original_uri  TEXT,                      -- /containers/api/...
    status        INTEGER,
    duration_ms   INTEGER,
    resource_type TEXT,                      -- container|image|volume|network
    resource_id   TEXT,
    resource_name TEXT,
    detail        TEXT                       -- JSON opcional
);

CREATE INDEX IF NOT EXISTS idx_audit_ts          ON audit_log(ts);
CREATE INDEX IF NOT EXISTS idx_audit_user        ON audit_log(user);
CREATE INDEX IF NOT EXISTS idx_audit_request_id  ON audit_log(request_id);
CREATE INDEX IF NOT EXISTS idx_audit_audit_type  ON audit_log(audit_type);
```

> Nota: NO replicamos `audit_log` del kafka-dashboard 1:1 — aquí no hay `topic_metadata` ni `acl_metadata`. El único estado es el audit. Si en el futuro se quisiera anotar containers (igual que owners en topics), se añade en backlog.

---

## 5. Integración con el gateway

### 5.1. Bloques nginx nuevos en `backoffice/home/nginx.conf`

Patrón idéntico a kafka-dashboard, con dos diferencias:

1. **WS upgrade** habilitado en `/containers/api/containers/*/exec`.
2. Authz para exec: **admin only**. Authz para DELETE container/image/volume/network: **admin only**. Authz para POST start/stop/restart: admin+operator.

```nginx
upstream containers_dashboard_fe_upstream  { server containers-dashboard-fe:80; }
upstream containers_dashboard_bff_upstream { server containers-dashboard-bff:8000; }

# Frontend estático
location /containers/ {
    auth_request /oauth2/auth;
    error_page 401 = @redirect_to_login;
    auth_request_set $auth_user   $upstream_http_x_auth_request_user;
    auth_request_set $auth_groups $upstream_http_x_auth_request_groups;

    proxy_set_header Host              $http_host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Auth-Request-User   $auth_user;
    proxy_set_header X-Auth-Request-Groups $auth_groups;

    proxy_pass http://containers_dashboard_fe_upstream/;
}

# WebSocket exec — admin only
location ~ ^/containers/api/containers/[^/]+/exec$ {
    auth_request /oauth2/auth;
    error_page 401 = @redirect_to_login;
    auth_request_set $auth_user   $upstream_http_x_auth_request_user;
    auth_request_set $auth_groups $upstream_http_x_auth_request_groups;

    if ($auth_groups !~ "(^|,)admin(,|$)") { return 403; }

    proxy_http_version 1.1;
    proxy_set_header Upgrade           $http_upgrade;
    proxy_set_header Connection        "upgrade";
    proxy_set_header Host              $http_host;
    proxy_set_header X-Auth-Request-User   $auth_user;
    proxy_set_header X-Auth-Request-Groups $auth_groups;
    proxy_set_header X-Original-URI        $request_uri;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;

    proxy_pass http://containers_dashboard_bff_upstream;
}

# API REST/SSE
location /containers/api/ {
    auth_request /oauth2/auth;
    error_page 401 = @redirect_to_login;
    auth_request_set $auth_user   $upstream_http_x_auth_request_user;
    auth_request_set $auth_groups $upstream_http_x_auth_request_groups;

    # Health pasa sin auth
    location = /containers/api/health {
        auth_request off;
        proxy_pass http://containers_dashboard_bff_upstream/api/health;
    }

    # Authz por método/path — usaremos `map` (no `if`) en implementación final.
    # Esquema lógico:
    #   GET/HEAD   → cualquier autenticado
    #   POST       → start/stop/restart: admin|operator
    #   DELETE     → admin only
    #   (exec WS lo maneja el location ~ de arriba)
    set $authz_required role_any;
    if ($request_method = POST)   { set $authz_required role_writer; }
    if ($request_method = DELETE) { set $authz_required role_admin; }
    # Implementación final con `map $request_method $authz_required` + `map $auth_groups $has_role`
    # (ver tasks Fase A.2.2)

    proxy_set_header Host                  $http_host;
    proxy_set_header X-Auth-Request-User   $auth_user;
    proxy_set_header X-Auth-Request-Groups $auth_groups;
    proxy_set_header X-Original-URI        $request_uri;
    # SSE necesita estos headers para no bufferear
    proxy_buffering    off;
    proxy_cache        off;
    proxy_read_timeout 3600s;

    proxy_pass http://containers_dashboard_bff_upstream/api/;
}
```

### 5.2. Tarjeta en home

`backoffice/home/index.html` añade tarjeta visible para los 4 roles. La authz fina la decide gateway+BFF.

```html
<a href="/containers/" class="card" data-roles="admin,operator,support,viewer">
  <h3>Containers Dashboard</h3>
  <p>Ver, reiniciar, inspeccionar y diagnosticar containers Docker del host.</p>
  <small>Docker daemon · self-protected</small>
</a>
```

> Convive con la tarjeta existente de Portainer (no la sustituye; ver §1 requirements "Coexistencia").

---

## 6. Matriz role × endpoint

| Endpoint | Method | admin | operator | support | viewer |
|---|---|:-:|:-:|:-:|:-:|
| `/api/health` | GET | ✅ | ✅ | ✅ | ✅ (sin auth) |
| `/api/summary` | GET | ✅ | ✅ | ✅ | ✅ |
| `/api/containers` | GET | ✅ | ✅ | ✅ | ✅ |
| `/api/containers/{id}` | GET | ✅ | ✅ | ✅ | ✅ |
| `/api/containers/{id}/logs` | GET | ✅ | ✅ | ✅ | ✅ |
| `/api/containers/{id}/logs/stream` | GET (SSE) | ✅ | ✅ | ✅ | ✅ |
| `/api/containers/{id}/stats` | GET (SSE) | ✅ | ✅ | ✅ | ✅ |
| `/api/containers/{id}/inspect` | GET | ✅ | ✅ | ✅ | ✅ |
| `/api/containers/{id}/start` | POST | ✅ | ✅ | ❌ | ❌ |
| `/api/containers/{id}/stop` | POST | ✅ | ✅ | ❌ | ❌ |
| `/api/containers/{id}/restart` | POST | ✅ | ✅ | ❌ | ❌ |
| `/api/containers/{id}` | DELETE | ✅ | ❌ | ❌ | ❌ |
| `/api/containers/{id}/exec` | WS | ✅ | ❌ | ❌ | ❌ |
| `/api/images` | GET | ✅ | ✅ | ✅ | ✅ |
| `/api/images/{id}` | DELETE | ✅ | ❌ | ❌ | ❌ |
| `/api/volumes` | GET | ✅ | ✅ | ✅ | ✅ |
| `/api/volumes/{name}` | DELETE | ✅ | ❌ | ❌ | ❌ |
| `/api/networks` | GET | ✅ | ✅ | ✅ | ✅ |
| `/api/networks/{id}` | DELETE | ✅ | ❌ | ❌ | ❌ |

> Esta tabla es el **contrato verificable**: `smoke-tests.md` ejecuta una request por cada celda con un usuario de cada rol.

---

## 7. Manejo de errores

### 7.1. Error envelope

```json
{
  "error": "<machine_code>",
  "message": "<human-readable, en inglés>",
  "details": { /* opcional, contexto */ }
}
```

### 7.2. Códigos de error definidos

| Code | HTTP | Origen |
|---|---|---|
| `invalid_payload` | 400 | pydantic validation |
| `invalid_query` | 400 | query params fuera de rango |
| `invalid_shell` | 400 | shell ∉ {sh,bash,ash} |
| `builtin_network_protected` | 403 | bridge/host/none |
| `container_not_found` | 404 | — |
| `image_not_found` | 404 | — |
| `volume_not_found` | 404 | — |
| `network_not_found` | 404 | — |
| `confirmation_required` | 409 | header ausente o no coincide |
| `container_running` | 409 | DELETE container running sin force |
| `already_running` | 409 | start sobre running |
| `already_stopped` | 409 | stop sobre stopped |
| `image_in_use` | 409 | DELETE image con containers |
| `volume_in_use` | 409 | DELETE volume montado |
| `network_in_use` | 409 | DELETE network con containers |
| `protected_resource` | 423 | denylist hit |
| `docker_unavailable` | 503 | socket no responde |

### 7.3. Mapeo docker-py exceptions

| docker-py exception | HTTP | error code |
|---|---|---|
| `docker.errors.NotFound` | 404 | `*_not_found` (depende del recurso) |
| `docker.errors.APIError` (status 409) | 409 | `*_in_use` o `container_running` |
| `docker.errors.ImageNotFound` | 404 | `image_not_found` |
| `docker.errors.NotFound` (pull) | 404 | n/a (no pull en MVP) |
| `requests.exceptions.ConnectionError` (socket) | 503 | `docker_unavailable` |
| `requests.exceptions.ReadTimeout` | 503 | `docker_unavailable` |
| (otra) | 500 | `internal_error` |

---

## 8. Audit

### 8.1. Doble fuente

| Fuente | Captura | Limitación |
|---|---|---|
| oauth2-proxy (existente) | quién, cuándo, status — pero `path=/oauth2/auth` (subreq) | L2 BackOffice |
| BFF (nuevo) | URI original + `resource_type/id/name` + `audit_type` (request/exec_open/exec_close) | sólo lo que llega al BFF |

Ambos acaban en `backoffice-audit-*`. `audit_source` discrimina (`oauth2-proxy` vs `containers-dashboard-bff`). **MISMO índice que kafka-dashboard** — el campo `audit_source` ya tiene 2 valores hoy, ahora tendrá 3.

### 8.2. Pipeline del BFF

```
BFF logger "containers_dashboard.audit" (JSON ndjson)
  └─→ RotatingFileHandler 50MB×3 → /var/log/backoffice/containers-dashboard-app.log
        └─→ filebeat input "containers-dashboard-app" (filestream, fingerprint.length=64)
              └─→ logstash conditional branch "containers-dashboard-app" in [tags]
                    └─→ ES backoffice-audit-YYYY.MM.dd
```

El volumen `backoffice-audit-logs` ya existe (compartido con kafka-dashboard). Sólo añadimos un input Filebeat y una rama Logstash.

### 8.3. Schema del evento BFF

```json
{
  "@timestamp": "2026-05-10T12:00:00.123Z",
  "audit_source": "containers-dashboard-bff",
  "audit_type": "request",
  "user": "lglabsoperator@lglabs.local",
  "groups": ["operator"],
  "method": "POST",
  "path": "/api/containers/abc123/restart",
  "original_uri": "/containers/api/containers/abc123/restart",
  "status": 202,
  "resource_type": "container",
  "resource_id": "abc123",
  "resource_name": "lg-infra-elk-kibana-1",
  "duration_ms": 142,
  "request_id": "uuid"
}
```

Para exec sessions (audit_type ∈ `exec_open|exec_close`), `details` lleva `{shell, command_id}` o `{duration_ms, exit_code, close_reason}`.

### 8.4. Sanitización

- NO request body en logs.
- Env values redactados server-side antes de loguear inspect.
- Stream content de exec NO se loguea (§B7).
- Cuando un endpoint loguea recurso, sólo identificadores (id, name, image:tag), no descripciones largas.

---

## 9. Configuración y secretos

### 9.1. `.env.example`

```bash
# containers-dashboard
CONTAINERS_DASHBOARD_BFF_MEM_LIMIT=256m
CONTAINERS_DASHBOARD_FE_MEM_LIMIT=64m
CONTAINERS_DASHBOARD_LOG_LEVEL=INFO
CONTAINERS_DASHBOARD_EXEC_IDLE_TIMEOUT_S=300
CONTAINERS_DASHBOARD_AUDIT_LOG_PATH=/var/log/backoffice/containers-dashboard-app.log
DOCKER_API_TIMEOUT_S=10
```

### 9.2. Variables internas

| Var | Default | Uso |
|---|---|---|
| `DOCKER_HOST` | `unix:///var/run/docker.sock` | docker-py client |
| `SQLITE_PATH` | `/data/app.db` | audit DB |
| `EXEC_IDLE_TIMEOUT_S` | `300` | WS idle timeout |
| `LOG_LEVEL` | `INFO` | logger Python |
| `BFF_PORT` | `8000` | puerto interno |
| `AUDIT_LOG_PATH` | `/var/log/backoffice/containers-dashboard-app.log` | rotating handler |

---

## 10. Healthchecks y memory limits

### 10.1. `containers-dashboard-bff`

```yaml
healthcheck:
  test: ["CMD", "wget", "-q", "-O-", "http://localhost:8000/api/health"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 20s
deploy:
  resources:
    limits:
      memory: ${CONTAINERS_DASHBOARD_BFF_MEM_LIMIT:-256m}
```

### 10.2. `containers-dashboard-fe`

```yaml
healthcheck:
  test: ["CMD", "wget", "-q", "-O-", "http://localhost/"]
  interval: 30s
  timeout: 3s
  retries: 3
  start_period: 5s
deploy:
  resources:
    limits:
      memory: ${CONTAINERS_DASHBOARD_FE_MEM_LIMIT:-64m}
```

### 10.3. Boot order

- `containers-dashboard-bff` no depende de otro servicio del BackOffice (solo del docker.sock que existe en el host).
- `containers-dashboard-fe` no depende de nadie.
- `nginx-gateway` resuelve upstreams al arrancar — el BackOffice debe levantar este sub-stack como parte del compose include.

---

## 11. Decisiones técnicas registradas

### 11.1. Sí

| ID | Decisión | Por qué |
|---|---|---|
| AD-1..10 | Ver §1.4 | — |
| AD-11 | OpenAPI auto en `/api/openapi.json` | Útil para tests de contrato |
| AD-12 | UUID v4 para `request_id` | Propagado en header `X-Request-Id`; correlación cross-fuente |
| AD-13 | docker-py con `timeout=10s` por default | Evita colgar el BFF si el daemon va lento |
| AD-14 | Stats SSE: backpressure por `asyncio.Queue(maxsize=10)` | Si cliente lento, descarta samples antiguos |

### 11.2. No

| ID | Rechazo | Por qué |
|---|---|---|
| AD-N1 | Compose stacks management | Lo cubre Portainer; añadirlo duplica esfuerzo |
| AD-N2 | Pull/push imágenes desde UI | Operación lenta, mejor en CI/CLI |
| AD-N3 | gRPC entre fe y bff | Es navegador, HTTP+JSON+WS es lo natural |
| AD-N4 | Caché de containers list (Redis o memoria) | docker.sock es local y rápido |
| AD-N5 | OPA / external authz engine | Overkill; nginx + headers + denylist suficiente |
| AD-N6 | Multi-host / Swarm | YAGNI |
| AD-N7 | Grabar contenido de exec | Compromiso de seguridad — §B7 |

---

## 12. Trazabilidad inversa

(Se completa al escribir `tasks.md`. Cada task referencia esta sección. Cada US referencia las tasks.)

---

## 13. Projects view (Phase I)

> Adenda a v0.2.0 — añade vista de agrupación por compose project con diagrama de componentes. Cubre **US-10** (`requirements.md` §4).

### 13.1. Discovery: cómo se identifican proyectos

Docker Compose añade automáticamente labels a los containers que crea:

| Label | Significado | Origen |
|---|---|---|
| `com.docker.compose.project` | Nombre del proyecto (slug) | nombre del directorio o `--project-name` |
| `com.docker.compose.service` | Rol del container dentro del proyecto | clave bajo `services:` en compose |
| `com.docker.compose.depends_on` | CSV de dependencias declaradas | `depends_on:` del compose |
| `com.docker.compose.config-hash` | Hash del compose merged | usado para detectar drift |

**Discovery:**

1. `docker.containers.list(all=True)` (todos, running + stopped).
2. Para cada container, leer `Labels["com.docker.compose.project"]`. Si falta → asignar al pseudo-proyecto `(unmanaged)`.
3. Agrupar por nombre de proyecto.
4. Por cada proyecto, recolectar (a) services, (b) networks `NetworkSettings.Networks` (unión de todos sus containers), (c) volumes mount-points `Mounts` filtrados a `Type=volume`.

> El daemon NO expone "compose projects" como recurso de primera clase; las labels son la única fuente fiable. Esto es estándar y lo usa Portainer también.

### 13.2. Modelo (Pydantic v2)

```python
# bff/app/models/projects.py

class ProjectService(BaseModel):
    name: str            # com.docker.compose.service
    container: str       # container name (sin /)
    container_id: str
    state: str           # running | exited | paused | created | restarting | dead
    image: str
    ports: list[str] = []
    depends_on: list[str] = []   # parseado de label depends_on
    is_protected: bool = False   # entry en denylist

class ProjectNetwork(BaseModel):
    name: str
    services_in: list[str]       # service names

class ProjectVolume(BaseModel):
    name: str                    # docker volume name
    services_using: list[str]    # service names que lo montan

class ProjectListItem(BaseModel):
    name: str
    services: list[str]          # sólo nombres
    containers_total: int
    containers_running: int
    networks: list[str]          # sólo nombres
    volumes: list[str]
    aggregate_status: Literal["up", "degraded", "down", "stopped"]
    created_at_min: datetime | None
    created_at_max: datetime | None

class GraphNode(BaseModel):
    id: str                      # service name (único en el proyecto)
    label: str                   # display: "service\ncontainer"
    state: str

class GraphEdge(BaseModel):
    from_: str = Field(alias="from")
    to: str
    type: Literal["depends_on", "network", "volume"]
    meta: dict = {}              # {"network": "lg-net"} ó {"volume": "vol-name"}

class ProjectDetail(BaseModel):
    name: str
    services: list[ProjectService]
    networks: list[ProjectNetwork]
    volumes: list[ProjectVolume]
    graph: dict[str, list]       # {"nodes": [...], "edges": [...]}
```

### 13.3. Repositorio: `ProjectsRepo`

```python
# bff/app/repos/projects_repo.py

class ProjectsRepo:
    def __init__(self, docker_repo: DockerRepo): ...

    def list_projects(self, include_unmanaged: bool = False) -> list[ProjectListItem]:
        """Agrupa todos los containers por label compose.project."""

    def get_project(self, name: str) -> ProjectDetail:
        """
        Para name='(unmanaged)': agrupa containers sin label.
        Para cualquier otro: filtra por label.
        Construye services, networks (unión), volumes (unión), y el grafo.
        Lanza ProjectNotFound si no hay containers que matcheen.
        """

    def _build_graph(self, services, networks, volumes) -> dict:
        """
        Aristas:
          - depends_on: una por cada entry de label compose.depends_on
            (csv parsing). Tipo='depends_on'.
          - network: para cada network del proyecto, una clique parcial
            (NO clique completa para evitar O(n²)): edge entre service[0] y
            cada otro service en esa network. Tipo='network', meta.network=name.
            Si la network es 'bridge' default, se SKIP (ruido).
          - volume: para cada volume usado por >=2 services, edge entre
            el primer service y los demás. Tipo='volume', meta.volume=name.
        Dedupe: una sola edge por (from, to, type, meta) ignorando dirección
        para network/volume; respetando dirección para depends_on.
        """
```

> **Decisión de diseño** (AD-13.1): para co-network/co-volume usamos "star pattern" (service[0] como hub) en vez de clique completa. Razón: clique para 10 services con 1 network = 45 aristas, ilegible. Star = 9 aristas, comprensible. El usuario ve "todos pegados a la misma network" igual de claro.

### 13.4. Router: `/api/projects`

```python
# bff/app/routers/projects.py

router = APIRouter(prefix="/projects", tags=["projects"])

@router.get("", response_model=list[ProjectListItem])
def list_projects(
    include_unmanaged: bool = Query(False),
    repo: ProjectsRepo = Depends(get_projects_repo),
    user = Depends(require_any_role)
):
    return repo.list_projects(include_unmanaged=include_unmanaged)

@router.get("/{name}", response_model=ProjectDetail)
def get_project(
    name: str,
    repo: ProjectsRepo = Depends(get_projects_repo),
    user = Depends(require_any_role)
):
    try:
        return repo.get_project(name)
    except ProjectNotFound:
        raise HTTPException(404, f"Project '{name}' not found")
```

> **Read-only**: 0 mutations en `/api/projects/*`. Las acciones (start/stop/restart/remove) reutilizan los routers existentes desde el frontend (mismo backend, misma RBAC, misma audit).

### 13.5. Aggregate status (cálculo)

```python
def _aggregate(services: list[ProjectService]) -> str:
    states = {s.state for s in services}
    running = sum(1 for s in services if s.state == "running")
    total = len(services)
    if running == total:
        return "up"
    if running == 0:
        # any exited with non-zero? → down; else stopped
        # NOTE: docker-py exposes ExitCode via inspect; en list_projects
        # no lo refetcheamos para no penalizar p95. Heuristic:
        # si 'dead' o 'restarting' → down; else stopped.
        if {"dead", "restarting"} & states:
            return "down"
        return "stopped"
    return "degraded"
```

### 13.6. Frontend

#### 13.6.1. Routing (hash-based, ya en uso)

| Ruta | Vista |
|---|---|
| `#/` | **Projects list (NEW landing)** |
| `#/projects/<name>` | Project detail (Overview/Topology/Networks/Volumes tabs) |
| `#/home` | Daemon home (US-9 — antes era `/`) |
| `#/containers`, `#/images`, `#/volumes`, `#/networks` | sin cambios |
| `#/containers/<id>` | sin cambios (los nodos del grafo enlazan aquí) |

#### 13.6.2. Estructura UI — Project list

```
┌────────────────────────────────────────────────────────┐
│ Projects                       [+] include unmanaged   │
├────────────────────────────────────────────────────────┤
│ ┌────────────┐ ┌────────────┐ ┌────────────┐           │
│ │ backoffice │ │ kafka      │ │ elk        │           │
│ │ 🟢 up      │ │ 🟡 degraded│ │ 🟢 up      │           │
│ │ 6/6 running│ │ 3/4 running│ │ 4/4 running│           │
│ │ 6 services │ │ 4 services │ │ 4 services │           │
│ │ 2 networks │ │ 1 network  │ │ 1 network  │           │
│ └────────────┘ └────────────┘ └────────────┘           │
└────────────────────────────────────────────────────────┘
```

Card click → `#/projects/<name>`. Card es plenamente keyboard-accessible (role=button, tabindex, Enter/Space).

#### 13.6.3. Project detail — tabs

```
< Back to Projects     backoffice            🟢 up
─────────────────────────────────────────────────────────
[ Overview ] [ Topology ] [ Networks ] [ Volumes ]
```

- **Overview**: tabla de services (=mismo formato de la lista plana de containers, sin paginación), con acciones inline (start/stop/restart/remove) que reutilizan los modales y endpoints existentes (`/api/containers/<ref>/{start,stop,restart}`).
- **Topology**: contenedor `<div id="cd-graph">` donde se inyecta el código Mermaid generado, más una toolbar de filtros:

  ```
  ☑ depends_on   ☑ networks   ☑ volumes        [Re-render]
  ```

- **Networks**: lista accordion de networks con qué services participan; click en network name → `#/networks/<name>`.
- **Volumes**: ídem para volumes; click → `#/volumes/<name>`.

#### 13.6.4. Mermaid render

```javascript
// frontend/index.html (Alpine component cd.projectDetail)
async render(detail, filters) {
  const lines = ['graph LR'];
  // Nodos
  for (const s of detail.services) {
    const colorClass = {
      running: 'cdRunning',
      exited:  'cdExited',
      paused:  'cdPaused',
    }[s.state] || 'cdOther';
    lines.push(`  ${s.id}["${s.name}<br/>${s.container}"]:::${colorClass}`);
  }
  // Edges
  for (const e of detail.graph.edges) {
    if (!filters[e.type]) continue;
    const arrow = {
      depends_on: '-->',           // sólido
      network:    '-.-',            // punteado
      volume:     '===',            // grueso/doble
    }[e.type];
    const label = e.type === 'network' ? `|${e.meta.network}|`
                : e.type === 'volume'  ? `|${e.meta.volume}|`
                : '';
    lines.push(`  ${e.from} ${arrow}${label} ${e.to}`);
  }
  // Class definitions
  lines.push('  classDef cdRunning fill:#bbf7d0,stroke:#16a34a;');
  lines.push('  classDef cdExited  fill:#fecaca,stroke:#dc2626;');
  lines.push('  classDef cdPaused  fill:#fde68a,stroke:#d97706;');
  lines.push('  classDef cdOther   fill:#e5e7eb,stroke:#6b7280;');
  const code = lines.join('\n');
  const { svg } = await mermaid.render('cd-graph-svg', code);
  document.getElementById('cd-graph').innerHTML = svg;
  // Click handlers post-render
  document.querySelectorAll('#cd-graph .node').forEach(node => {
    node.style.cursor = 'pointer';
    node.addEventListener('click', () => {
      const id = node.id.replace(/^flowchart-/, '').split('-')[0];
      const svc = detail.services.find(s => s.id === id);
      if (svc) location.hash = `#/containers/${svc.container_id}`;
    });
  });
}
```

> **Decisión** (AD-13.2): Mermaid client-side, NO server-side rendering. Razón: server no necesita Node; el grafo cambia con filtros sin refetch.

### 13.7. Vendoreo de Mermaid 10

- Archivo: `frontend/assets/mermaid.min.js` (versión `10.9.4`, ~2.8MB → gzip nginx ~750KB).
- Source: `https://cdn.jsdelivr.net/npm/mermaid@10.9.4/dist/mermaid.min.js`.
- Inicialización: `mermaid.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'strict' })`.
- `securityLevel: 'strict'` impide ejecución de HTML/JS en labels (los nombres de service vienen de Docker; aunque ya están sanitizados, defensa en profundidad).

### 13.8. Audit

- `GET /api/projects` → audit middleware emite evento estándar (igual que cualquier GET). `event` derivado del path.
- `GET /api/projects/{name}` → ídem.
- Mutations seguidas desde el detail page emiten audit con su evento original (`container.start`, `container.stop`, etc.) — sin cambios de Phase G.

### 13.9. Casos límite

| Caso | Comportamiento |
|---|---|
| Containers con label compose.project pero compose.service vacío | service = container name |
| 2 containers con mismo `compose.service` (replicas) | se listan ambos como entries separados con suffix numérico (`web-1`, `web-2`) |
| Network `bridge` default | se omite del grafo (ruido) |
| `compose.depends_on` apunta a service que no existe en el proyecto (orphan) | edge dropped + warn en logs del BFF |
| Proyecto con 1 solo service | grafo con 1 nodo y 0 aristas |
| Proyecto vacío (todos containers fueron removed) | desaparece de `list_projects` |
| `(unmanaged)` con 50 containers | se renderiza pero el grafo se desactiva por defecto (>20 nodes); tab Topology muestra warning "Graph disabled — too many nodes". |

### 13.10. NFR

| NFR | Métrica | Cómo se mide |
|---|---|---|
| NFR-10 | `GET /api/projects` < 1s p95 con 30 proyectos / 100 containers | smoke I.5 con timing |
| NFR-11 | Render Mermaid < 500ms para proyectos ≤ 20 services | benchmark client-side console.time |
| NFR-12 | Mermaid library cacheable (Cache-Control inmutable nginx) | `expires 30d; immutable;` en location `/containers/assets/` |

### 13.11. Decisiones (Phase I)

| ID | Decisión | Razón |
|---|---|---|
| AD-13.1 | Star pattern para co-network/co-volume edges (no clique) | Legibilidad; clique escala O(n²) |
| AD-13.2 | Mermaid client-side render, librería vendoreada | No introducir Node en runtime |
| AD-13.3 | Pseudo-proyecto `(unmanaged)` opt-in via query param | Reduce ruido por defecto; cubre 100% del host con 1 toggle |
| AD-13.4 | Read-only en `/api/projects/*`; mutations vía routers existentes | Reusa RBAC + audit + denylist sin duplicar lógica |
| AD-13.5 | Projects pasa a ser landing (`#/`) | UX: el usuario quiere ver "qué hay" antes que la lista plana |
| AD-13.6 | Aggregate status sin re-inspect (heurística sobre `state` de list) | Mantener p95 < 1s; precisión "down vs stopped" no es crítica para UX |
| AD-13.7 | Network `bridge` default omitida del grafo | Casi todos los containers están ahí; no aporta info |
