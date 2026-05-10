# BackOffice — Tasks (MVP: C5 + C6 + C2)

> Plan de implementación. Cada tarea traza a uno o más requirements (`R-*`) y/o secciones de design (`D-*`).
>
> Convenciones:
> - Tareas marcables con `[ ]` / `[x]`.
> - Cada tarea declara: **archivos a tocar**, **definición de hecho (DoD)**, **trazabilidad**.
> - Orden = orden recomendado de ejecución. Las tareas de la misma fase pueden paralelizarse si tienen agente humano distinto.

Versión: 1.0.0 · Estado: MVP Completed · Última actualización: 2026-05-10

---

## Fase A — Andamiaje del stack

### A1. Crear esqueleto de carpetas y `.env.example`
- **Archivos**: `backoffice/.env.example`, `backoffice/.gitignore`, `backoffice/keycloak/`, `backoffice/oauth2-proxy/`, `backoffice/home/html/`, `backoffice/kibana-init/`
- **DoD**: estructura del §10 del design existe. `.env` añadido a gitignore. `.env.example` con todas las variables `BACKOFFICE_*` documentadas.
- **Traza**: D-§10, Constitution Art. III

### A2. `docker-compose.yml` base (sin servicios aún) + networks
- **Archivos**: `backoffice/docker-compose.yml`
- **DoD**: declara network `lg-backoffice`, declara `lg-kafka` y `lg-elk` como `external: true`. `COMPOSE_PROJECT_NAME=lg-infra-backoffice` definido en `.env.example`.
- **Traza**: D-§7, Constitution Art. II

### A3. Targets en Makefile raíz
- **Archivos**: `Makefile` (raíz)
- **DoD**: existen `docker-backoffice-up`, `docker-backoffice-down`, `docker-backoffice-down-vol` y alias `backoffice-up/down/clean`. Sumados a `all-up/down/clean`. `BACKOFFICE=backoffice` declarado junto a las otras variables.
- **Traza**: D-§11, Constitution Art. I

---

## Fase B — Identidad (C5)

### B1. Servicio Keycloak en compose
- **Archivos**: `backoffice/docker-compose.yml`
- **DoD**: container `lg-infra-backoffice-keycloak` arriba con healthcheck, memory limit, puerto host `8081`, volumen `backoffice-keycloak-data`. Variables `KEYCLOAK_VERSION`, `KEYCLOAK_PORT`, `KEYCLOAK_MEM_LIMIT` en `.env.example`.
- **Traza**: R-US-5.1, R-US-5.2, D-§3.1, Constitution Art. IV

### B2. Realm `lglabs` con 4 roles + 4 usuarios seed
- **Archivos**: `backoffice/keycloak/realm-lglabs.json`, `backoffice/keycloak/init.sh`
- **DoD**: import del realm es **idempotente** (no falla si ya existe). Realm `lglabs` con realm-roles `admin/operator/support/viewer` y un usuario por rol con creds `lglabs<rol>/lgpass`. Cliente OIDC `oauth2-proxy` con `valid-redirect-uris=http://localhost:8080/oauth2/callback`.
- **Traza**: R-US-5.2, D-§5, D-§9.1

### B3. Init container `keycloak-init`
- **Archivos**: `backoffice/docker-compose.yml`
- **DoD**: depende de Keycloak healthy, monta `realm-lglabs.json` ro, ejecuta `init.sh`, exit 0 al terminar.
- **Traza**: D-§9.1, Constitution Art. IV

---

## Fase C — Reverse proxy con SSO (C5 + base de C6) — ✅ Completada

### C1. Servicio oauth2-proxy en compose — [x]
- **Archivos**: `backoffice/docker-compose.yml`, `backoffice/oauth2-proxy/oauth2-proxy.cfg`
- **DoD**: container `lg-infra-backoffice-proxy` arriba en puerto host `8080`, OIDC apuntando a Keycloak realm `lglabs`, `request_logging_format` JSON con campos del §6. Healthcheck `/ping`. Memory limit declarado.
- **Traza**: R-US-5.1, R-US-5.3, D-§3.1, D-§6

### C2. Reglas de upstream + autorización por rol — [x]
- **Archivos**: `backoffice/home/nginx.conf` (autorización movida a nginx — ver design §5.1)
- **DoD**: rutas `/akhq/`, `/portainer/`, `/kibana/`, `/keycloak/` con stub responses validando matriz de roles; 403 cuando rol no autorizado. Validado E2E con bearer tokens.
- **Traza**: R-US-5.3, D-§5, D-§5.1

