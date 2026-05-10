# BackOffice — Smoke Tests (MVP C5 + C6 + C2)

> Tests manuales y semi-automatizados para validar las user stories del MVP.
>
> Pre-requisito: stack arriba con `make backoffice-up`.

---

## 1. Tests automatizados (curl)

### 1.1 Acceso anónimo redirige a login (US-5.1, US-5.3)

```bash
for path in / /me /akhq/ /portainer/ /kibana/ /keycloak/; do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8080$path")
  echo "$path -> $code"
done
```

**Esperado**: todos los paths devuelven `302` (redirect a `/oauth2/sign_in`).

### 1.2 OIDC discovery responde (Fase B)

```bash
curl -s http://localhost:8083/realms/lglabs/.well-known/openid-configuration | jq '.issuer'
```

**Esperado**: `"http://localhost:8083/realms/lglabs"`.

### 1.3 Token directo + claim `groups` por rol (US-5.2, US-5.3)

Verifica que cada usuario seed tiene su rol en el claim `groups` del JWT.
Usamos el hostname interno (`keycloak:8080`) para que el `iss` del token coincida con el que valida `oauth2-proxy`.

```bash
get_token() {
  docker exec lg-infra-backoffice-proxy wget -qO- \
    --post-data="client_id=oauth2-proxy&client_secret=lgpass-oidc-secret-change-me&username=lglabs$1&password=lgpass&grant_type=password&scope=openid profile email" \
    "http://keycloak:8080/realms/lglabs/protocol/openid-connect/token" | jq -r .access_token
}
for user in admin operator support viewer; do
  TOKEN=$(get_token "$user")
  GROUPS=$(echo "$TOKEN" | cut -d. -f2 | tr '_-' '/+' | base64 -d 2>/dev/null | jq -c '.groups')
  echo "lglabs${user} -> groups=$GROUPS"
done
```

**Esperado**:
```
lglabsadmin    -> groups=["admin"]
lglabsoperator -> groups=["operator"]
lglabssupport  -> groups=["support"]
lglabsviewer   -> groups=["viewer"]
```

### 1.3.b Matriz de autorización por rol (US-5.3)

Con el token de cada usuario, verificar 200/302/403 por upstream.
Reglas: admin ve todo; operator ve akhq+portainer+kibana; support+viewer solo kibana.

```bash
matrix() {
  local user=$1
  local token=$(get_token "$user")
  echo "--- lglabs${user} ---"
  for path in /me /akhq/ /portainer/ /kibana/ /keycloak/; do
    code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $token" "http://localhost:8080$path")
    echo "  $path -> $code"
  done
}
matrix admin
matrix operator
matrix support
matrix viewer
```

**Esperado** (200 = stub OK, 403 = denegado por rol; los upstreams reales darán 200/302):

| path | admin | operator | support | viewer |
|---|---|---|---|---|
| `/me` | 200 | 200 | 200 | 200 |
| `/akhq/` | 200 | 200 | 403 | 403 |
| `/portainer/` | 200 | 200 | 403 | 403 |
| `/kibana/` | 200 | 200 | 200 | 200 |
| `/keycloak/` | 200 | 403 | 403 | 403 |

### 1.4 Brute force protection (US-5.1 AC2)

```bash
# 6 intentos con password incorrecto
for i in 1 2 3 4 5 6; do
  curl -s -X POST "http://localhost:8083/realms/lglabs/protocol/openid-connect/token" \
    -d "client_id=oauth2-proxy" \
    -d "client_secret=lgpass-oidc-secret-change-me" \
    -d "username=lglabsoperator" \
    -d "password=WRONG" \
    -d "grant_type=password" | jq -r '"intento '$i': " + (.error_description // .error // "OK")'
done
# 7º intento con password correcto -> debe estar bloqueado
curl -s -X POST "http://localhost:8083/realms/lglabs/protocol/openid-connect/token" \
  -d "client_id=oauth2-proxy" \
  -d "client_secret=lgpass-oidc-secret-change-me" \
  -d "username=lglabsoperator" \
  -d "password=lgpass" \
  -d "grant_type=password" | jq -r '"intento 7 (con password correcto): " + (.error_description // .error // "OK")'
```

**Esperado**:
- Intentos 1-5: `"Invalid user credentials"`
- Intento 6: `"Account temporarily disabled"` o `"Account is not fully set up"` (lockout activado)
- Intento 7: bloqueado a pesar de password correcto (cumple AC2)

> Para desbloquear manualmente: `Keycloak Admin → users → lglabsoperator → Credentials → Reset` o esperar 15 min.

---

## 2. Tests manuales (browser)

### 2.1 Login + landing por rol (US-5.1, US-5.3)

Para cada rol, en una **ventana privada** distinta:

| Usuario | Pass | Tarjetas que DEBE ver | Tarjetas que NO debe ver |
|---|---|---|---|
| `lglabsadmin` | `lgpass` | AKHQ, Portainer, Kibana, Keycloak Admin | (ninguna oculta) |
| `lglabsoperator` | `lgpass` | AKHQ, Portainer, Kibana | Keycloak Admin |
| `lglabssupport` | `lgpass` | Kibana | AKHQ, Portainer, Keycloak Admin |
| `lglabsviewer` | `lgpass` | Kibana | AKHQ, Portainer, Keycloak Admin |

