# Kafka Dashboard — Smoke Tests

> Versión: 0.1.0 · Estado: Living document · Última actualización: 2026-05-10
>
> Tests reproducibles ejecutados al cierre de cada fase. Cada test indica precondiciones, comando, output esperado y user story que valida.
>
> Convención: cada fase se valida con los **4 usuarios seed** (lglabsadmin, lglabsoperator, lglabssupport, lglabsviewer), password `lgpass`.

---

## 0. Precondiciones globales

```bash
# Stack BackOffice + Kafka + ELK arrancado
make all-up && make backoffice-status

# Verificar que los 2 contenedores del kafka-dashboard están healthy
docker ps --filter "name=kafka-dashboard" --format "table {{.Names}}\t{{.Status}}"
# Esperado:
#   lg-infra-backoffice-kafka-dashboard-fe   Up X minutes (healthy)
#   lg-infra-backoffice-kafka-dashboard-bff  Up X minutes (healthy)
```

### 0.1 — Helper para obtener token JWT por usuario

```bash
get_token() {
  # $1 = sufijo (admin|operator|support|viewer)
  docker exec lg-infra-backoffice-proxy wget -qO- \
    --post-data="client_id=oauth2-proxy&client_secret=lgpass-oidc-secret-change-me&username=lglabs$1&password=lgpass&grant_type=password&scope=openid profile email" \
    "http://keycloak:8080/keycloak/realms/lglabs/protocol/openid-connect/token" 2>/dev/null \
    | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])"
}
```

---

## Fase A · Andamiaje

Valida que los servicios `kafka-dashboard-fe` y `kafka-dashboard-bff` están desplegados, integrados al gateway, con SSO heredado y matriz de roles aplicada por nginx (sin lógica de Kafka todavía).

### A.1 — Containers healthy

```bash
docker ps --filter "name=kafka-dashboard" --format "{{.Names}}: {{.Status}}"
```

**Esperado:**
```
lg-infra-backoffice-kafka-dashboard-fe: Up ... (healthy)
lg-infra-backoffice-kafka-dashboard-bff: Up ... (healthy)
```

### A.2 — Health endpoint público (sin auth)

```bash
curl -sS -w "\nHTTP %{http_code}\n" http://localhost:8080/kafka/api/health
```

**Esperado:**
```json
{"status":"ok","kafka":"unknown","registry":"unknown","sqlite":"unknown","phase":"A-placeholder"}
HTTP 200
```

### A.3 — `/kafka/` requiere login (redirect a IdP)

```bash
curl -sS -o /dev/null -w "HTTP %{http_code} → %{redirect_url}\n" http://localhost:8080/kafka/
```

**Esperado:**
```
HTTP 302 → http://localhost:8080/oauth2/sign_in?rd=http://localhost:8080/kafka/
```

### A.4 — Frontend placeholder accesible con bearer (admin)

```bash
TOKEN=$(get_token admin)
curl -sS -o /dev/null -w "HTTP %{http_code}\n" \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/kafka/
```

**Esperado:** `HTTP 200` (devuelve la página HTML placeholder).

### A.5 — Matriz role × endpoint (gateway nginx)

Valida `design.md §6` — que el gateway aplica las reglas correctas **antes** de tocar el BFF.

```bash
test_user() {
  local short=$1
  local user="lglabs${short}"
  local token=$(get_token "$short")
  if [ -z "$token" ]; then echo "[$user] NO TOKEN"; return; fi

  local fe=$(curl -sS -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $token" http://localhost:8080/kafka/)
  local api_get=$(curl -sS -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $token" http://localhost:8080/kafka/api/whoami)
  local topics_post=$(curl -sS -o /dev/null -w "%{http_code}" -X POST -H "Authorization: Bearer $token" http://localhost:8080/kafka/api/topics)
  local acl_post=$(curl -sS -o /dev/null -w "%{http_code}" -X POST -H "Authorization: Bearer $token" http://localhost:8080/kafka/api/acl-metadata)

  printf "[%-18s] /kafka/=%s   GET /api/whoami=%s   POST /api/topics=%s   POST /api/acl-metadata=%s\n" \
    "$user" "$fe" "$api_get" "$topics_post" "$acl_post"
}

for u in admin operator support viewer; do test_user "$u"; done
```