### C3. Tests manuales de auth (smoke) — [x]
- **Archivos**: `backoffice/specs/smoke-tests.md`
- **DoD**: documentadas las pruebas: anonymous → 302, lockout tras 5 intentos fallidos (Keycloak BFP), groups claim por rol, matriz de autorización 200/403. Tests automatizados pasan.
- **Traza**: R-US-5.1 (criterio lockout), R-US-5.3

---

## Fase D — Home y composición (C2) — ✅ Completada

### D1. Servicio Portainer CE — [x]
- **Archivos**: `backoffice/docker-compose.yml`
- **DoD**: container `lg-infra-backoffice-portainer` con docker.sock montado (ro), no expone puerto al host (solo accesible vía proxy en `/portainer/`). Volumen `backoffice-portainer-data`. Healthcheck (`/api/status`) + memory limit 256m. Verificado: `/portainer/api/status` responde con `Version 2.21.4`.
- **Traza**: R-US-2.2, D-§3.1

### D2. Home estática (nginx) — [x]
- **Archivos**: `backoffice/home/nginx.conf`, `backoffice/home/html/index.html`
- **DoD**: gateway nginx sirve `/` con tarjetas a AKHQ, Portainer, Kibana, Keycloak Admin. Tarjetas se muestran/ocultan vía JS leyendo `/me` (que devuelve `groups` desde headers de oauth2-proxy). Pendiente verificación visual en browser (smoke-tests §2.1).
- **Traza**: R-US-5.3, D-§3.1, D-§4

### D3. Conectar gateway a AKHQ, Kibana, Keycloak Admin — [x]
- **Archivos**: `backoffice/home/nginx.conf`, `backoffice/docker-compose.yml`, `kafka/docker-compose.yml`, `elk/docker-compose.yml`, `backoffice/oauth2-proxy/oauth2-proxy.cfg`
- **DoD**: gateway unido a networks `lg-infra-kafka_default` y `elastic`. AKHQ accesible vía `/akhq/` (config `MICRONAUT_SERVER_CONTEXT_PATH=/akhq` en kafka stack). Kibana en `/kibana/` (config `SERVER_BASEPATH=/kibana` + `SERVER_REWRITEBASEPATH=true`). Keycloak Admin en `/keycloak/` (`--http-relative-path=/keycloak`). Validado E2E: AKHQ retorna clusters reales y topics, Portainer retorna API status, Keycloak Admin Console redirige a su login.
- **Limitación**: Kibana no comparte SSO (licencia ES `basic`); muestra su propio login. Documentado en design §13/R4.
- **Traza**: R-US-2.1, R-US-2.3, D-§7, D-§13.1, D-§13.2

---

## Fase E — Audit log (C6) — ✅ Completada

### E1. Volumen compartido `backoffice-audit-logs` — [x]
- **Archivos**: `backoffice/docker-compose.yml`, `elk/docker-compose.yml`
- **DoD**: volumen externo `backoffice-audit-logs` declarado en ambos composes; oauth2-proxy escribe `/var/log/proxy/oauth2-proxy.log` (init container `proxy-volume-init` ajusta permisos UID 65532), Filebeat lo lee ro en `/var/log/backoffice/`.
- **Traza**: D-§8, D-§11

### E2. Input Filebeat para audit — [x]
- **Archivos**: `elk/filebeat.yml`, `elk/logstash.conf`
- **DoD**: filestream input `backoffice-audit` parsea ndjson, agrega `tags: [backoffice-audit]`. Logstash enruta condicionalmente a índice `backoffice-audit-%{+YYYY.MM.dd}`. `request_logging_format` corregido (oauth2-proxy quota internamente `{{.RequestURI}}` — ver design §13.3).
- **Traza**: R-US-6.1, D-§6

### E3. Init container `kibana-init` — [x]
- **Archivos**: `backoffice/kibana-init/setup-audit.sh`, `backoffice/docker-compose.yml`
- **DoD**: idempotente. Crea: ILM policy `backoffice-audit-ilm` (hot 7d / warm 30d / delete 365d), index template `backoffice-audit` con mappings tipados, data view `backoffice-audit` (`title: backoffice-audit-*`, `@timestamp`), saved search `backoffice-audit-search` ("BackOffice Audit") con columnas user/method/path/upstream/status/client_ip/duration y query `audit_type:request`. Volumen externo `lg-infra-elk_certs` montado ro para CA.
- **Traza**: R-US-6.1, D-§6, D-§9.2

