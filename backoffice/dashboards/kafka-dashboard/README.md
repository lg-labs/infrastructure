# Kafka Dashboard

> Microfrontend bajo el BackOffice (`/kafka/`). Gestión declarativa de **topics**, **schemas** y **ACL-metadata** del cluster Kafka de `lg-labs`. SSO + roles heredados del BackOffice. Audit unificado en `backoffice-audit-*`.

## Quickstart

El sub-stack arranca **automáticamente** con el BackOffice (incluido vía `include:` en `backoffice/docker-compose.yml`). No tiene comando `make` propio por diseño.

```bash
make elk-up            # pre-req
make kafka-up          # pre-req
make backoffice-up     # incluye kafka-dashboard
```

> 👋 **[Kafka Dashboard, Port:8080/kafka/](http://localhost:8080/kafka/)**
>
> _4 usuarios seed (admin / operator / support / viewer):_
> Username: `lglabsadmin` (o `lglabsoperator`, `lglabssupport`, `lglabsviewer`)
> Password: `lgpass`

😴 **Stop** (mantiene volúmenes):
```bash
make backoffice-down
```
⛔️ **Destroy** (borra `backoffice-kafka-dashboard-data`):
```bash
make backoffice-clean
```

## Arquitectura (resumen)

```
Browser ──:8080──▶ nginx-gateway ──/kafka/────▶ kafka-dashboard-fe   (nginx + Alpine)
                                  ──/kafka/api/▶ kafka-dashboard-bff (FastAPI)
                                                      │
                                                      ├─▶ Kafka brokers (admin client)
                                                      ├─▶ Schema Registry (HTTP)
                                                      ├─▶ SQLite (vol kafka-dashboard-data)
                                                      └─▶ NDJSON → vol backoffice-audit-logs ─▶ Filebeat ─▶ Logstash ─▶ ES
```

| Pieza | Tecnología | Carpeta |
|---|---|---|
| Frontend | HTML + Alpine.js + Tailwind (vendored, sin build) | `frontend/` |
| BFF | FastAPI + kafka-python + httpx + sqlmodel + PyYAML | `bff/` |
| Persistencia | SQLite, volumen `backoffice-kafka-dashboard-data` | (volumen) |
| Audit sink | Volumen compartido `backoffice-audit-logs` → ELK | (volumen) |

## Roles (heredados del BackOffice)

| Rol | Topics | Schemas | ACL-metadata | Export |
|---|---|---|---|---|
| `admin`    | CRUD | CRUD | **CRUD** | ✅ |
| `operator` | CRUD | CRUD | leer | ✅ |
| `support`  | leer | leer | leer | ❌ |
| `viewer`   | leer | leer | leer | ❌ |

## Documentación

| Archivo | Propósito |
|---|---|
| [`docs/user-guide.es.md`](docs/user-guide.es.md) | **Manual completo** (usuario + operador) — ES |
| [`docs/user-guide.en.md`](docs/user-guide.en.md) | Mirror inglés |
| `specs/CONSTITUTION-addendum.md` | Anexo a la constitution del BackOffice |
| `specs/requirements.md` | Qué hace el dashboard (US + criterios de aceptación) |
| `specs/design.md` | Cómo está diseñado (contratos API, modelo SQLite, audit) |
| `specs/tasks.md` | Plan de implementación (Fases A–H) + estado |
| `specs/smoke-tests.md` | Tests reproducibles (B7, C, F live) |

## Smoke tests

```bash
# Pre-req: stack levantado (make backoffice-up)
bash bff/tests/scripts/smoke-c.sh   # CRUD topics + RBAC end-to-end
bash bff/tests/scripts/smoke-f.sh   # Audit pipeline E2E (BFF → Filebeat → Logstash → ES)
bash bff/tests/scripts/smoke-b7.sh  # Audit middleware → SQLite
```

CI: job `kafka-dashboard-smoke` en `.github/workflows/test-dotfiles.yml` (manual / scheduled).

## Integración con el BackOffice

- Ruta gateway: `/kafka/` (UI) + `/kafka/api/` (BFF). No expone puerto host.
- SSO: oauth2-proxy headers `X-Auth-Request-{User,Email,Groups}` consumidos en BFF (`require_admin` / `require_writer`).
- RBAC en **dos capas**: nginx-gateway (filtro por header) + FastAPI dependencies (defense-in-depth).
- Tarjeta en home BackOffice (`/`) visible para los 4 roles.
- Audit log → mismo índice ES `backoffice-audit-*` que oauth2-proxy, discriminado por campo `audit_source: "kafka-dashboard-bff"`.