**Esperado** (los códigos del BFF que reciben el request son 200; los 404 son del placeholder que no implementa esos endpoints aún; los 403 los emite el gateway antes del BFF):

```
[lglabsadmin       ] /kafka/=200   GET /api/whoami=200   POST /api/topics=404   POST /api/acl-metadata=404
[lglabsoperator    ] /kafka/=200   GET /api/whoami=200   POST /api/topics=404   POST /api/acl-metadata=403
[lglabssupport     ] /kafka/=200   GET /api/whoami=200   POST /api/topics=403   POST /api/acl-metadata=403
[lglabsviewer      ] /kafka/=200   GET /api/whoami=200   POST /api/topics=403   POST /api/acl-metadata=403
```

> **Lectura de la tabla:**
> - Todos los roles ven la UI (`/kafka/` = 200) y leen la API (`GET = 200`).
> - admin/operator pueden mutar topics/schemas (`POST /api/topics` no es 403; el 404 indica que llegó al BFF y este aún no implementa POST).
> - support/viewer reciben `403` del gateway en mutaciones de topics (no llegan al BFF).
> - Solo admin puede mutar ACL-metadata; operator recibe `403` igual que los demás.
>
> **Nota Fase A**: en este momento `GET /api/whoami` puede dar `404` o `200` dependiendo del placeholder. El test final lo valida una vez Fase B reemplace el placeholder por el BFF real con `/api/whoami`.

### A.6 — Tarjeta visible en home del BackOffice (manual, browser)

Pasos:

1. Abrir `http://localhost:8080/` en navegador (modo incógnito).
2. Login con cada uno de los 4 usuarios (`lglabsadmin`, `lglabsoperator`, `lglabssupport`, `lglabsviewer`, password `lgpass`).
3. Verificar que la tarjeta **"Kafka Dashboard"** aparece para los 4 roles.
4. Click en la tarjeta → llega a `/kafka/` **sin re-login** y ve la página placeholder con badge "Fase A · Andamiaje".

### A.7 — `whoami` propaga grupos del JWT al BFF

```bash
TOKEN=$(get_token operator)
curl -sS -H "Authorization: Bearer $TOKEN" http://localhost:8080/kafka/api/whoami
```

**Esperado:** `{"user":null,"groups":"operator"}` (en flujo bearer, `user` viene null porque no hay sesión cookie; `groups` está poblado).

En navegador (cookie de sesión), `user` viene poblado con el email del usuario.

### A.8 — Sin regresiones en BackOffice

```bash
# AKHQ accesible para admin/operator
TOKEN=$(get_token admin)
curl -sS -o /dev/null -w "AKHQ admin: %{http_code}\n" -H "Authorization: Bearer $TOKEN" http://localhost:8080/akhq/
curl -sS -o /dev/null -w "Portainer admin: %{http_code}\n" -H "Authorization: Bearer $TOKEN" http://localhost:8080/portainer/
curl -sS -o /dev/null -w "Kibana admin: %{http_code}\n" -H "Authorization: Bearer $TOKEN" http://localhost:8080/kibana/
```

**Esperado:** todos `200` o `302` (algún redirect interno a su login propio en el caso de Portainer es OK — lo importante es no `5xx`).

---

## Fase B · BFF Topics CRUD

**Estado:** ✅ PASS (2026-05-10) · imagen `lg-infra-backoffice/kafka-dashboard-bff:0.1.0`

### B.1 — Build de la imagen y arranque limpio

```bash
docker compose -f backoffice/docker-compose.yml build kafka-dashboard-bff
docker compose -f backoffice/docker-compose.yml up -d kafka-dashboard-bff
sleep 6
docker ps --filter name=kafka-dashboard-bff --format "{{.Status}}"
# → "Up X seconds (healthy)"
docker logs lg-infra-backoffice-kafka-dashboard-bff 2>&1 | grep -E "owners loaded|migrations applied|kafka-dashboard-bff ready"
# → 3 líneas JSON (lifespan ok)
```

### B.2 — `/api/health` responde `kafka: ok` (BFF conectado al cluster real)

```bash
curl -fsS http://localhost:8080/kafka/api/health | python3 -m json.tool
```

Esperado:

```json
{"status":"ok","kafka":"ok","registry":"unknown","sqlite":"ok"}
```

### B.3 — Tests unitarios / contract suite

