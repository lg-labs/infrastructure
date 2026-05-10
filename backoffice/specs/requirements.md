# BackOffice — Requirements

> Documento funcional. Describe **qué** hace el BackOffice, no **cómo**. Decisiones técnicas viven en `design.md`.

Versión: 0.3.0 · Estado: MVP Implemented · Última actualización: 2026-05-10

> **Cambios v0.2.0 → v0.3.0**: marca todas las US del MVP (5.1, 5.2, 5.3, 6.1, 2.1, 2.2, 2.3) como **Implementadas**. Documenta limitaciones reales descubiertas durante implementación: Kibana no comparte SSO (ES basic license — ver design §13/R4), `path` en audit log es la subrequest de auth (`/oauth2/auth`) no la URI original (ver design §13.3, mejora futura en backlog).

---

## 1. Visión

Una herramienta interna **única** que permite al equipo de `lg-labs` operar la plataforma sin necesidad de abrir múltiples UIs (Kibana, AKHQ, PgAdmin, Grafana, SonarQube), administrar datos de negocio almacenados en Postgres, atender solicitudes de soporte sobre entidades del sistema, y gestionar configuración dinámica (feature flags) de las aplicaciones que corren sobre la infra.

## 2. Personas

| Persona | Rol | Necesidad principal |
|---|---|---|
| **Admin** | Mantiene la infra y los datos | Acceso total: CRUD, operaciones destructivas, gestión de usuarios del BackOffice |
| **Operator** | Opera la plataforma día a día | Ver estado, reiniciar servicios, consultar datos, lanzar acciones reversibles |
| **Support** | Atiende usuarios finales | Buscar entidades de negocio, ver historial, ejecutar acciones correctivas acotadas |
| **Viewer** | Solo lectura (PM, stakeholders) | Consultar dashboards, datos y métricas sin modificar nada |

> [CLARIFICACIÓN-1] ¿Estos cuatro roles te hacen sentido o quieres ajustarlos?

## 3. Capabilities (alto nivel)

Cada capability será su propio ciclo SDD iterativo. Para el **MVP** elegimos UNA (ver §6).

| ID | Capability | Descripción breve |
|---|---|---|
| C1 | **Admin de datos de negocio** | CRUD sobre tablas Postgres con permisos por tabla/columna y por rol |
| C2 | **Operación de infra** | Ver estado de Kafka topics/consumer groups, reiniciar servicios docker, consultar logs ELK desde una sola UI |
| C3 | **Soporte / Customer service** | Vistas pre-armadas por entidad (ej. "ver usuario X" → datos + eventos Kafka recientes + acciones permitidas) |
| C4 | **Feature flags / configuración** | Toggles y valores de configuración consumibles por las apps vía API o Kafka |
| C5 | **Auth con roles** | Login, gestión de usuarios del BackOffice, permisos por capability |
| C6 | **Audit log** | Registro persistente de toda acción modificatoria (Artículo VI de la Constitution) |

## 4. User Stories y Acceptance Criteria

### C5 — Auth con roles (transversal, requerido por todas)

**US-5.1** Como Admin quiero iniciar sesión con usuario y contraseña para acceder al BackOffice.
- GIVEN que tengo credenciales válidas, WHEN ingreso usuario y contraseña, THEN accedo a la home con las capabilities permitidas por mi rol.
- GIVEN credenciales inválidas, WHEN intento ingresar 5 veces seguidas, THEN mi cuenta queda bloqueada por 15 min.

**US-5.2** Como Admin quiero crear/editar/eliminar usuarios del BackOffice y asignarles un rol.
- GIVEN que soy Admin, WHEN creo un usuario con rol Operator, THEN ese usuario puede loguearse y ve solo las capabilities de Operator.

**US-5.3** Como cualquier rol quiero ver solo las capabilities autorizadas para mi rol.
- GIVEN que soy Viewer, WHEN entro a la home, THEN no veo opciones de modificación en ninguna pantalla.

> [CLARIFICACIÓN-2] ¿Necesitas SSO/OIDC desde el inicio o auth local basta para el MVP?

### C6 — Audit log (transversal)

**US-6.1** Como Admin quiero ver un registro auditable de toda acción modificatoria realizada en el BackOffice.
- GIVEN que un Operator ejecutó una acción destructiva, WHEN consulto el audit log filtrando por su usuario, THEN veo: timestamp, usuario, rol, capability, acción, entidad afectada, payload antes/después.
- GIVEN que pasaron 90 días, WHEN un registro cumple ese tiempo, THEN sigue disponible (retención mínima 1 año).

> [CLARIFICACIÓN-3] ¿Retención de audit log: 90 días, 1 año, indefinida?

### C1 — Admin de datos de negocio

**US-1.1** Como Operator quiero ver, filtrar y paginar registros de cualquier tabla autorizada de la base Postgres.
- GIVEN que mi rol tiene acceso a la tabla `orders`, WHEN abro la vista, THEN veo los primeros 50 registros con paginación y puedo filtrar por al menos 3 columnas.

**US-1.2** Como Operator quiero crear, editar y eliminar registros de tablas autorizadas, con confirmación explícita en operaciones destructivas.
- GIVEN que intento eliminar un registro, WHEN confirmo en el modal, THEN se elimina y queda registro en audit log.

