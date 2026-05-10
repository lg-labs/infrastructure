# Containers Dashboard

> Microfrontend bajo el BackOffice (`/containers/`). Gestión del **daemon Docker del host**: containers, images, volumes, networks, logs, exec shell **+ Projects view (Phase I)** con descubrimiento automático de Compose stacks y diagrama de topología renderizado con Mermaid. SSO + roles heredados del BackOffice. Audit unificado en `backoffice-audit-*`. Coexiste con Portainer (`/portainer/`).

## Capacidades (feature matrix)

| ID  | Capacidad                                       | Roles                | Endpoint(s) clave                                           |
| --- | ----------------------------------------------- | -------------------- | ----------------------------------------------------------- |
| C-A | Listar/inspeccionar containers, images, volumes, networks | viewer+ | `GET /api/containers`, `/images`, `/volumes`, `/networks`   |
| C-B | Logs y stats en vivo                            | viewer+              | `GET /api/containers/{id}/logs`, `/stats` (SSE)             |
| C-C | Start / Stop / Restart                          | admin, operator      | `POST /api/containers/{id}/{start,stop,restart}`            |
| C-D | Exec shell (WS, idle 5min)                      | admin only           | `WS /api/containers/{id}/exec`                              |
| C-E | Remove (containers, images, volumes, networks)  | admin only           | `DELETE /api/{kind}/{id}` con `X-Confirm-Resource`          |
| C-F | Audit unificado en ELK                          | (system)             | `audit_source: containers-dashboard-bff`                    |
| C-P | **Projects view + topología** (Phase I)         | viewer+              | `GET /api/projects`, `GET /api/projects/{name}` (read-only) |

## Quickstart

El sub-stack arranca **automáticamente** con el BackOffice (incluido vía `include:` en `backoffice/docker-compose.yml`).

```bash
make elk-up            # pre-req
make backoffice-up     # incluye containers-dashboard
```

> 👋 **[Containers Dashboard, Port:8080/containers/](http://localhost:8080/containers/)**
>
> _4 usuarios seed:_
> Username: `lglabsadmin` (o `lglabsoperator`, `lglabssupport`, `lglabsviewer`)
> Password: `lgpass`

😴 **Stop** (mantiene volúmenes):
```bash
make backoffice-down
```
⛔️ **Destroy**:
```bash
make backoffice-clean
```

## ⚠️ Modelo de privilegios

Este BFF tiene `docker.sock:rw` montado (igual que Portainer). Mitigación:

- **Denylist hard-coded** (HTTP 423) protege keycloak, gateway, oauth2-proxy, portainer y los propios containers del dashboard.
- **`exec` y `remove` son admin-only**; start/stop/restart son admin+operator.
- **Confirmación obligatoria** vía header `X-Confirm-Resource: <name>` (excepto Start) → 409 si no coincide.
- **Builtin networks** (`bridge`/`host`/`none`) protegidas con 403 ante DELETE.
- **Env vars sensibles** (regex `(?i)(password|secret|token|key|credential)`) redactadas a `<redacted>` server-side.

## Arquitectura (resumen)

```
Browser ──:8080──▶ nginx-gateway ──/containers/────▶ containers-dashboard-fe   (nginx + Alpine + xterm.js)
                                  ──/containers/api/▶ containers-dashboard-bff (FastAPI)
                                                            │
                                                            ├─▶ /var/run/docker.sock (rw, host daemon)
                                                            ├─▶ SQLite (vol containers-dashboard-data, audit_log table)
                                                            └─▶ NDJSON → vol backoffice-audit-logs ─▶ Filebeat ─▶ Logstash ─▶ ES
                                                                                                       (audit_source: containers-dashboard-bff)
```

| Pieza | Tecnología | Carpeta |
|---|---|---|
| Frontend | HTML + Alpine.js 3.14 + Tailwind 3.4 + xterm.js 5.3 (vendored, sin build) | `frontend/` |
| BFF | FastAPI + docker-py 7.x + sqlmodel | `bff/` |
| Persistencia | SQLite, volumen `backoffice-containers-dashboard-data` | (volumen) |
| Audit sink | Volumen compartido `backoffice-audit-logs` → ELK | (volumen) |

## Roles (heredados del BackOffice)

| Rol | List | Detail | Logs/Stats | Start/Stop/Restart | Exec | Remove |
|---|---|---|---|---|---|---|
| `admin`    | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| `operator` | ✅ | ✅ | ✅ | ✅ | — | — |
| `support`  | ✅ | ✅ | ✅ | — | — | — |
| `viewer`   | ✅ | ✅ | ✅ | — | — | — |

## Cuándo usar Containers Dashboard vs Portainer

| Caso | Usa |
|---|---|
| Operación de equipo con **audit centralizado en ELK** + RBAC SSO Keycloak | **Containers Dashboard** |
| Self-protection automática (denylist) | **Containers Dashboard** |
| Vista 360° avanzada de Docker (stacks, registry UI, gestión de templates, swarm) | **Portainer** |
| Compose stacks editor / multi-host / build pipelines | **Portainer** |

> Ambos coexisten en el mismo BackOffice (`/containers/` y `/portainer/`).

## Documentación

| Archivo | Propósito |
|---|---|
| [`docs/user-guide.es.md`](docs/user-guide.es.md) | **Manual completo** (usuario + operador) — ES |
| [`docs/user-guide.en.md`](docs/user-guide.en.md) | Mirror inglés |
| `specs/CONSTITUTION-addendum.md` | Anexo a la constitution del BackOffice |
| `specs/requirements.md` | Qué hace el dashboard (US + criterios de aceptación) |
| `specs/design.md` | Cómo está diseñado (contratos API, modelo SQLite, audit) |
| `specs/tasks.md` | Plan de implementación (Fases A–H) + estado |
| `specs/smoke-tests.md` | Tests reproducibles |
| `specs/backlog.md` | Capabilities pospuestas + tech debt + trazabilidad |

## Smoke tests

```bash
# Pre-req: stack levantado (make elk-up && make backoffice-up)
bash bff/tests/scripts/smoke-c.sh   # Read-only + RBAC (12 casos)
bash bff/tests/scripts/smoke-d.sh   # Mutations start/stop/restart (9 casos)
bash bff/tests/scripts/smoke-f.sh   # DELETE matrix (13 casos)
bash bff/tests/scripts/smoke-g.sh   # Audit pipeline E2E (BFF → Filebeat → Logstash → ES) (6 casos)
bash bff/tests/scripts/smoke-i.sh   # Phase I — Projects view + topology (9 casos)
```

CI: job `containers-dashboard-smoke` en `.github/workflows/test-dotfiles.yml` (manual / scheduled).

## Integración con el BackOffice

- Ruta gateway: `/containers/` (UI) + `/containers/api/` (BFF) + WS `/containers/api/containers/<id>/exec` (admin-only via gateway). No expone puerto host.
- SSO: oauth2-proxy headers `X-Auth-Request-{User,Email,Groups}` consumidos en BFF (`require_admin` / `require_writer` / `require_reader`). RBAC en **dos capas**: nginx-gateway (filtro por header) + FastAPI dependencies (defense-in-depth).
- WS exec: nginx valida `admin` group via `auth_request` antes del Upgrade; BFF re-valida `X-Auth-Request-Groups` como pre-check.
- Tarjeta en home BackOffice (`/`) visible para los 4 roles.
- Audit log → mismo índice ES `backoffice-audit-*` que oauth2-proxy y kafka-dashboard, discriminado por `audit_source: "containers-dashboard-bff"`.