### E4. Validar trazabilidad end-to-end — [x]
- **Archivos**: `backoffice/specs/smoke-tests.md` (TODO: añadir caso)
- **DoD**: ejecutar acciones autenticadas (login admin → bearer token, GET `/me`, GET `/portainer/api/status`, GET `/akhq/api/cluster`) y verificar que cada subrequest de auth aparece en índice `backoffice-audit-*` con `user=lglabsadmin@lglabs.local`, `status=202`, `audit_type=request` en ≤ 30s. Validado: 49 docs no-anónimos en ES, traza `user → method → path → status` completa.
- **Limitación conocida**: oauth2-proxy registra `path=/oauth2/auth` (la subrequest de auth), no la URI original del cliente. La URI original se pasa como header `X-Original-URI` pero no aparece en el access log. Mejora futura: emitir access log de nginx-gateway al mismo volumen compartido. Ver backlog.
- **Traza**: R-US-6.1

---

## Fase F — Documentación e integración con repo — ✅ Completada

### F1. README del stack BackOffice — [x]
- **Archivos**: `backoffice/README.md`
- **DoD**: documenta URL única (8080), 4 usuarios seed con tabla de roles/acceso, comandos `make backoffice-{up,down,clean}`, troubleshooting (puerto en uso, host not found, JSON decode, lockout BFP, "Account is not fully set up"), nota sobre dependencia de `elk/` y `kafka/`, audit log y limitaciones (Kibana SSO, gap URI original).
- **Traza**: Constitution Art. I.4

### F2. Sección en README raíz — [x]
- **Archivos**: `README.md` (raíz)
- **DoD**: nueva sección "Start with BackOffice" con URL, los 4 usuarios seed, comandos up/down/clean en el mismo estilo de las demás secciones; link reference `[backoffice]` y `[backoffice-doc]` añadidos.
- **Traza**: Constitution Art. I.4

### F3. Smoke test en CI — [x]
- **Archivos**: `.github/workflows/test-dotfiles.yml`
- **DoD**: nuevo job `backoffice-smoke` en `ubuntu-latest` (Docker nativo) ejecutado solo en `workflow_dispatch` y `schedule` (no en cada PR — el stack es pesado). Levanta elk + kafka + backoffice, verifica anonymous → 302 en 6 paths, obtiene token de admin y verifica `/me` → 200 con bearer. Cleanup `make all-clean` siempre. Dump de logs en failure.
- **Traza**: Constitution Art. I (CI existente)

### F4. Side cleanup del Makefile — [x]
- **Archivos**: `Makefile`
- **DoD**: el typo `PROMETHUEUS` y la duplicación `postgres-*` mencionados en la ficha original ya estaban resueltos (análisis estaba desactualizado). Limpieza adicional: artefacto de shell prompt en `elk-crt:` (línea 20).
- **Traza**: hallazgos del análisis inicial

---

## Fase G — Cierre del ciclo SDD — ✅ Completada

### G1. Actualizar specs con lo realmente implementado — [x]
- **Archivos**: `backoffice/specs/requirements.md`, `backoffice/specs/design.md`
- **DoD**: `requirements.md` v0.3.0 ("MVP Implemented") con nota de cambios y limitaciones reales documentadas. `design.md` v0.2.0 ("MVP Implemented") con nota de cambios apuntando a §13.1–§13.4. TBDs resueltos (Design-1) o explícitamente bloqueados (Design-4).
- **Traza**: Constitution Art. VII (Spec-anchored)

### G2. Definir backlog para próxima iteración — [x]
- **Archivos**: `backoffice/specs/backlog.md` (nuevo)
- **DoD**: priorizado en 3 secciones: A (capabilities A1=C1, A2=C3, A3=C4 con estimaciones y bloqueos), B (mejoras al MVP: B1 audit URI gap, B2 Kibana SSO, B3 race networks, B4 memory budget, B5 secrets rotation, B6 SPA home, B7 CI en cada PR), C (trazabilidad inversa contra requirements/design/TBDs).
- **Traza**: requirements §6 (capabilities fuera de MVP)

---

## Trazabilidad inversa (Requirement → Tareas)

| Requirement | Tareas |
|---|---|
| R-US-5.1 Login | B1, B2, C1, C3 |
| R-US-5.2 Gestión usuarios | B1, B2 |
| R-US-5.3 Visibilidad por rol | C2, D2, C3 |
| R-US-6.1 Audit log | E1, E2, E3, E4 |
| R-US-2.1 Estado Kafka | D3 |
| R-US-2.2 Restart containers | D1 |
| R-US-2.3 Búsqueda logs ELK | D3 |
| NF-1 ≤ 2 min up | A2, F1 (verificar) |
| NF-2 ≤ 2 GB RAM | B1, C1, D1, D2 (memory limits) + verificación final |
| NF-4 Audit sobrevive a `down` | E1 |

## Estimación gruesa

| Fase | Esfuerzo (h, dev experimentado) |
|---|---|
| A | 1-2 |
| B | 3-4 |
| C | 3-4 |
| D | 4-6 |
| E | 3-4 |
| F | 1-2 |
| G | 1 |
| **Total MVP** | **16-23 h** |