> [CLARIFICACIÓN-4] ¿Qué tablas/dominios concretos del Postgres expones en el MVP? (ahora la DB está vacía, ¿hay un esquema previsto?)

### C2 — Operación de infra

**US-2.1** Como Operator quiero ver el estado de los topics y consumer groups de Kafka sin abrir AKHQ aparte.
- GIVEN que el cluster está arriba, WHEN abro la vista de Kafka, THEN veo los topics, particiones, lag por consumer group.

**US-2.2** Como Operator quiero reiniciar contenedores docker desde la UI.
- GIVEN que selecciono el contenedor `kafka1`, WHEN confirmo "restart", THEN el contenedor se reinicia y queda en audit log.

**US-2.3** Como Operator quiero buscar logs en ELK desde una caja de búsqueda integrada.
- GIVEN que ingreso un texto, WHEN busco, THEN veo los últimos 100 hits con timestamp, container, mensaje.

> [CLARIFICACIÓN-5] ¿Operar la infra implica también acciones sobre stacks que aún no existen (ej. lanzar jobs, escalar)? ¿O solo ver/reiniciar lo que ya hay?

### C3 — Soporte

**US-3.1** Como Support quiero buscar una entidad de negocio (ej. usuario, orden) por ID o atributos clave.
- GIVEN que ingreso un ID válido, WHEN busco, THEN veo la "vista 360" con datos de Postgres + últimos N eventos relacionados en Kafka.

**US-3.2** Como Support quiero ejecutar acciones pre-aprobadas sobre una entidad (ej. "reenviar email", "resetear estado").
- GIVEN que estoy en la vista de una entidad, WHEN ejecuto una acción permitida, THEN se ejecuta, queda en audit log y se publica un evento en `backoffice.1.0.event.<accion>`.

> [CLARIFICACIÓN-6] ¿Qué entidades y qué acciones de soporte concretas? Sin esto C3 es solo placeholder.

### C4 — Feature flags

**US-4.1** Como Admin quiero crear flags booleanos y valores de configuración con scope global o por ambiente.
- GIVEN que creo el flag `new-checkout=true`, WHEN una app consulta el endpoint, THEN recibe `true`.

**US-4.2** Como Operator quiero togglear un flag y ver el cambio reflejado en menos de 30 segundos en las apps consumidoras.
- GIVEN que cambio el flag, WHEN una app consulta dentro de los 30s, THEN ve el nuevo valor.

> [CLARIFICACIÓN-7] ¿Las apps consumirán flags vía HTTP polling, SSE/WebSocket, o eventos Kafka?

## 5. Requisitos no funcionales

- **NF-1** Despliegue local en menos de 2 minutos con `make backoffice-up`.
- **NF-2** Footprint de memoria total del stack BackOffice ≤ 2 GB.
- **NF-3** Compatible con macOS y Linux x86_64 / arm64 (igual que el resto del repo).
- **NF-4** Audit log debe sobrevivir a `docker-compose down` (no a `down --volumes`).
- **NF-5** Cero dependencias de servicios cloud externos.

## 6. MVP — Alcance de la primera iteración (CONFIRMADO)

**MVP**: **C5 (Auth con roles) + C6 (Audit log) + C2 (Operar infra existente)**.

Razonamiento:
- C5 y C6 son transversales y obligatorios por la Constitution.
- C2 entrega valor inmediato con la infra que ya existe (Kafka, Docker, ELK) sin depender de datos de negocio que aún no existen en Postgres.
- C1 queda fuera del MVP porque Postgres está vacío y no hay esquema de negocio definido (ver §8 CLARIF-4).

**Fuera del MVP** (iteraciones futuras): C1, C3, C4.

## 7. Fuera de alcance (explícito)

- Despliegue en producción / hosting cloud.
- Multi-tenancy.
- i18n / l10n (solo español o solo inglés en MVP — definir).
- Mobile-first UI.
- Integración con Splunk (ELK cubre logs).

---

## Lista de clarificaciones

**Resueltas:**
- [x] **CLARIF-4** (resuelta 2026-05-09): Postgres vacío sin esquema. C1 queda **fuera del MVP**.
- [x] **CLARIF-8** (resuelta 2026-05-09): MVP = **C5 + C6 + C2**.

**No bloqueantes para Design** (asumimos defaults razonables, revisitar antes de implementar la capability afectada):
- [ ] **CLARIF-1**: roles Admin/Operator/Support/Viewer → asumido OK hasta objeción.
- [ ] **CLARIF-2**: SSO vs auth local → **default: auth local en MVP**, SSO en iteración futura.
- [ ] **CLARIF-3**: retención audit log → **default: 1 año**.
- [ ] **CLARIF-5**: alcance "operar infra" → **default MVP**: solo lectura/restart sobre stacks ya existentes (Kafka, Docker, ELK). Nada de lanzar jobs nuevos ni escalar.
- [ ] **CLARIF-6**: entidades/acciones soporte (C3) → diferida con C3.
- [ ] **CLARIF-7**: protocolo flags (C4) → diferida con C4.
