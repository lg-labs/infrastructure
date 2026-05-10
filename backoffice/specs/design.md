# BackOffice — Design (MVP: C5 + C6 + C2)

> Documento técnico. Define **cómo** se construye lo aprobado en `requirements.md` v0.3.0. Todo lo aquí descrito debe respetar `CONSTITUTION.md`.

Versión: 0.2.0 · Estado: MVP Implemented · Última actualización: 2026-05-10

> **Cambios v0.1.0 → v0.2.0**: añadidas §13.1 (basepaths Phase D), §13.2 (race condition de networks), §13.3 (gotchas Phase E: quoting de oauth2-proxy, ruteo Logstash, init Kibana), §13.4 (tabla de artefactos finales del audit pipeline). Marcado TBD-Design-1 como resuelto y TBD-Design-4 como bloqueado por licencia.

---

## 1. Resumen ejecutivo

El MVP es **C5 (Auth con roles) + C6 (Audit log) + C2 (Operar infra existente)**. La capability dominante es C2 (operar Kafka, Docker, ELK desde una sola UI), no CRUD de datos.

**Decisión central**: ningún tool admin OSS de propósito general (Retool, Appsmith, Directus, NocoDB, Forest) está pensado para operar infra (Kafka topics, restart de containers, búsqueda en ELK). Están orientados a CRUD sobre BBDD. Por tanto, "tool open-source" para este MVP **no significa un admin builder**, significa **componer dashboards open-source ya existentes** detrás de un **reverse-proxy con SSO** que aporta auth+roles+audit unificado.

## 2. Evaluación de opciones (ADR resumido)

| Opción | C5 Auth/Roles | C6 Audit | C2 Operar infra | Esfuerzo | Veredicto |
|---|---|---|---|---|---|
| **A. Retool OSS / Appsmith** | Sí (built-in) | Parcial (audit interno) | Mal — requiere construir cada panel a mano contra APIs de Kafka/Docker/ELK | Alto | **Rechazada**: paga complejidad de un app builder pero igual hay que construirlo todo |
| **B. Directus / NocoDB** | Sí | Sí | No aplica — son DB-first | Alto | **Rechazada**: el MVP no es CRUD de datos |
| **C. Build custom (Next.js/Nest)** | Sí | Sí | Sí, pero hay que construir | Muy alto | **Rechazada por Constitution Art. VIII** (iteración pequeña) |
| **D. Reverse proxy + SSO + UIs OSS existentes** | Sí (delegada a IdP) | Sí (logs del proxy → ELK) | Sí: AKHQ ya existe (Kafka), Portainer CE (Docker), Kibana ya existe (ELK) | **Bajo** | **ELEGIDA** |

**Decisión**: Opción D. Reutilizamos al máximo la infra del repo y solo añadimos **dos piezas nuevas**: un IdP ligero y un reverse proxy con SSO.

## 3. Componentes propuestos

```
                            ┌─────────────────────────────┐
   Browser ── HTTPS ───►   │  oauth2-proxy (reverse proxy)│ ── audit log ──► ELK (existente)
                            │   • valida sesión OIDC      │
                            │   • inyecta cabeceras user/ │
                            │     roles a upstreams        │
                            └──────┬───────────┬──────────┘
                                   │           │
                ┌──────────────────┼───────────┼─────────────────────┐
                ▼                  ▼           ▼                     ▼
          ┌──────────┐     ┌──────────────┐ ┌──────────┐    ┌────────────────┐
          │  Home    │     │  AKHQ        │ │ Portainer│    │ Kibana         │
          │  (nginx  │     │ (existente,  │ │ CE (NEW) │    │ (existente,    │
          │  static) │     │  ya en repo) │ │          │    │  ya en repo)   │
          │   (NEW)  │     └──────┬───────┘ └────┬─────┘    └────────┬───────┘
          └──────────┘            │              │                   │
                                  ▼              ▼                   ▼
                              Kafka (3 brokers)   docker.sock    Elasticsearch
                              [existente]         (mount ro+rw)  [existente]

         ┌────────────────────────────┐
         │ Keycloak (NEW)             │ ← IdP local con realm `lglabs`
         │  • users + roles           │   roles: admin, operator, support, viewer
         │  • emite OIDC tokens       │
         └────────────────────────────┘
```

### 3.1 Piezas nuevas (a construir)