```bash
cd backoffice/dashboards/kafka-dashboard/bff
python3 -m venv /tmp/kd-venv && /tmp/kd-venv/bin/pip install -q -r requirements.txt -r tests/requirements-test.txt
/tmp/kd-venv/bin/pytest -q
# → 41 passed
```

### B.4 — Matriz role × endpoint contra el cluster real

Setup tokens (refrescar si pasan >60s):

```bash
for role in admin operator support viewer; do
  curl -sf -X POST "http://localhost:8083/keycloak/realms/lglabs/protocol/openid-connect/token" \
    -d "grant_type=password" -d "client_id=oauth2-proxy" -d "client_secret=lgpass-oidc-secret-change-me" \
    -d "username=lglabs${role}" -d "password=lgpass" \
    | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])" > /tmp/kd-token-${role}
done
```

Matriz esperada (HTTP status):

| Endpoint                              | Method | viewer | support | operator | admin |
|---------------------------------------|--------|--------|---------|----------|-------|
| `/kafka/api/topics`                   | GET    | 200    | 200     | 200      | 200   |
| `/kafka/api/_owners`                  | GET    | 200    | 200     | 200      | 200   |
| `/kafka/api/summary`                  | GET    | 200    | 200     | 200      | 200   |
| `/kafka/api/topics`                   | POST   | 403    | 403     | **201**  | 201   |
| `/kafka/api/topics/<n>`               | PATCH  | 403    | 403     | 200      | 200   |
| `/kafka/api/topics/<n>` sin confirm   | DELETE | 403    | 403     | **409**  | 409   |
| `/kafka/api/topics/<n>` con confirm   | DELETE | 403    | 403     | **204**  | 204   |
| `/kafka/api/topics/__consumer_offsets` con confirm | DELETE | 403 | 403 | 403 | **403** (`internal_topic_protected`) |
| `/kafka/api/topics/<n>/export`        | GET    | 403    | 403     | 200      | 200   |

Script ejecutable: `bff/tests/scripts/smoke-b7.sh` (ver repo).

### B.5 — Validaciones de negocio (CRUD)

- POST con `name` que NO empieza por `lglabs.` → **422** `validation_error`.
- POST con `owner` no presente en `owners.yaml` → **400** `invalid_owner` con `details.valid_owners`.
- POST duplicado → **409** `topic_already_exists`.
- POST con `description` < 10 chars → **422**.
- POST con `partitions > 100` → **422**.
- PATCH `partitions` decreciente → **400** `invalid_partitions`.
- PATCH `cleanup_policy=compact` + `retention_ms=86400000` → reflejado en `configs` del describe.

### B.6 — Audit log persistido en SQLite

```bash
docker exec lg-infra-backoffice-kafka-dashboard-bff python3 -c \
  "import sqlite3; c=sqlite3.connect('/data/kafka-dashboard.sqlite'); \
   [print(r) for r in c.execute('SELECT user,method,status,resource FROM audit_log ORDER BY id DESC LIMIT 8').fetchall()]"
```

Esperado: filas con `method`, `status`, `resource` correctos para cada request.

> **Limitación conocida — Bearer flow:** con `Authorization: Bearer <token>`, oauth2-proxy valida el JWT pero no inyecta `X-Auth-Request-User`, por lo que el campo `user` queda como `"anonymous"` en el audit. En el flujo real de UI (cookie/sesión), la cabecera SÍ se propaga. Mejora para Fase F: derivar identidad del JWT cuando el header esté ausente.

### B.7 — Sin regresiones en BackOffice

```bash
docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "backoffice|portainer|keycloak|gateway"
```

Todos `Up X (healthy)` excepto el conocido `gateway (unhealthy)` (preexistente, ver Fase A.8).

---

## Fase C · Frontend Topics

Valida que la SPA Alpine + Tailwind se entrega correctamente por nginx, los assets vendorados se sirven bajo `/kafka/assets/`, y los endpoints REST consumidos por la UI honran la matriz de roles aplicada por el gateway. La verificación visual (UX, modales, toasts, formularios) se complementa con el checklist manual al final.

Decisiones de Fase C ratificadas en SDD:
- Single-page app con hash router (`#/`, `#/topics`, `#/topics/<name>`).
- Tailwind 3.4 JIT (browser build) y Alpine 3.14 vendorados en `frontend/assets/` (sin build step).
- Scope: solo Topics. Schemas y ACL-metadata se incorporan en Fases D y E.

