# Kafka Dashboard — Requirements

> Versión: 0.1.0 · Estado: Draft · Última actualización: 2026-05-10
>
> Este documento captura **qué** debe hacer el Kafka Dashboard. El **cómo** está en `design.md`. Las decisiones inmutables están en `CONSTITUTION-addendum.md` (que hereda `backoffice/CONSTITUTION.md`).
>
> Tracking: cada US tiene ID estable, prioridad MoSCoW y criterios de aceptación verificables (Given/When/Then).

---

## 1. Contexto

El cluster Kafka de `lg-labs` (3 brokers + Schema Registry + AKHQ) hoy se gestiona:

- **AKHQ** (`/akhq/`): UI completa de OSS, pero genérica — no impone convenciones del equipo, no tiene auditoría unificada con el resto del BackOffice, y la creación de topics no obliga a documentar owner/descripción.
- **CLI directo a brokers**: requiere acceso al host, sin trazabilidad por usuario, no auditable.

Falta una **consola propia** que (a) imponga convenciones del equipo (naming, owner obligatorio, descripción), (b) emita audit unificado con `backoffice-audit-*`, y (c) prepare el camino para ACLs reales sin re-trabajar el contrato.

## 2. Stakeholders y roles

| Rol | Necesidad principal |
|---|---|
| **admin** | Ver y modificar todo. Gestionar ACL-metadata. |
| **operator** | Crear/editar/borrar topics y schemas en su día a día. |
| **support** | Inspeccionar topics y schemas para diagnosticar incidentes. No modifica. |
| **viewer** | Lectura pura para reporting. |

Matriz completa en `CONSTITUTION-addendum.md` §A7.

## 3. Capacidades en scope (MVP v0.1)

| ID | Capability | Prioridad |
|---|---|---|
| C-T | Topics: listar, ver, crear, editar config, borrar | Must |
| C-S | Schemas: listar, ver, registrar, evolucionar | Must |
| C-A | ACL-metadata: listar, crear, editar, borrar (sin enforcement) | Must |
| C-H | Home del dashboard con resumen del cluster | Should |
| C-X | Exportar topic config / schema a JSON | Must |

Fuera de scope MVP (ver `backlog.md` cuando se cree):
- Producir / consumir mensajes (lo cubre AKHQ)
- Conectores Kafka Connect / KSQL
- Gestión de consumer groups (lo cubre AKHQ)
- ACLs reales en el broker (ver §A6 path de migración)

---

## 4. User Stories

### US-1 · Listar topics del cluster (C-T)

**Como** cualquier usuario autenticado
**quiero** ver la lista de topics del cluster con sus métricas básicas
**para** entender qué hay desplegado y diagnosticar.

**Prioridad:** Must
**Roles:** admin, operator, support, viewer (todos)

**Criterios de aceptación:**

- AC-1.1 · Given un usuario autenticado, when entra a `/kafka/`, then ve una tabla con columnas `name`, `partitions`, `replication_factor`, `min_isr`, `cleanup_policy`, `retention_ms`, `description` (de SQLite si existe), `owner` (de SQLite si existe).
- AC-1.2 · Given más de 50 topics, when carga la lista, then se pagina (50 por página) y se puede filtrar por substring del nombre.
- AC-1.3 · Given un topic interno (`__consumer_offsets`, `_schemas`, etc.), when carga la lista, then queda oculto por defecto y hay un toggle “mostrar topics internos”.
- AC-1.4 · Given un usuario `viewer`, when entra a la lista, then no ve botones de “Crear/Editar/Borrar”.

### US-2 · Crear topic (C-T)

**Como** admin u operator
**quiero** crear un topic con configuración explícita y metadatos
**para** garantizar que cada topic nace con owner y descripción.

**Prioridad:** Must
**Roles:** admin, operator

**Criterios de aceptación:**

