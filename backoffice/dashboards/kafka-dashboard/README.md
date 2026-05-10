# Kafka Dashboard

> Microfrontend bajo el BackOffice (ruta `/kafka/`). Gestión centralizada de topics, schemas y ACL-metadata del cluster Kafka de `lg-labs`.
>
> **Estado:** Spec-driven, en construcción. Ver `specs/`.

## Composición

| Pieza | Tecnología | Carpeta |
|---|---|---|
| Frontend | HTML + Alpine.js, sin build step | `frontend/` |
| BFF | FastAPI + kafka-python + requests (Schema Registry) | `bff/` |
| Persistencia local | SQLite en volumen `kafka-dashboard-data` | (volumen) |

## Documentación SDD

| Archivo | Propósito |
|---|---|
| `specs/CONSTITUTION-addendum.md` | Anexo a la constitution del BackOffice |
| `specs/requirements.md` | Qué hace el dashboard (US + criterios) |
| `specs/design.md` | Cómo está diseñado (contratos API, modelo SQLite, roles) |
| `specs/tasks.md` | Plan de implementación + estado |
| `specs/smoke-tests.md` | Tests reproducibles |
| `docs/user-guide.{es,en}.md` | Manuales de uso |

## Integración con el BackOffice

- Se sirve detrás del gateway en `/kafka/` (no expone puerto host)
- Hereda SSO+roles del BackOffice (oauth2-proxy headers `X-Auth-Request-*`)
- Tarjeta en la home (`/`) visible para admin/operator/support/viewer
- Audit log unificado con `backoffice-audit-*` index
