# BackOffice — Constitution

> Principios **inmutables** que aplican a toda decisión de diseño, implementación y evolución de la feature BackOffice. Cualquier desviación debe ser justificada explícitamente en el `design.md` con sección "Constitution Violations".

Versión: 0.1.0 · Estado: Draft · Última actualización: 2026-05-09

---

## Artículo I — Coherencia con el repo `lg-labs/infrastructure`

1. **Despliegue exclusivamente vía Docker Compose v2.** No se introduce Kubernetes, Helm ni Terraform.
2. Cada servicio nuevo vive en una subcarpeta de `backoffice/` con su propio `docker-compose.yml` y `.env` hermano.
3. La feature se opera mediante targets en el `Makefile` raíz siguiendo el patrón existente:
   - `docker-backoffice-up`, `docker-backoffice-down`, `docker-backoffice-down-vol`
   - Alias amigables: `backoffice-up`, `backoffice-down`, `backoffice-clean`
   - Inclusión en `all-up` / `all-down` / `all-clean`.
4. El `README.md` raíz debe documentar URL, credenciales y comandos del nuevo stack.

## Artículo II — Naming conventions

1. `COMPOSE_PROJECT_NAME=lg-infra-backoffice`
2. Containers prefijados con `lg-infra-backoffice-<rol>` (ej. `lg-infra-backoffice-app`, `lg-infra-backoffice-db`).
3. Networks Docker prefijadas con `lg-` (ej. `lg-backoffice`).
4. Variables de entorno: `BACKOFFICE_VERSION`, `BACKOFFICE_PORT`, `BACKOFFICE_USER`, `BACKOFFICE_PASS`, `BACKOFFICE_MEM_LIMIT`.
5. Si publica eventos a Kafka, topics con namespace versionado: `backoffice.1.0.event.<accion>`.

## Artículo III — Credenciales de laboratorio

1. Credenciales por defecto: usuario `lglabs` / password `lgpass` (consistente con el resto del repo).
2. Estas credenciales **no son seguras** y solo aplican a entornos locales. Cualquier mención de "producción" queda fuera de alcance.
3. Secretos sensibles (tokens externos, API keys) **nunca** se commitean; van en `.env` ignorado por git.

## Artículo IV — Operabilidad

1. Todo container **debe** tener `healthcheck` declarado.
2. Dependencias entre containers usan `depends_on: condition: service_healthy`.
3. Todo container **debe** declarar `deploy.resources.limits.memory`.
4. Configuraciones se montan como volúmenes `:ro` cuando es posible.
5. Bootstrap declarativo vía init containers (patrón `setup`/`init-kafka`/`sonar_api` del repo).

## Artículo V — Reutilización antes que duplicación

1. Si la feature necesita Postgres, **debe** evaluarse primero usar `databases/postgres` vía network externa antes de levantar uno propio.
2. Si la feature necesita observabilidad, debe integrarse con el stack existente (`elk/`, `grafana-loki/`, `prometheus/`) en lugar de añadir herramientas nuevas.
3. Si necesita autenticación SSO en el futuro, evaluar añadir un stack `auth/` (Keycloak) reutilizable, no embeber auth propietaria.

## Artículo VI — Soberanía del usuario sobre las acciones destructivas

1. Cualquier operación que modifique datos de negocio o estado de infra **debe** requerir confirmación explícita en la UI.
2. Toda acción destructiva (delete, restart, drop topic, etc.) **debe** quedar registrada en un audit log persistente.
3. El BackOffice **nunca** ejecuta acciones automáticas sin intervención humana en su versión inicial.

## Artículo VII — SDD Spec-anchored

1. Los specs (`requirements.md`, `design.md`, `tasks.md`) viven junto al código en `backoffice/specs/` y se mantienen **sincronizados** con la implementación.
2. Todo cambio funcional empieza por actualizar el spec correspondiente antes de tocar código.
3. Los specs son revisados como parte del PR igual que el código.

## Artículo VIII — Iteración pequeña

1. La primera entrega es un **MVP delgado**: una sola capability end-to-end funcionando, no las cuatro intenciones a la vez.
2. Las demás capabilities (operar infra, admin datos, soporte, feature flags) se incorporan en iteraciones posteriores, cada una con su propio ciclo SDD.

---

## Cambios a esta Constitution

Modificar este documento requiere acuerdo explícito y bump de versión. Los cambios deben listarse al pie:

- `0.1.0` (2026-05-09): Versión inicial draft.