- AC-2.1 · Given un admin/operator, when abre el formulario “Crear topic”, then ve campos: `name` (requerido, ver AC-2.2), `partitions` (requerido, 1-100), `replication_factor` (requerido, 1-3, default 3), `cleanup_policy` (delete|compact|both, default delete), `retention_ms` (default 604800000 = 7d), `min_insync_replicas` (default 2), `description` (requerido, min 10 chars), `owner` (requerido, **dropdown** alimentado desde `kafka-dashboard/config/owners.yaml` versionado en repo).
- AC-2.2 · El nombre del topic debe cumplir el regex `^lglabs\.[a-z0-9]([a-z0-9._-]*[a-z0-9])?$` y no exceder 249 chars. La UI **prefilla** el campo con `lglabs.` y bloquea borrar el prefijo. Si el regex falla o el nombre excede el límite, la UI muestra error sin llamar al BFF.
- AC-2.2.b · El BFF re-valida el regex en server-side y rechaza con `400 invalid_topic_name` si no cumple — la UI no es la única defensa.
- AC-2.2.c · El owner enviado debe existir en `owners.yaml`; el BFF rechaza con `400 invalid_owner` si no. El YAML se carga al arrancar y se recarga en cada request (es pequeño, no justifica caché).
- AC-2.3 · Given un nombre que ya existe en el cluster, when envía, then el BFF responde `409 Conflict` con mensaje legible y la UI lo muestra.
- AC-2.4 · Given `replication_factor > brokers disponibles`, when envía, then el BFF responde `400` con mensaje legible.
- AC-2.5 · Given creación exitosa, then (a) el topic existe en el cluster, (b) `description` y `owner` se guardan en SQLite asociados al topic, (c) audit en `backoffice-audit-*` muestra `audit_type=request`, `path=/kafka/api/topics`, `method=POST`, `status=201`, usuario correcto.
- AC-2.6 · Given un usuario `support` o `viewer`, when intenta `POST /kafka/api/topics`, then nginx responde `403` antes de tocar el BFF.

### US-3 · Editar configuración de topic (C-T)

**Como** admin u operator
**quiero** modificar configs editables de un topic existente
**para** ajustar retención/compactación sin recrearlo.

**Prioridad:** Must
**Roles:** admin, operator

**Criterios de aceptación:**

- AC-3.1 · Given un topic existente, when entra a su detalle, then ve sus configs actuales y puede editar `retention_ms`, `cleanup_policy`, `min_insync_replicas`, `description`, `owner`.
- AC-3.2 · `partitions` solo se puede **aumentar** (no reducir); el formulario lo refleja con `min` igual al valor actual.
- AC-3.3 · `replication_factor` **no** se edita en MVP (requiere reasignación; fuera de scope).
- AC-3.4 · Given una edición exitosa, then el cluster refleja el cambio y SQLite refleja `description`/`owner` actualizados.

### US-4 · Borrar topic con confirmación explícita (C-T)

**Como** admin u operator
**quiero** borrar un topic con doble confirmación
**para** evitar borrados accidentales.

**Prioridad:** Must
**Roles:** admin, operator

**Criterios de aceptación:**

- AC-4.1 · Given un topic, when pulsa “Borrar”, then la UI exige escribir el nombre exacto del topic en un input.
- AC-4.2 · Given confirmación correcta, when envía, then la UI manda `DELETE /kafka/api/topics/{name}` con header `X-Confirm-Resource: <name>`.
- AC-4.3 · Given el header `X-Confirm-Resource` ausente o no coincidente con `{name}` en el path, when llega al BFF, then responde `409 Conflict` con `{"error":"confirmation_required"}` y **no** borra nada.
- AC-4.4 · Given confirmación válida y borrado OK, then (a) el topic desaparece del cluster, (b) los metadatos SQLite asociados se borran, (c) audit muestra el `DELETE` con usuario y nombre del topic.
- AC-4.5 · Given un topic interno (prefijo `__` o `_`), when intenta borrar, then el BFF responde `403 Forbidden` con `{"error":"internal_topic_protected"}`, independientemente del rol.