Pasos:
1. Abrir `http://localhost:8080/`
2. Click → redirige a Keycloak
3. Ingresar credenciales
4. Verifica que solo ves las tarjetas listadas

### 2.2 403 al acceder a recurso no autorizado por URL directa (US-5.3)

Logueado como `lglabsviewer`:
1. Navegar a `http://localhost:8080/akhq/`
2. **Esperado**: página 403 "Acceso denegado".

Logueado como `lglabsoperator`:
1. Navegar a `http://localhost:8080/keycloak/`
2. **Esperado**: página 403.

### 2.3 Logout (US-5.1)

1. Click en "Cerrar sesión" en la home
2. **Esperado**: vuelve a la pantalla de login

---

## 3. Audit log (US-6.1) — Fase E

### 3.1 Pipeline básico — el log existe y crece

```bash
docker exec lg-infra-backoffice-proxy ls -la /var/log/proxy/
docker exec lg-infra-backoffice-proxy tail -5 /var/log/proxy/oauth2-proxy.log
```

**Esperado**: archivo `oauth2-proxy.log` presente con entradas JSON válidas (`{"ts":...,"audit_type":"request",...}`).

### 3.2 Filebeat ingesta sin errores

```bash
docker logs filebeat01 --since 1m 2>&1 | grep -c "Error decoding"
```

**Esperado**: `0`. Si > 0, hay líneas no-JSON (revisar `request_logging_format` en `oauth2-proxy/oauth2-proxy.cfg`).

### 3.3 Índice `backoffice-audit-*` existe en ES

```bash
source elk/.env
curl -sk -u "elastic:${ELASTIC_PASSWORD}" "https://localhost:9200/_cat/indices/backoffice-audit-*?v"
```

**Esperado**: línea `backoffice-audit-YYYY.MM.DD ... docs.count > 0`.

### 3.4 ILM, template, data view, saved search creados (E3)

```bash
source elk/.env
curl -sk -u "elastic:${ELASTIC_PASSWORD}" "https://localhost:9200/_ilm/policy/backoffice-audit-ilm" | jq '.["backoffice-audit-ilm"].policy.phases | keys'
curl -sk -u "elastic:${ELASTIC_PASSWORD}" "https://localhost:9200/_index_template/backoffice-audit" | jq '.index_templates[0].index_template.index_patterns'
curl -sS -u "elastic:${ELASTIC_PASSWORD}" "http://localhost:5601/kibana/api/data_views/data_view/backoffice-audit" -H "kbn-xsrf: true" | jq '.data_view | {name, title, timeFieldName}'
curl -sS -u "elastic:${ELASTIC_PASSWORD}" "http://localhost:5601/kibana/api/saved_objects/search/backoffice-audit-search" -H "kbn-xsrf: true" | jq '.attributes | {title, columns}'
```

**Esperado**:
- ILM phases: `["delete","hot","warm"]`
- Template patterns: `["backoffice-audit-*"]`
- Data view: `{name: "BackOffice Audit", title: "backoffice-audit-*", timeFieldName: "@timestamp"}`
- Saved search columns: `["user","method","path","upstream","status","client_ip","duration"]`

### 3.5 Trazabilidad end-to-end (E4)

Genera tráfico autenticado y verifica que aparece en el índice ≤ 30s después.

```bash
# 1) Obtener token de admin
TOK=$(curl -sk -X POST "http://localhost:8083/keycloak/realms/lglabs/protocol/openid-connect/token" \
  -d "grant_type=password&client_id=oauth2-proxy&client_secret=lgpass-oidc-secret-change-me&username=lglabsadmin&password=lgpass" \
  | jq -r .access_token)

# 2) Realizar 3 acciones autenticadas
curl -sk -o /dev/null -H "Authorization: Bearer $TOK" "http://localhost:8080/me"
curl -sk -o /dev/null -H "Authorization: Bearer $TOK" "http://localhost:8080/portainer/api/status"
curl -sk -o /dev/null -H "Authorization: Bearer $TOK" "http://localhost:8080/akhq/api/cluster"

# 3) Esperar ingesta y consultar
sleep 8
source elk/.env
curl -sk -u "elastic:${ELASTIC_PASSWORD}" \
  "https://localhost:9200/backoffice-audit-*/_search?size=5&sort=@timestamp:desc&q=user:lglabsadmin*" \
  | jq '.hits.hits[]._source | {ts, user, method, path, status}'
```

**Esperado**: al menos 3 documentos con `user: "lglabsadmin@lglabs.local"`, `status: 202`, `method: "GET"`. Cada subrequest de auth es un evento.

> **Limitación documentada (design §13.3)**: el campo `path` registra `/oauth2/auth` (la subrequest de nginx), no la URI original (`/portainer/...`). La URI original viaja en el header `X-Original-URI` pero hoy no se persiste en el access log. Mejora futura en backlog.

---

## 4. Tear down

```bash
make backoffice-down        # conserva volúmenes (sesiones Keycloak persistentes)
make backoffice-clean       # borra todos los volúmenes
```
