# BackOffice

> Stack único de administración para infra `lg-labs`. Reúne Keycloak (IdP), oauth2-proxy (SSO), nginx (gateway + autorización por rol), Portainer (gestión de contenedores) y reusa AKHQ + Kibana + Keycloak Admin como upstreams autenticados.
>
> MVP = **Auth (C5) + Audit (C6) + Operar infra existente (C2)**. Diseñado vía Spec-Driven Development; ver `specs/`.

## Estado

✅ Fase A (andamiaje) — ✅ Fase B (Keycloak) — ✅ Fase C (SSO) — ✅ Fase D (upstreams + Portainer) — ✅ Fase E (audit pipeline)

## Una sola URL

Todo el BackOffice se expone en **`http://localhost:8080`** (variable `BACKOFFICE_PORT`).

Tarjetas en la home y rutas reservadas:

| Recurso | Ruta | Visible para |
|---|---|---|
| AKHQ (Kafka) | `/akhq/` | admin, operator |
| Portainer (Docker) | `/portainer/` | admin, operator |
| Kibana (logs) | `/kibana/` | todos |
| Keycloak Admin | `/keycloak/` | admin |
| Identidad actual | `/me` | todos los autenticados |

> ⚠️ **Limitación**: Kibana no comparte SSO con el resto (la licencia `basic` de ES no incluye OIDC/SAML). El proxy autoriza por rol pero Kibana muestra su propio login (`elastic` / contraseña en `elk/.env`). Documentado en `specs/design.md` §13/R4.

## Comandos

```bash
make backoffice-up        # levanta Keycloak + oauth2-proxy + nginx + Portainer
make backoffice-down      # baja conservando volúmenes (sesiones persisten)
make backoffice-clean     # baja y borra volúmenes
```

Para validar el stack: `bash specs/smoke-tests.md` (las secciones de tests automatizados son ejecutables vía copy-paste).

## Credenciales seed (lab only)

Definidas en `keycloak/realm-lglabs.json`. **No usar en producción.**

| Usuario | Password | Rol | Acceso |
|---|---|---|---|
| `lglabsadmin` | `lgpass` | admin | todo |
| `lglabsoperator` | `lgpass` | operator | AKHQ, Portainer, Kibana |
| `lglabssupport` | `lgpass` | support | Kibana |
| `lglabsviewer` | `lgpass` | viewer | Kibana |

Admin de Keycloak: `lglabs` / `lgpass` (variables `KEYCLOAK_ADMIN_USER`/`KEYCLOAK_ADMIN_PASS` en `.env`).

## Dependencias entre stacks

Para que el MVP funcione end-to-end, los siguientes stacks deben estar arriba **antes** que `backoffice`:

```bash
make elk-up      # ES + Kibana + Filebeat + Logstash (audit + búsqueda de logs)
make kafka-up    # Kafka + AKHQ
make backoffice-up
```

O simplemente: `make all-up`.

> 🐛 **Race condition conocida** (`specs/design.md` §13.2): nginx-gateway resuelve los hostnames de los upstreams al arrancar. Si `akhq:8080` o `kibana:5601` no resuelven, el container falla. La forma segura es `make all-up`.

## Audit log

Cada request autenticada queda en el índice de Elasticsearch `backoffice-audit-YYYY.MM.DD` (ILM `backoffice-audit-ilm`: hot 7d / warm 30d / delete 365d).

En Kibana → Discover, seleccionar la **data view "BackOffice Audit"** y abrir la **saved search "BackOffice Audit"** para ver columnas user/method/path/upstream/status.

> Limitación: `path` registra `/oauth2/auth` (subrequest de auth en nginx), no la URI original del cliente. Ver `specs/design.md` §13.3.

## Documentación SDD

| Archivo | Qué es |
|---|---|
| `docs/user-guide.es.md` | **Manual de uso (español)** — usuario final + operador del stack, con diagramas Mermaid |
| `docs/user-guide.en.md` | **User guide (English)** — end user + stack operator, with Mermaid diagrams |
| `CONSTITUTION.md` | 8 principios inmutables (composición sobre invención, idempotencia, etc.) |
| `specs/requirements.md` | qué hace el BackOffice (user stories + criterios de aceptación) |
| `specs/design.md` | cómo está diseñado (componentes, redes, gotchas) |
| `specs/tasks.md` | plan de implementación + estado |
| `specs/smoke-tests.md` | tests reproducibles para validar cada fase |
| `specs/backlog.md` | mejoras post-MVP y capabilities pendientes |

## Troubleshooting

- **Puerto 8080 ya en uso**: cambiar `BACKOFFICE_PORT` en `backoffice/.env`.
- **`host not found in upstream "akhq"`**: levantar primero `make kafka-up` y `make elk-up`, luego recrear el gateway.
- **Filebeat: `Error decoding JSON`**: el `request_logging_format` de oauth2-proxy generó una línea inválida. Revisar `oauth2-proxy/oauth2-proxy.cfg` y respetar el quoting documentado en design §13.3.
- **Login funciona pero "Account is not fully set up"**: el usuario seed no tiene email. Re-aplicar `realm-lglabs.json` o setear email vía Keycloak Admin.
- **Brute force lockout**: tras 5 fallos Keycloak bloquea 15 min. Desbloquear: Keycloak Admin → users → \<usuario\> → Credentials → Reset.