### US-5 · Listar y ver schemas (C-S)

**Como** cualquier usuario autenticado
**quiero** ver los schemas registrados en Schema Registry
**para** entender qué contratos de mensajes existen.

**Prioridad:** Must
**Roles:** admin, operator, support, viewer

**Criterios de aceptación:**

- AC-5.1 · Given un usuario autenticado, when entra a `/kafka/schemas`, then ve la lista de subjects con su última versión, su `compatibility_level` efectivo, y el tipo (AVRO|JSON|PROTOBUF).
- AC-5.2 · Given un subject, when entra al detalle, then ve **todas** las versiones, su id, su schema (formateado) y diff con la versión anterior si la hay.
- AC-5.3 · Given el Schema Registry no responde (timeout 5s), when carga la lista, then la UI muestra un banner de error sin romperse.

### US-6 · Registrar y evolucionar schemas (C-S)

**Como** admin u operator
**quiero** registrar nuevos schemas y evolucionar los existentes
**para** versionar contratos sin tocar el registry directamente.

**Prioridad:** Must
**Roles:** admin, operator

**Criterios de aceptación:**

- AC-6.1 · Given el formulario “Registrar subject”, when envía, then el BFF llama a `POST /subjects/{subject}/versions` del Schema Registry y propaga el resultado.
- AC-6.2 · Given una nueva versión incompatible con el modo configurado en el Registry, when envía, then el BFF re-emite el error `409` del Registry tal cual (no enmascara — §A5).
- AC-6.3 · Given el formulario, when permite cambiar `compatibility_level` del subject, then llama a `PUT /config/{subject}` sólo si el rol es admin u operator.

### US-7 · Gestionar ACL-metadata (C-A)

**Como** admin
**quiero** registrar quién debería poder leer/escribir cada topic
**para** documentar el modelo de permisos antes de tener authorizer real.

**Prioridad:** Must
**Roles:** admin (escritura), todos (lectura)

**Criterios de aceptación:**

- AC-7.1 · El modelo de cada entrada incluye: `principal` (string), `host` (default `*`), `operation` (READ|WRITE|CREATE|DELETE|ALTER|DESCRIBE|ALL), `resource_type` (TOPIC|GROUP|CLUSTER), `resource_name` (string o pattern), `pattern_type` (LITERAL|PREFIXED), `permission_type` (ALLOW|DENY), `created_by`, `created_at`, `note`.
- AC-7.2 · Given un admin, when crea/edita/borra entradas, then se persiste en SQLite y el audit lo refleja.
- AC-7.3 · La UI muestra un banner persistente: “⚠ ACL-metadata informativas — el cluster no las aplica. Ver migración en design §X.”
- AC-7.4 · Given un operator/support/viewer, when intenta `POST/PUT/DELETE` en `/kafka/api/acl-metadata`, then nginx responde `403`.
- AC-7.5 · El export del listado a JSON sigue el mismo schema que aceptaría `AdminClient.create_acls` — esto facilita la migración (§A6).

### US-8 · Home del dashboard con resumen (C-H)

**Como** cualquier usuario autenticado
**quiero** ver un resumen del cluster al entrar
**para** orientarme rápido.

**Prioridad:** Should
**Roles:** todos

**Criterios de aceptación:**

- AC-8.1 · La home `/kafka/` muestra: número de brokers vivos, topics totales (excluyendo internos), schemas totales, ACL-metadata totales, y links rápidos a las 4 secciones.
- AC-8.2 · Si algún componente (brokers, registry, sqlite) no responde, el bloque correspondiente muestra estado degradado sin tirar el resto.

### US-9 · Exportar topic / schema a JSON (C-X)

