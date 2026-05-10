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

> _Pendiente — se completará al cerrar Fase B._

---

## Fase C · Frontend Topics

> _Pendiente._

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