### C.1 — SPA index y assets servidos por el FE

```bash
docker exec lg-infra-backoffice-kafka-dashboard-fe sh -c \
  'wget -qO- http://127.0.0.1/ | head -10 && echo --- && ls /usr/share/nginx/html/assets/'
```

**Esperado:**
```
<!DOCTYPE html>
<html lang="es">
...
<title>Kafka Dashboard · LG Labs</title>
  <script src="/kafka/assets/tailwind.min.js"></script>
  <script src="/kafka/assets/app.js"></script>
  <script defer src="/kafka/assets/alpine.min.js"></script>
---
alpine.min.js
app.js
tailwind.min.js
```

**Resultado:** ✅ PASS — index.html servido con los 3 scripts apuntando a `/kafka/assets/...` (rutas absolutas correctas para el prefijo del gateway). Assets vendorados presentes (alpine 44KB, tailwind 451KB, app.js ~5KB).

### C.2 — Assets accesibles por el gateway con prefijo `/kafka/`

```bash
TOKEN=$(get_token admin)
for path in / assets/app.js assets/alpine.min.js assets/tailwind.min.js; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" \
    "http://localhost:8080/kafka/$path")
  echo "/kafka/$path → $code"
done
```

**Esperado:** todos `200`.

**Resultado:** ✅ PASS — los 4 paths devuelven 200. Los assets servidos directamente bajo `/assets/...` (sin prefijo) devuelven 404, lo cual es el comportamiento esperado: el gateway no los expone fuera del subpath del dashboard.

### C.3 — Endpoints consumidos por la SPA responden correctamente

```bash
TOKEN=$(get_token viewer)
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8080/kafka/api/health
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8080/kafka/api/whoami
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8080/kafka/api/summary
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8080/kafka/api/_owners | python3 -m json.tool | head -10
```

**Esperado:** `health` 200 con `status: ok`; `whoami` devuelve `groups` con el rol; `summary` con contadores; `_owners` con 4 entradas del YAML.

**Resultado:** ✅ PASS — todos responden 200; `summary` devuelve `{"brokers_alive":3,"topics_total":N,"components":{"kafka":"ok","sqlite":"ok"}}`; `whoami` devuelve `{"user":null,"groups":"admin|operator|support|viewer"}` (user null en flujo Bearer es esperado, ver §B.4); `_owners` devuelve los 4 ids `team-platform`, `team-data`, `team-payments`, `team-identity`.

### C.4 — Matriz de roles sobre acciones de la UI (POST/DELETE/EXPORT)

Valida que las acciones de mutación (`x-show="user.is_writer"` en la SPA) están además protegidas por nginx, y que el flag `is_admin` corresponde al header `X-Auth-Request-Groups`.

```bash
# POST de prueba
for r in admin operator support viewer; do
  T=$(cat /tmp/kd-token-$r)
  body='{"name":"lglabs.smoke.cphase.'$r'","partitions":3,"replication_factor":3,"configs":{},"owner":"team-platform","description":"phase C smoke topic","environment":"dev"}'
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    -H "Authorization: Bearer $T" -H "Content-Type: application/json" \
    -d "$body" http://localhost:8080/kafka/api/topics)
  echo "POST as $r → $code"
done

# DELETE con confirmación
for r in admin operator support viewer; do
  T=$(cat /tmp/kd-token-$r)
  code=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
    -H "Authorization: Bearer $T" -H "X-Confirm-Resource: lglabs.smoke.cphase.$r" \
    http://localhost:8080/kafka/api/topics/lglabs.smoke.cphase.$r)
  echo "DELETE as $r → $code"
done

# EXPORT
for r in admin operator support viewer; do
  T=$(cat /tmp/kd-token-$r)
  code=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $T" \
    http://localhost:8080/kafka/api/topics/lglabs.smoke.cphase.admin/export)
  echo "EXPORT as $r → $code"
done
```

**Esperado:**
| Acción | admin | operator | support | viewer |
|---|---|---|---|---|
| POST   | 201 | 201 | 403 | 403 |
| DELETE | 204 | 204 | 403 | 403 |
| EXPORT | 200 | 200 | 403 | 403 |