| Componente | Imagen | Por qué |
|---|---|---|
| **Keycloak** | `quay.io/keycloak/keycloak` | IdP que provee C5 (auth + roles) sin acoplar a credenciales de cada UI. Realm pre-aprovisionado vía `--import-realm`. |
| **nginx-gateway** | `nginx:alpine` | **Punto de entrada único** (`:8080`). Hace dos cosas: (a) sirve la home estática con tarjetas filtradas por rol, (b) actúa como reverse proxy que delega autenticación a oauth2-proxy via `auth_request` y aplica autorización por path consultando `/oauth2/auth?allowed_groups=<rol>`. |
| **oauth2-proxy** | `quay.io/oauth2-proxy/oauth2-proxy` | Sidecar de auth. Una sola instancia; las decisiones de autorización por upstream las hace nginx vía `?allowed_groups=`. Emite logs JSON de cada `auth_request` que alimentan C6. |
| **Portainer CE** | `portainer/portainer-ce` | Cubre la parte de "ver/reiniciar containers" de C2 (US-2.2). Monta `/var/run/docker.sock`. |
| **Audit collector** | reutiliza Filebeat existente | Envía logs JSON de oauth2-proxy a Elasticsearch en índice `backoffice-audit-*`. |

### 3.2 Piezas reutilizadas (sin tocar)

- **AKHQ** (ya en `kafka/`) → US-2.1 (ver topics, lag).
- **Kibana** (ya en `elk/`) → US-2.3 (búsqueda de logs) + visualización de audit log.
- **Elasticsearch** (ya en `elk/`) → backend del audit log.

## 4. Mapeo Capability → Componente

| User Story | Componente que la satisface |
|---|---|
| US-5.1 Login | Keycloak + oauth2-proxy |
| US-5.2 Gestión usuarios BackOffice | Keycloak Admin Console (UI built-in) |
| US-5.3 Visibilidad por rol | Home estática filtra tarjetas según claims OIDC; oauth2-proxy bloquea upstream si rol no autorizado |
| US-6.1 Audit log consultable | oauth2-proxy → access log JSON → Filebeat → ES índice `backoffice-audit-*` → Kibana saved search |
| US-2.1 Estado Kafka | AKHQ (existente) |
| US-2.2 Restart containers | Portainer CE |
| US-2.3 Búsqueda logs ELK | Kibana Discover (existente) |

## 5. Modelo de roles (OIDC claims)

Realm Keycloak `lglabs` con realm-roles:

| Rol | Acceso |
|---|---|
| `admin` | Home, AKHQ, Portainer (full), Kibana, Keycloak Admin |
| `operator` | Home, AKHQ, Portainer (restart only), Kibana |
| `support` | Home, Kibana (read-only saved searches) |
| `viewer` | Home, Kibana (read-only) |

Mapeo a oauth2-proxy: una instancia, autorización en el `nginx-gateway` consultando el header `X-Auth-Request-Groups` que oauth2-proxy inyecta tras `auth_request`.

### 5.1 Patrón de autorización en nginx (Fase C — implementado)

El uso directo de `?allowed_groups=` en `auth_request` falla porque nginx URL-encodea el `?` y oauth2-proxy no parsea el query string. Tampoco se puede usar `if ($groups !~ ...)` directamente en la misma `location` que `auth_request`, porque `if` corre en la fase **rewrite** (antes de `access`, donde se ejecuta `auth_request`), por lo que `$groups` aún está vacío.

**Solución implementada**: cada upstream tiene dos `location`s — una pública con `auth_request` que hace `try_files /__nonexistent__ @do_X`, y una `internal` `@do_X` donde el `if ($groups !~ "...")` ya tiene la variable poblada. Si el regex no matchea, devuelve 403; si matchea, hace `proxy_pass` al upstream real.

```nginx
location /akhq/ {
    auth_request     /oauth2/auth;
    auth_request_set $groups $upstream_http_x_auth_request_groups;
    try_files /__nonexistent__ @do_akhq;
}
location @do_akhq {
    internal;
    if ($groups !~ "(^|,)(admin|operator)(,|$)") { return 403; }
    error_page 403 = @forbidden_page;
    rewrite ^ /stub/akhq break;
    proxy_pass http://127.0.0.1:8081;
}
```

### 5.2 JWT bearer para tests automatizados (Fase C — implementado)

