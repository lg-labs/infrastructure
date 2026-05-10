# BackOffice — Backlog post-MVP

> Mejoras y capabilities fuera del scope MVP (C5 + C6 + C2). Cada item incluye intención, requirement(s) o limitación de origen, y tamaño estimado.
>
> Versión: 0.1.0 · Última actualización: 2026-05-10

---

## A. Capabilities pendientes (de `requirements.md` §6)

### A1. C1 — CRUD de datos de negocio
- **Intención**: BackOffice escribe/lee entidades en Postgres (clientes, productos, configuraciones aplicativas).
- **Pre-requisito**: existe esquema Postgres definido por una aplicación cliente. Hoy no hay tal esquema.
- **Diseño abierto**: ¿panel admin auto-generado (Forest, AdminJS, Refine), o DSL declarativo? Componente nuevo en stack BackOffice.
- **Estimación**: 8-12h (incluye onboarding de un esquema piloto).
- **Bloqueado por**: definición de esquema y datasource.

### A2. C3 — Soporte (search + acciones acotadas)
- **Intención**: usuario `support` busca entidades (por id/email/transacción) y ejecuta acciones reversibles ("reenviar email", "marcar como resuelto").
- **Pre-requisito**: A1 + catálogo de entidades soporte + lista de acciones permitidas.
- **Estimación**: 4-6h sobre A1.

### A3. C4 — Feature flags / config dinámica
- **Intención**: gestionar flags por aplicación-environment desde el BackOffice; las apps los consumen vía API/SDK.
- **Diseño abierto**: ¿servicio dedicado (Unleash, Flagd) o tabla en Postgres + endpoint propio?
- **Estimación**: 6-10h.

---

## B. Mejoras al MVP

### B1. Audit log: registrar URI original (no la subrequest de auth)
- **Origen**: design §13.3, tasks E4 limitación. Hoy `path` del audit log es siempre `/oauth2/auth` porque oauth2-proxy ve la auth-subrequest de nginx, no la URI original.
- **Opciones**:
  1. Añadir un access log estructurado al gateway nginx, escrito al volumen `backoffice-audit-logs`. Filebeat ingesta ambos archivos con tags distintos.
  2. Filtro en Logstash que enriquece con `[fields][x-original-uri]` si Filebeat lo agrega.
- **Recomendación**: opción 1 (más limpia y desacopla de oauth2-proxy).
- **Estimación**: 2-3h.
- **Traza**: R-US-6.1 (mejora de calidad).

### B2. Kibana SSO real (cuando haya licencia ≥ Gold)
- **Origen**: design §13/R4. Limitación de licencia ES `basic`.
- **Acción**: configurar `xpack.security.authc.realms.oidc.kc.*` apuntando a Keycloak; deshabilitar el login propio de Kibana; mapear `groups` claim → roles de ES.
- **Estimación**: 4-6h (mucho de eso es validar mapping de roles).
- **Bloqueado por**: upgrade de licencia.

### B3. Race condition de networks: orden determinístico
- **Origen**: design §13.2. `make backoffice-up` falla si `kafka` o `elk` no están arriba.
- **Opciones**:
  1. Hacer `backoffice-up` dependa de `elk-up` y `kafka-up` en el Makefile.
  2. Usar `nginx` con `resolver` dinámico + `set $upstream …; proxy_pass $upstream;` para resolver en runtime.
- **Recomendación**: opción 1 (simple, alineada con la tradición del repo).
- **Estimación**: 1h.

### B4. Memory budget verificado
- **Origen**: TBD-Design-2. Aún sin medir el consumo total real del stack levantado.
- **Acción**: `docker stats` durante 5 min con tráfico sintético; documentar en design §3 / README.
- **Estimación**: 1h.

### B5. Rotación de secrets
- **Origen**: hoy `lgpass` literal en muchos sitios. OK para lab, mal para entornos compartidos.
- **Acción**: introducir `.env.local` no versionado y refactor para que todos los secretos lean de `.env`.
- **Estimación**: 2h.

### B6. Home dinámica con SPA o templates
- **Origen**: TBD-Design-3. Hoy es HTML estático con JS que muestra/oculta tarjetas leyendo `/me`.
- **Acción opcional**: SPA mínima (Alpine.js o Preact) si crece el catálogo de tarjetas.
- **Estimación**: 4h.

### B7. CI smoke ejecutado en cada PR
- **Origen**: F3 quedó como `workflow_dispatch + schedule` (pesado). Si los runners se vuelven más capaces o se introduce `services:` con docker-in-docker, mover a `pull_request`.
- **Estimación**: 2h.

---

## C. Trazabilidad inversa

| Fuente | Items |
|---|---|
| `requirements.md §6` (capabilities fuera de MVP) | A1, A2, A3 |
| `design.md §13.3` (gap de URI en audit) | B1 |
| `design.md §13/R4` (Kibana SSO) | B2 |
| `design.md §13.2` (race networks) | B3 |
| `design.md §14` TBDs | B2, B4, B6 |
| Hallazgos de implementación | B5, B7 |