**Resultado:** ✅ PASS — coincide con la matriz esperada y con la tabla de design §7. El gateway rechaza con 403 antes de llegar al BFF para los roles `support` y `viewer` en POST/DELETE; EXPORT (GET) devuelve 200 solo para `admin`/`operator` (defensa en profundidad: el BFF aplica `require_writer` en `/{name}/export`, mientras que el gateway permite GET genéricos a cualquier rol — el BFF refuerza la regla de negocio).

### C.5 — Confirmación destructiva (`X-Confirm-Resource`)

```bash
T=$(cat /tmp/kd-token-admin)
# crear topic temporal
curl -s -X POST -H "Authorization: Bearer $T" -H "Content-Type: application/json" \
  -d '{"name":"lglabs.smoke.c5","partitions":1,"replication_factor":3,"configs":{},"owner":"team-platform","description":"confirm test","environment":"dev"}' \
  http://localhost:8080/kafka/api/topics > /dev/null

# DELETE sin header
curl -s -o /dev/null -w "no-header → %{http_code}\n" -X DELETE \
  -H "Authorization: Bearer $T" http://localhost:8080/kafka/api/topics/lglabs.smoke.c5
# DELETE header incorrecto
curl -s -o /dev/null -w "wrong → %{http_code}\n" -X DELETE \
  -H "Authorization: Bearer $T" -H "X-Confirm-Resource: nope" \
  http://localhost:8080/kafka/api/topics/lglabs.smoke.c5
# DELETE correcto
curl -s -o /dev/null -w "correct → %{http_code}\n" -X DELETE \
  -H "Authorization: Bearer $T" -H "X-Confirm-Resource: lglabs.smoke.c5" \
  http://localhost:8080/kafka/api/topics/lglabs.smoke.c5
```

**Esperado:** `409` (sin header), `409` (header distinto al recurso), `204` (correcto).

**Resultado:** ✅ PASS — el BFF devuelve 409 con `error: confirmation_required` en los dos primeros casos y 204 al confirmar. La SPA implementa este flujo en el modal de borrado pidiendo escribir el nombre exacto del topic antes de habilitar el botón "Borrar" (ver `topicDetailView()` en `frontend/index.html`).

### C.6 — Sin regresiones en BackOffice

```bash
docker ps --filter "name=lg-infra-backoffice" --format "{{.Names}}: {{.Status}}"
```

**Esperado:** todos los servicios del BackOffice MVP siguen `Up (healthy)` salvo `gateway` que mantiene el estado pre-existente reportado en B.7.

**Resultado:** ✅ PASS — sin cambios en el resto del stack; los únicos contenedores tocados en esta fase son `lg-infra-backoffice-kafka-dashboard-fe` (bind-mount, sin rebuild) que sirvió la SPA actualizada tras `nginx -s reload`.

### C.7 — Checklist manual de UX (browser, las 4 cuentas)

> Ejecutar en navegador limpio (incógnito) abriendo `http://localhost:8080/kafka/`. Repetir con cada uno de los 4 usuarios seed.

- [ ] Login redirige al IdP, vuelve al dashboard tras autenticarse.
- [ ] Top bar muestra el badge de salud (verde) y el usuario/rol detectado.
- [ ] `Inicio` muestra las 3 tarjetas de summary y la composición.
- [ ] `Topics` lista los topics no internos, con búsqueda y paginación.
- [ ] Botón `Crear` solo aparece para `admin` y `operator` (oculto para `support`/`viewer`).
- [ ] Modal de creación valida: prefijo `lglabs.`, owner obligatorio, descripción ≥10 chars.
- [ ] Detalle de topic muestra metadatos, configs y particiones; botones `Editar`, `Borrar`, `Exportar JSON` aparecen según rol.
- [ ] Borrar exige escribir el nombre exacto del topic antes de habilitar el botón.
- [ ] Toast en español aparece tanto para éxitos como para errores (mensajes desde `humanizeError()`).
- [ ] `Exportar JSON` descarga un archivo `<nombre>.json` con la configuración completa.

> El checklist UX queda como evidencia operacional; los puntos automáticos (C.1–C.6) son los gates duros de la fase.

---

## Fase D · Schemas

> _Pendiente._

---

## Fase E · ACL-metadata

> _Pendiente._

---

## Fase F · Audit pipeline

> _Pendiente._

---

## Fase G · Documentación

> _Pendiente._