Para permitir tests E2E sin browser, oauth2-proxy acepta `Authorization: Bearer <jwt>`. Configuración:

- `skip_jwt_bearer_tokens = true`
- `extra_jwt_issuers = "http://keycloak:8080/realms/lglabs=oauth2-proxy"` (issuer **interno**, JWKS reachable desde el contenedor)
- Realm tiene un `oidc-audience-mapper` que añade `aud=oauth2-proxy` al access_token (oauth2-proxy lo exige).
- Smoke tests obtienen el token vía `docker exec` contra `keycloak:8080` para que `iss` matchee.
- nginx-gateway forwardea `proxy_set_header Authorization $http_authorization` en la subrequest a `/oauth2/auth`.

## 6. Audit log (C6) — diseño concreto

- oauth2-proxy emite `request_logging_format` JSON con: `timestamp`, `user`, `groups`, `method`, `path`, `upstream`, `status`, `client_ip`.
- Filebeat (existente, en `elk/`) tiene un nuevo input que lee el log file mountado en volumen `backoffice-audit-logs`.
- Pipeline de ingesta crea el índice `backoffice-audit-YYYY.MM.DD`.
- ILM policy: hot 7d → warm 30d → delete 365d (NF resuelve CLARIF-3 por default a 1 año).
- Saved search en Kibana: "BackOffice Audit", filtrable por usuario/path/upstream.

**Nota**: este audit captura el **acceso a las UIs y a sus APIs** vía proxy. Las acciones internas hechas dentro de Portainer/AKHQ que no pasen por el proxy quedan fuera del audit. Documentado como limitación conocida; aceptable para MVP.

## 7. Networking

- Network nueva: `lg-backoffice` (bridge).
- Networks **externas reutilizadas** (declaradas como `external: true` en el compose): `lg-kafka` (definida en `kafka/docker-compose.yml`) y `elastic` (definida en `elk/docker-compose.yml` — ojo: nombre histórico, no sigue el prefijo `lg-`).
- Puertos host (siguiendo patrón del repo, evitando colisiones con 3000/5601/9000/9080):
  - `8080` → oauth2-proxy (entry point único `http://localhost:8080`)
  - `8083` → Keycloak admin (8081/8082 estaban ocupados en el host de referencia)
  - `9001` → Portainer (no expuesto fuera de red interna en runtime; solo durante setup)

> [TBD-Design-1] ~~Validar puerto 8080/8081/9001 libres en tu máquina.~~ **Resuelto Fase B**: Keycloak movido a 8083 por colisión con procesos locales.

## 8. Persistencia

| Volumen | Contenido | `down` | `down --volumes` |
|---|---|---|---|
| `backoffice-keycloak-data` | Realm, users, roles | conserva | borra |
| `backoffice-portainer-data` | Settings de Portainer | conserva | borra |
| `backoffice-audit-logs` | Logs raw del proxy antes de Filebeat | conserva | borra |
| Índice ES `backoffice-audit-*` | Audit estructurado | conserva (vol del stack ELK) | depende del stack ELK |

Cumple **NF-4** (audit sobrevive a `down`).

## 9. Bootstrap declarativo

Init containers (patrón del repo `setup`/`init-kafka`/`sonar_api`):

1. ~~`keycloak-init`~~ **Reemplazado por `--import-realm` nativo de Keycloak** (Implementation note Fase B): el realm `realm-lglabs.json` se monta en `/opt/keycloak/data/import/` y Keycloak lo importa al startup de forma idempotente (omite si el realm existe). Esto elimina un container y reduce footprint.
2. `kibana-init`: crea index pattern `backoffice-audit-*`, ILM policy y saved search "BackOffice Audit". Idempotente (chequea si existen).

## 10. Estructura de archivos

```
backoffice/
├── CONSTITUTION.md
├── README.md                       (instrucciones, comandos, URLs)
├── docker-compose.yml
├── .env                            (NO commiteado; .env.example sí)
├── .env.example
├── specs/
│   ├── requirements.md
│   ├── design.md                   (este archivo)
│   └── tasks.md
├── keycloak/
│   ├── realm-lglabs.json           (importado por keycloak-init)
│   └── init.sh
├── oauth2-proxy/
│   └── oauth2-proxy.cfg
├── home/
│   ├── nginx.conf
│   └── html/
│       └── index.html              (landing con tarjetas por rol)
└── kibana-init/
    └── setup-audit.sh
```

