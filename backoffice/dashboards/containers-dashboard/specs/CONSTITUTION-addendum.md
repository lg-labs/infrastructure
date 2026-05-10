# Containers Dashboard — Constitution Addendum

> Sub-stack del BackOffice. **Hereda** todos los principios de `backoffice/CONSTITUTION.md`. Este documento sólo añade (o aclara) lo que es específico del Containers Dashboard.
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

### B1. Microfrontend, no app independiente

El Containers Dashboard se sirve **siempre** detrás del gateway del BackOffice (`/containers/`). No expone puerto host propio. No tiene IdP propio, ni home propia, ni sistema de roles propio. Los headers `X-Auth-Request-User` / `X-Auth-Request-Groups` que inyecta oauth2-proxy son la única fuente de identidad para el BFF.

### B2. El daemon Docker es la única fuente de verdad

El BFF habla **directamente** con `/var/run/docker.sock` vía `docker-py`. **No** mantiene caché propia. **No** persiste ningún estado del daemon (containers/imágenes/volúmenes/redes son consultados en cada request). Esto evita drift contra Portainer, AKHQ u otros consumidores del mismo socket.

**Excepción documentada:** el audit log persiste en SQLite local (`containers-dashboard-data`) — es el único estado que el BFF posee.

### B3. Acceso completo al socket → defensa en profundidad obligatoria

Montar `/var/run/docker.sock:rw` en el BFF significa **acceso root al host** a través de `docker exec` o `docker run --privileged`. Por tanto:

- **Banner permanente** en la UI: "⚠️ Este dashboard tiene acceso completo al daemon Docker del host. Acciones destructivas son irreversibles." (igual patrón que el banner de ACL-metadata en kafka-dashboard).
- **Denylist hard-coded** de containers críticos del propio BackOffice, no configurable vía YAML, no configurable vía env. Vive en `app/safety/denylist.py` y se versiona en repo. Cualquier cambio requiere PR.
- **Authz redundante**: gateway nginx + dependency `require_admin`/`require_writer` en cada router del BFF. Mismo principio defense-in-depth que kafka-dashboard ACL-metadata (design §A7 kafka).

### B4. Operaciones destructivas requieren confirmación explícita

Stop / Restart / Remove / Exec **requieren** header `X-Confirm-Resource: <name|id>` que coincida con el path. El BFF responde `409 Conflict` si falta o no coincide. Mismo patrón que kafka-dashboard §A4.

**Excepción**: `Start` no requiere confirmación (no es destructiva — el container está parado, encenderlo no destruye estado).

### B5. Self-protection no negociable

La denylist (§B3) bloquea con **HTTP 423 Locked** cualquier mutación (stop, restart, exec, remove) sobre los containers del propio BackOffice + dashboard:

```
lg-infra-backoffice-keycloak
lg-infra-backoffice-gateway
lg-infra-backoffice-proxy
lg-infra-backoffice-portainer
lg-infra-backoffice-containers-dashboard-bff
lg-infra-backoffice-containers-dashboard-fe
```

Razón: evitar auto-DoS del propio dashboard (si paras el gateway o el BFF, pierdes el acceso para arrancarlos de vuelta). El admin que **realmente** quiera tocarlos puede usar Portainer (`/portainer/`) o CLI directo.

### B6. Roles delegan en BackOffice — con asimetría exec/remove

Matriz de permisos (heredada de BackOffice + acotada al ámbito Containers):

| Acción | admin | operator | support | viewer |
|---|:---:|:---:|:---:|:---:|
| Listar / inspect / logs / stats | ✅ | ✅ | ✅ | ✅ |
| Listar imágenes / volumes / networks | ✅ | ✅ | ✅ | ✅ |
| Start / Stop / Restart container | ✅ | ✅ | ❌ | ❌ |
| Exec shell en container | ✅ | ❌ | ❌ | ❌ |
| Remove container / image / volume / network | ✅ | ❌ | ❌ | ❌ |

Justificación de asimetría:
- **operator** tiene start/stop/restart porque son operaciones reversibles propias del día a día.
- **operator** NO tiene exec porque exec equivale a "shell root en el host" — escala de riesgo distinta.
- **operator** NO tiene remove porque borrar imágenes/volumes puede romper stacks vecinos de forma irreversible.

### B7. Exec sessions son auditadas y limitadas

El endpoint exec abre una sesión WebSocket (xterm.js ↔ docker exec):

- **Solo admin**.
- **Idle timeout 5 min**: sin input/output del cliente, el BFF cierra el WS.
- **Audit reforzado**: cada sesión emite 2 eventos en `backoffice-audit-*`:
  - `audit_type=exec_open` al iniciar (con `container_name`, `image`, `command`).
  - `audit_type=exec_close` al cerrar (con `duration_ms`, `exit_code` cuando aplica).
- **Sin grabación de stream** (no se captura el contenido del shell — sería un compromiso de seguridad guardar comandos+output en logs).

### B8. Audit log heredado + extendido

Toda mutación pasa por nginx-gateway → oauth2-proxy → BFF. El audit log de oauth2-proxy registra el SSO (con limitación L2 ya conocida del BackOffice). El BFF añade audit propio (`audit_source: containers-dashboard-bff`) con la URI original + identificadores del recurso (`container_id`, `image_id`, etc.).

### B9. Inventario read-only por defecto

GET de imágenes / volumes / networks es accesible para los 4 roles (es información de inventario, no operativa). Las mutaciones sobre estos recursos (remove image, remove volume, remove network) son **solo admin** + denylist + confirmación.