**Como** admin u operator
**quiero** descargar la configuración de un topic o schema
**para** versionarla en git o documentación.

**Prioridad:** Must
**Roles:** admin, operator

**Criterios de aceptación:**

- AC-9.1 · El detalle de topic/schema tiene un botón “Export JSON” que descarga un archivo `.json` con el estado completo (configs + metadatos + ACL-metadata asociadas si las hay).

---

## 5. Requisitos no funcionales

| ID | Requisito | Métrica |
|---|---|---|
| NFR-1 | Listado de topics responde en < 1s para clusters de hasta 500 topics | p95 |
| NFR-2 | Creación de topic completa en < 3s (incluye write a SQLite) | p95 |
| NFR-3 | Toda mutación produce un evento en `backoffice-audit-*` en < 10s | p95 |
| NFR-4 | El BFF tolera reinicios del cluster Kafka: reintenta conexión con backoff y la UI degrada con banner | — |
| NFR-5 | El BFF respeta los memory limits del BackOffice (default `256m`, configurable vía `.env`) | hard limit |
| NFR-6 | La UI funciona sin JS framework de build — sólo Alpine.js servido por nginx | sin Node en runtime |
| NFR-7 | Cero secretos en imagen ni en repo; todas las credenciales (si las hubiera) por env | grep `lglabs/lgpass` solo en `.env.example` |

## 6. Out of scope (con razón)

| Item | Razón |
|---|---|
| Producir/consumir mensajes desde la UI | AKHQ ya lo hace bien, no duplicamos |
| Gestión de consumer groups | Idem AKHQ |
| Kafka Connect | No usamos conectores en `lg-labs` aún |
| KSQL | Idem |
| ACLs reales (enforcement en broker) | El cluster no tiene authorizer activado; ver §A6 |
| Multi-cluster | Hoy hay un solo cluster `lg-labs` |
| Métricas avanzadas (lag, throughput) | Las cubre AKHQ y, en el futuro, Prometheus/Grafana |

## 7. Convenciones del equipo (data-driven)

### 7.1. Prefijo obligatorio de topics

Todos los topics gestionados por el dashboard **deben** empezar por `lglabs.`. El BFF rechaza otros nombres con `400 invalid_topic_name`. Esto se justifica para:

- Aislar visualmente topics gestionados por el dashboard de los topics internos del cluster (`__consumer_offsets`, `_schemas`, etc.) y de cualquier topic legacy.
- Facilitar futuras ACLs reales con pattern `PREFIXED lglabs.` (ver §A6 path de migración).
- Permitir filtros simples en AKHQ y en métricas.

### 7.2. Owners en YAML versionado

El campo `owner` de un topic **no** es texto libre: se elige de un dropdown alimentado por `kafka-dashboard/config/owners.yaml`. Razones:

- Versionable en git → cada cambio de equipo deja huella.
- Onboarding/offboarding explícito (PR para añadir/quitar owner).
- Sin acoplarse a un servicio de identidad (Keycloak users no equivalen 1:1 a equipos).

**Schema del YAML** (validado al arrancar el BFF):

```yaml
owners:
  - id: team-platform
    name: "Plataforma"
    contact: "platform@lglabs.local"
  - id: team-data
    name: "Datos & Analítica"
    contact: "data@lglabs.local"
  - id: team-payments
    name: "Pagos"
    contact: "payments@lglabs.local"
```

- `id` debe matchear `^[a-z0-9-]+$`, único.
- `name` y `contact` requeridos.
- Si el YAML está malformado al arrancar, el BFF **falla rápido** (exit 1) — no levanta degradado.
- Si el YAML está vacío (sin owners), la UI muestra error claro y bloquea creación de topics, pero permite listar/borrar (degradación parcial documentada).

## 8. Trazabilidad inversa

(Se completará cuando exista `tasks.md`. Cada US referenciará las tareas que la implementan; cada tarea referenciará la US que satisface.)