## 11. Cambios fuera de `backoffice/`

- `Makefile` raíz: añadir `docker-backoffice-{up,down,down-vol}` + alias `backoffice-{up,down,clean}` + sumar a `all-*`. Corregir el typo `PROMETHUEUS` y la duplicación postgres como side cleanup.
- `README.md` raíz: nueva sección BackOffice con URL `http://localhost:8080`, creds seed y comandos.
- `.github/workflows/test-dotfiles.yml`: añadir smoke test `make backoffice-up`.
- `elk/`: añadir un volumen compartido para que Filebeat pueda leer `backoffice-audit-logs`. **Cambio mínimo, documentado**.

## 12. Constitution check

| Artículo | Cumple | Nota |
|---|---|---|
| I — Compose only | ✅ | |
| II — Naming | ✅ | `lg-infra-backoffice-*`, `lg-backoffice` network |
| III — Creds `lglabs/lgpass` | ✅ | Para usuarios seed por rol |
| IV — Healthchecks + memory limits | ✅ | Todos los containers nuevos |
| V — Reutilización | ✅ | AKHQ, Kibana, ES, Filebeat reutilizados |
| VI — Confirmación + audit | ⚠️ | "Confirmación destructiva" depende de Portainer (la trae built-in). Audit sí. |
| VII — Spec-anchored | ✅ | Specs en `backoffice/specs/` |
| VIII — Iteración pequeña | ✅ | MVP de 1 capability + bases (auth/audit) |

**Violaciones**: ninguna bloqueante. La nota del Art. VI se acepta porque los UIs reutilizados (Portainer, AKHQ) ya proveen confirmación nativa.

## 13. Riesgos y limitaciones conocidas

- **R1**: oauth2-proxy no audita acciones internas de Portainer/AKHQ (solo el acceso al proxy). Mitigación: Portainer tiene su propio activity log; en iteración futura ingestar también ese log a ES.
- **R2**: Acoplar Filebeat al volumen del proxy crea dependencia entre stacks `backoffice` y `elk`. Mitigación: documentar en README que `make all-up` es el camino feliz.
- **R3**: Keycloak es relativamente pesado (~500 MB RAM). Vigilar **NF-2** (≤2 GB total). Plan B: cambiar a `dexidp/dex` si se excede.
- **R4 (Fase D)**: **Kibana NO comparte SSO con Keycloak**. El cluster está en licencia `basic`, lo que excluye `xpack.security.authc.providers.oidc/saml` (Platinum+). El gateway autoriza el acceso a `/kibana/` por rol vía oauth2-proxy, pero Kibana muestra su propio formulario de login (usuario `elastic` o `kibana_system`). Consecuencia: doble login para usuarios con acceso a observabilidad. Mitigaciones futuras: (a) `POST /_license/start_trial` (30 días Platinum → OIDC); (b) anonymous-auth + run-as con un user fijo de Kibana (pierde trazabilidad por usuario); (c) header-auth con proxy realm. Decisión registrada en sesión: documentar y avanzar.

### 13.1 Decisiones de Phase D — Compatibilidad con basepaths

Para que cada upstream pueda vivir bajo un subpath en el gateway:

- **AKHQ** (`/akhq/`): `MICRONAUT_SERVER_CONTEXT_PATH=/akhq` y `akhq.server.base-path: /akhq` en `lg-infra-kafka` compose.
- **Kibana** (`/kibana/`): `SERVER_BASEPATH=/kibana` y `SERVER_REWRITEBASEPATH=true` en `lg-infra-elk` compose.
- **Keycloak** (`/keycloak/`): `--http-relative-path=/keycloak` en su `command`. Esto mueve **TODOS** los endpoints (incluido `/health/ready`) bajo ese prefijo, así que el healthcheck y todas las URLs de oauth2-proxy (`oidc_issuer_url`, `redeem_url`, `profile_url`, `oidc_jwks_url`, `extra_jwt_issuers`) deben incluir `/keycloak/realms/lglabs/...`.
- **Portainer** (`/portainer/`): no soporta basepath nativo. Se hace `rewrite ^/portainer/(.*) /$1 break;` en nginx. Funciona porque la API es absoluta y los assets están en `/`.

