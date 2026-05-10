# Kafka Dashboard — Constitution Addendum

> Sub-stack del BackOffice. **Hereda** todos los principios de `backoffice/CONSTITUTION.md`. Este documento sólo añade (o aclara) lo que es específico del Kafka Dashboard.
>
> Versión: 0.1.0 · Estado: Approved · Última actualización: 2026-05-10

---

## Herencia

Aplican íntegros los 8 principios del BackOffice:

1. Composición sobre invención
2. Una sola URL de entrada
3. Idempotencia
4. Init containers para bootstrap declarativo
5. Healthchecks + memory limits obligatorios
6. Separación de stacks (cross-stack only via networks externas)
7. Spec-Driven (cada decisión queda en `specs/` antes del código)
8. Lab-defaults documentados (creds, puertos)

> Si un principio del BackOffice contradice algo escrito aquí, **gana el del BackOffice**.

---

## Adiciones específicas

### A1. Microfrontend, no app independiente

El Kafka Dashboard se sirve **siempre** detrás del gateway del BackOffice (`/kafka/`). No expone puerto host propio. No tiene su propio IdP, su propia home, ni su propio sistema de roles. Los headers `X-Auth-Request-User` / `X-Auth-Request-Groups` que inyecta oauth2-proxy son la única fuente de identidad para el BFF.

**Implicación:** el BFF no implementa autenticación; sólo autoriza por header.

### A2. BFF stateless en lo posible; estado en SQLite con justificación

El estado canónico de Kafka vive en Kafka (topics, configs) y en Schema Registry (schemas). El BFF **no** cachea, **no** replica.

Excepción documentada: metadatos que Kafka no almacena (descripciones libres de topic, owners, ACL-metadata). Se persisten en SQLite local en volumen `kafka-dashboard-data`. Cualquier dato en SQLite **debe** poder regenerarse o quedarse vacío sin romper la UI: la app degrada con gracia.

### A3. Contratos API antes que UI

Cada endpoint del BFF se define en `specs/design.md` (path, method, request schema, response schema, status codes, errores) **antes** de implementarlo. La UI consume ese contrato; tests de contrato son obligatorios.

### A4. Operaciones destructivas requieren confirmación explícita

Borrar topic, reset retention, eliminar schema: la UI exige confirmación con texto idéntico al nombre del recurso. El BFF responde `409 Conflict` si no llega un header `X-Confirm-Resource: <nombre>` que coincida.

### A5. Schema evolution respeta compatibilidad declarada en Schema Registry

El BFF **no** fuerza modos de compatibilidad. Si el Schema Registry rechaza un schema por incompatible, el BFF re-emite el error tal cual (no enmascara, no “arregla”).

### A6. ACLs son metadatos hasta nuevo aviso

Mientras el cluster de Kafka no tenga `authorizer.class.name` activado, las “ACLs” del dashboard son metadatos en SQLite (auditables, listables, sin enforcement). Cuando el cluster lo soporte, será trivial sustituir el adaptador por uno que llame al `AdminClient.createAcls`.

**Path de migración (cuando el cluster active authorizer):**

1. Activar `authorizer.class.name=org.apache.kafka.metadata.authorizer.StandardAuthorizer` (KRaft) en `kafka/docker-compose.yml`.
2. En el BFF, sustituir la implementación de `AclMetadataRepository` (SQLite) por `KafkaAclRepository` que use `AdminClient.create_acls` / `describe_acls` de kafka-python. El **mismo contrato de API** se preserva (mismas rutas, mismos schemas request/response).
3. Migración de datos: leer las ACL-metadata de SQLite y aplicarlas como ACLs reales una sola vez (script idempotente). SQLite queda vacía después.
4. Marcar en `design.md` la limitación como resuelta y bumpar versión.

> Esto justifica por qué el contrato de API ya hoy modela ACLs realistas (principal, host, operation, resource, permission_type) en lugar de algo simplificado: el código de hoy es el código de mañana, sólo cambia el repositorio detrás.

### A7. Roles delegan en BackOffice

Matriz de permisos (heredada de BackOffice + acotada al ámbito Kafka):

| Acción | admin | operator | support | viewer |
|---|:---:|:---:|:---:|:---:|
| Listar topics / schemas / ACL-metadata | ✅ | ✅ | ✅ | ✅ |
| Crear/editar topic | ✅ | ✅ | ❌ | ❌ |
| Borrar topic | ✅ | ✅ | ❌ | ❌ |
| Registrar/evolucionar schema | ✅ | ✅ | ❌ | ❌ |
| Crear/editar ACL-metadata | ✅ | ❌ | ❌ | ❌ |

> No hay nuevos roles. No hay roles dedicados de Kafka. Si el equipo necesita granularidad, se introducirá en una iteración futura tras decisión consciente.

### A8. Audit log heredado

Toda mutación pasa por nginx-gateway → oauth2-proxy → upstream. El audit log de oauth2-proxy registra automáticamente quién intentó qué (con limitación L2 documentada en BackOffice design §13.3). El BFF añade un audit propio en SQLite con la URI original (que sí ve) para cubrir esa limitación.