**Acoplamiento aceptado**: la Fase D **modifica los compose de `kafka/` y `elk/`** (`lg-infra-kafka/docker-compose.yml`, `lg-infra-elk/docker-compose.yml`). Documentado en §11.

### 13.2 Patrones de network

El gateway necesita estar en tres networks:
- `lg-backoffice` (interna, default)
- `lg-infra-kafka_default` (external) — para resolver `akhq:8080`
- `elastic` (external) — para resolver `kibana:5601`

**Race condition descubierta**: nginx resuelve los `upstream` al startup y crashea si los hosts no resuelven. Si los stacks externos no están arriba al levantar el gateway, hay que hacer `make all-up` o bien levantar primero `kafka` y `elk`.

### 13.3 Decisiones de Phase E — Audit pipeline

**Quoting de oauth2-proxy**: el template `request_logging_format` recibe campos como `{{.RequestURI}}` ya quotados internamente por oauth2-proxy. Envolverlos en `\"...\"` produce JSON inválido (`"path":""/oauth2/auth""`). La cfg final NO envuelve `RequestURI`. Otros campos string (Username, Client, Timestamp, RequestMethod, Upstream, Protocol) sí requieren quotes manuales.

**Ruteo en Logstash**: en lugar de un input dedicado en Filebeat con output directo a ES (R-D-§6 original), se opta por:
1. Filebeat: filestream con `tags: [backoffice-audit]` + parser ndjson, envía todo a Logstash (un único pipeline).
2. Logstash: condicional `if "backoffice-audit" in [tags]` enruta a índice `backoffice-audit-*`; resto a `logstash-*`.
   Razón: reusa la conexión TLS Filebeat→Logstash existente y evita duplicar credenciales en Filebeat.

**Init Kibana**: container `kibana-init` corre con imagen `curlimages/curl`, monta el volumen externo `lg-infra-elk_certs` (ro) para validar TLS contra ES, y usa la URL Kibana con basepath `/kibana`. Es idempotente: PUT sobre ILM/template, `override:true` en data view, `overwrite=true` en saved search.

**Limitación conocida — gap de URI original en audit log**: oauth2-proxy registra `path=/oauth2/auth` (la subrequest enviada por nginx para `auth_request`), no la URI que el cliente realmente solicitó (`/portainer/api/status`, `/akhq/...`, etc.). La URI original se propaga en el header `X-Original-URI` pero no aparece en el access log. Para auditoría completa de qué recursos accede cada usuario, en una iteración futura habría que: (a) emitir un access log de nginx-gateway al mismo volumen `backoffice-audit-logs`, o (b) usar un upstream filter en Logstash para enriquecer con campos de la subrequest.

### 13.4 Phase E — Implementación final

| Artefacto | Identificador | Notas |
|---|---|---|
| Volumen | `backoffice-audit-logs` (external) | Init `proxy-volume-init` ajusta UID 65532. Mountado en oauth2-proxy `/var/log/proxy/` y filebeat01 `/var/log/backoffice/` ro. |
| Filebeat input | id `backoffice-audit` | Filestream, ndjson, tags `backoffice-audit` |
| Logstash output | conditional | Índice `backoffice-audit-%{+YYYY.MM.dd}` |
| ILM policy | `backoffice-audit-ilm` | hot 7d (rollover 10gb) → warm 30d (shrink 1 shard, forcemerge) → delete 365d |
| Index template | `backoffice-audit` | match `backoffice-audit-*`, priority 200, mappings tipados (ip, keyword, short, long, float, date) |
| Data view | id `backoffice-audit` | name "BackOffice Audit", time field `@timestamp` |
| Saved search | id `backoffice-audit-search` | columnas user/method/path/upstream/status/client_ip/duration, query `audit_type:request` |

## 14. Lista de TBDs (no bloqueantes para Tasks)

- [x] ~~**TBD-Design-1**: validar puertos 8080/8081/9001~~ — Resuelto Fase B (Keycloak en 8083).
- [ ] **TBD-Design-2**: confirmar memory budget tras primer `make backoffice-up`
- [ ] **TBD-Design-3**: decidir si la Home estática se reemplaza más adelante por SPA con rutas dinámicas por rol
- [ ] **TBD-Design-4** (Phase D): integrar Kibana con Keycloak SSO. Bloqueado por licencia basic. Re-evaluar en una iteración futura.
