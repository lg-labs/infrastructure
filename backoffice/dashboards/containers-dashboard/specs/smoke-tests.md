# Containers Dashboard — Smoke Tests

> Versión: 0.1.0 · Estado: Approved · Última actualización: 2026-05-10
>
> Este documento contiene los smoke tests **manuales y automatizados** que validan cada fase. Se ejecutan después de cada commit de fase y como parte de CI (`containers-dashboard-smoke` job).
>
> **Pre-requisito común**: BackOffice MVP up + 4 usuarios Keycloak (`lglabsadmin`, `lglabsoperator`, `lglabssupport`, `lglabsviewer`, todos con password `lgpass`).

---

## Helper — obtener bearer token

```bash
get_token() {
  local user=$1 pass=${2:-lgpass}
  curl -s -X POST "http://localhost:8080/keycloak/realms/lglabs/protocol/openid-connect/token" \
    -d "grant_type=password" \
    -d "client_id=oauth2-proxy" \
    -d "client_secret=lgpass-secret" \
    -d "username=$user" -d "password=$pass" \
    -d "scope=openid profile email groups" \
    | jq -r .access_token
}

ADMIN=$(get_token lglabsadmin)
OPERATOR=$(get_token lglabsoperator)
SUPPORT=$(get_token lglabssupport)
VIEWER=$(get_token lglabsviewer)
```

> Si el realm/client_secret difiere, ajustar (ver `backoffice/keycloak/realms/lglabs-realm.json`).

---

## Fase A · Andamiaje

### A.1 — Servicios up

```bash
docker ps --filter name=containers-dashboard --format '{{.Names}}\t{{.Status}}'
# Esperado:
# lg-infra-backoffice-containers-dashboard-fe   Up X (healthy)
# lg-infra-backoffice-containers-dashboard-bff  Up X (healthy)
```

### A.2 — Health público sin auth

```bash
curl -sS -o /dev/null -w "health=%{http_code}\n" http://localhost:8080/containers/api/health
# Esperado: health=200
```

### A.3 — Frontend con SSO

```bash
curl -sS -o /dev/null -w "fe_no_auth=%{http_code}\n" http://localhost:8080/containers/
# Esperado: fe_no_auth=302  (redirect to /oauth2/start)

curl -sS -o /dev/null -w "fe_with_auth=%{http_code}\n" \
  -H "Authorization: Bearer $ADMIN" http://localhost:8080/containers/
# Esperado: fe_with_auth=200
```

### A.4 — Authz nginx (sin tocar BFF)

```bash
# Viewer/support NO pueden POST/DELETE
for tok in "$VIEWER" "$SUPPORT"; do
  curl -sS -o /dev/null -w "post=%{http_code}\n" -X POST \
    -H "Authorization: Bearer $tok" -H "X-Confirm-Resource: foo" \
    "http://localhost:8080/containers/api/containers/abc/restart"
done
# Esperado: post=403  (gateway, antes de tocar BFF)

# Operator NO puede DELETE (admin only)
curl -sS -o /dev/null -w "del=%{http_code}\n" -X DELETE \
  -H "Authorization: Bearer $OPERATOR" -H "X-Confirm-Resource: foo" \
  "http://localhost:8080/containers/api/containers/abc"
# Esperado: del=403
```

### A.5 — Tarjeta en home

```bash
curl -sS -H "Authorization: Bearer $ADMIN" http://localhost:8080/ | grep -c "Containers Dashboard"
# Esperado: ≥ 1
```

---

## Fase B · BFF Read-only

### B.1 — Listar containers

```bash
curl -sS -H "Authorization: Bearer $ADMIN" \
  "http://localhost:8080/containers/api/containers" | jq '.total, .items[0].name'
# Esperado: total ≥ 1, name no null
```

### B.2 — Detalle + redact env

```bash
# Tomar el id de un container con env (ej. el propio bff)
ID=$(docker inspect lg-infra-backoffice-containers-dashboard-bff -f '{{.Id}}')
curl -sS -H "Authorization: Bearer $ADMIN" \
  "http://localhost:8080/containers/api/containers/$ID" \
  | jq '.env[] | select(.key | test("(?i)password|secret|token")) | .value'
# Esperado: todas las salidas son "<redacted>"
```

### B.3 — Logs

```bash
curl -sS -H "Authorization: Bearer $ADMIN" \
  "http://localhost:8080/containers/api/containers/$ID/logs?tail=50" | jq '.lines | length'
# Esperado: 1..50
```

### B.4 — Stats SSE (5s sample)

```bash
timeout 5 curl -sN -H "Authorization: Bearer $ADMIN" \
  "http://localhost:8080/containers/api/containers/$ID/stats" | head -3
# Esperado: ≥ 1 línea "data: {...}" con cpu_percent y memory_usage_mb
```

### B.5 — is_protected en denylist

```bash
KC_ID=$(docker inspect lg-infra-backoffice-keycloak -f '{{.Id}}')
curl -sS -H "Authorization: Bearer $ADMIN" \
  "http://localhost:8080/containers/api/containers" \
  | jq --arg id "$KC_ID" '.items[] | select(.id==$id) | .is_protected'
# Esperado: true
```

### B.6 — Inventario images/volumes/networks

```bash
for r in images volumes networks; do
  curl -sS -o /dev/null -w "$r=%{http_code}\n" \
    -H "Authorization: Bearer $ADMIN" \
    "http://localhost:8080/containers/api/$r"
done
# Esperado: images=200, volumes=200, networks=200
```

### B.7 — Summary

```bash
curl -sS -H "Authorization: Bearer $ADMIN" \
  http://localhost:8080/containers/api/summary \
  | jq '.containers.total, .daemon_version'
# Esperado: total ≥ 10, version no null
```

### B.8 — Matriz de roles read-only

```bash
for tok_name in ADMIN OPERATOR SUPPORT VIEWER; do
  tok=${!tok_name}
  for path in /summary /containers /images /volumes /networks; do
    code=$(curl -sS -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $tok" \
      "http://localhost:8080/containers/api$path")
    echo "$tok_name $path = $code"
  done
done
# Esperado: TODAS = 200 (lectura es para todos los roles autenticados)
```

---

## Fase C · Frontend SPA

`bff/tests/scripts/smoke-c.sh` (automatizado):

- C.1 Assets `/containers/assets/{alpine.min.js,tailwind.min.js,app.js}` → 200.
- C.2 Hash routes responden en SPA: `/containers/`, `/containers/#/containers`, `/containers/#/images`, etc. (todos sirven el mismo `index.html` 200).
- C.3 Banner permanente "Este dashboard tiene acceso completo al daemon Docker" presente en HTML.
- C.4 No-regresión: BackOffice MVP `/`, `/akhq/`, `/portainer/`, `/keycloak/`, `/kibana/` siguen accesibles con 200/302.
- C.5 No-regresión: Kafka Dashboard `/kafka/` sigue accesible.

**Manual (no bloqueante para cierre)**:
- Login con cada rol → tarjeta visible → entrar al dashboard → navegar las 4 listas.
- Como viewer: no se ven botones de start/stop/restart (visualmente ocultos).
- Container en denylist muestra badge "🔒 protegido" en la lista.

---

## Fase D · Mutations start/stop/restart

`bff/tests/scripts/smoke-d.sh` (automatizado):

### D.1 — Setup container test

```bash
docker run -d --name cd-smoke-test --label lglabs.smoke=true alpine:3 sleep 600
TEST_ID=$(docker inspect cd-smoke-test -f '{{.Id}}')
```

### D.2 — Stop con confirmación

```bash
curl -sS -o /dev/null -w "%{http_code}\n" -X POST \
  -H "Authorization: Bearer $OPERATOR" \
  -H "X-Confirm-Resource: cd-smoke-test" \
  "http://localhost:8080/containers/api/containers/$TEST_ID/stop"
# Esperado: 202

docker inspect cd-smoke-test -f '{{.State.Status}}'
# Esperado: exited
```

### D.3 — Stop SIN X-Confirm-Resource

```bash
curl -sS -o /dev/null -w "%{http_code}\n" -X POST \
  -H "Authorization: Bearer $OPERATOR" \
  "http://localhost:8080/containers/api/containers/$TEST_ID/stop"
# Esperado: 409
```

### D.4 — Start (no requiere confirmación)

```bash
curl -sS -o /dev/null -w "%{http_code}\n" -X POST \
  -H "Authorization: Bearer $OPERATOR" \
  "http://localhost:8080/containers/api/containers/$TEST_ID/start"
# Esperado: 202
```

### D.5 — Restart

```bash
curl -sS -o /dev/null -w "%{http_code}\n" -X POST \
  -H "Authorization: Bearer $OPERATOR" \
  -H "X-Confirm-Resource: cd-smoke-test" \
  "http://localhost:8080/containers/api/containers/$TEST_ID/restart"
# Esperado: 202
```

### D.6 — Denylist (423 Locked)

```bash
KC_ID=$(docker inspect lg-infra-backoffice-keycloak -f '{{.Id}}')
curl -sS -o /dev/null -w "%{http_code}\n" -X POST \
  -H "Authorization: Bearer $OPERATOR" \
  -H "X-Confirm-Resource: lg-infra-backoffice-keycloak" \
  "http://localhost:8080/containers/api/containers/$KC_ID/restart"
# Esperado: 423
```

### D.7 — Authz negativos

```bash
for tok_name in SUPPORT VIEWER; do
  tok=${!tok_name}
  code=$(curl -sS -o /dev/null -w "%{http_code}" -X POST \
    -H "Authorization: Bearer $tok" \
    -H "X-Confirm-Resource: cd-smoke-test" \
    "http://localhost:8080/containers/api/containers/$TEST_ID/stop")
  echo "$tok_name=$code"
done
# Esperado: SUPPORT=403, VIEWER=403
```

### D.8 — Audit en SQLite

```bash
docker exec lg-infra-backoffice-containers-dashboard-bff \
  sqlite3 /data/app.db \
  "SELECT user, method, original_uri, status, resource_name FROM audit_log WHERE resource_name='cd-smoke-test' ORDER BY id DESC LIMIT 5;"
# Esperado: ≥ 4 filas con lglabsoperator + paths /containers/api/...
```

### D.9 — Cleanup

```bash
docker rm -f cd-smoke-test
```

---

## Fase E · Exec shell

### E.1 — Admin abre exec

> Usar `wscat` (o cliente WS de Python). Test esquemático:

```bash
TEST_ID=$(docker inspect lg-infra-backoffice-keycloak -f '{{.Id}}')   # uno seguro de listar; pero está en denylist
# Mejor: usar uno fuera de denylist
TEST_ID=$(docker inspect lg-infra-elk-kibana-1 -f '{{.Id}}')

wscat --connect "ws://localhost:8080/containers/api/containers/$TEST_ID/exec?shell=sh" \
  -H "Authorization: Bearer $ADMIN"
# > id
# < uid=0(root) gid=0(root) groups=0(root)
# > exit
# < (close)
```

Verificar audit:
```bash
docker exec lg-infra-backoffice-containers-dashboard-bff \
  sqlite3 /data/app.db \
  "SELECT audit_type, user, resource_name FROM audit_log WHERE audit_type LIKE 'exec_%' ORDER BY id DESC LIMIT 4;"
# Esperado: exec_open + exec_close, user=lglabsadmin@lglabs.local
```

### E.2 — Operator NO puede exec (gateway 403)

```bash
curl -sS -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $OPERATOR" \
  -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Key: dGVzdA==" -H "Sec-WebSocket-Version: 13" \
  "http://localhost:8080/containers/api/containers/$TEST_ID/exec?shell=sh"
# Esperado: 403
```

### E.3 — Admin contra denylist → 423

```bash
KC_ID=$(docker inspect lg-infra-backoffice-keycloak -f '{{.Id}}')
# WS upgrade rechazado por BFF con close 1011 + audit denegado.
# (verificar en logs del BFF + SQLite ausencia de exec_open exitoso)
```

### E.4 — Idle timeout

Conectar como admin, no enviar nada por 5min10s, verificar close code 1001. (Manual o test largo en CI opt-in.)

---

## Fase F · Remove

### F.1 — Setup

```bash
docker run -d --name cd-rm-test alpine:3 sleep 600
RM_ID=$(docker inspect cd-rm-test -f '{{.Id}}')
docker stop cd-rm-test
```

### F.2 — Operator NO puede DELETE

```bash
code=$(curl -sS -o /dev/null -w "%{http_code}" -X DELETE \
  -H "Authorization: Bearer $OPERATOR" \
  -H "X-Confirm-Resource: cd-rm-test" \
  "http://localhost:8080/containers/api/containers/$RM_ID")
echo "operator_delete=$code"
# Esperado: 403
```

### F.3 — Admin DELETE OK

```bash
code=$(curl -sS -o /dev/null -w "%{http_code}" -X DELETE \
  -H "Authorization: Bearer $ADMIN" \
  -H "X-Confirm-Resource: cd-rm-test" \
  "http://localhost:8080/containers/api/containers/$RM_ID")
echo "admin_delete=$code"
# Esperado: 204

docker ps -a --filter "id=$RM_ID" --format '{{.Names}}'
# Esperado: vacío
```

### F.4 — Container running sin force → 409

```bash
docker run -d --name cd-rm-running alpine:3 sleep 600
RUN_ID=$(docker inspect cd-rm-running -f '{{.Id}}')
code=$(curl -sS -o /dev/null -w "%{http_code}" -X DELETE \
  -H "Authorization: Bearer $ADMIN" \
  -H "X-Confirm-Resource: cd-rm-running" \
  "http://localhost:8080/containers/api/containers/$RUN_ID")
# Esperado: 409 (container_running)

# Con force=true → 204
code=$(curl -sS -o /dev/null -w "%{http_code}" -X DELETE \
  -H "Authorization: Bearer $ADMIN" \
  -H "X-Confirm-Resource: cd-rm-running" \
  "http://localhost:8080/containers/api/containers/$RUN_ID?force=true")
# Esperado: 204
```

### F.5 — Builtin network protected

```bash
BR_ID=$(docker network inspect bridge -f '{{.Id}}')
code=$(curl -sS -o /dev/null -w "%{http_code}" -X DELETE \
  -H "Authorization: Bearer $ADMIN" \
  -H "X-Confirm-Resource: bridge" \
  "http://localhost:8080/containers/api/networks/$BR_ID")
echo "bridge_delete=$code"
# Esperado: 403 (builtin_network_protected)
```

### F.6 — Volume in_use → 409

```bash
docker volume create cd-rm-vol-test
docker run -d --name cd-rm-vol-mount -v cd-rm-vol-test:/data alpine:3 sleep 600
code=$(curl -sS -o /dev/null -w "%{http_code}" -X DELETE \
  -H "Authorization: Bearer $ADMIN" \
  -H "X-Confirm-Resource: cd-rm-vol-test" \
  "http://localhost:8080/containers/api/volumes/cd-rm-vol-test")
echo "vol_in_use=$code"
# Esperado: 409
docker rm -f cd-rm-vol-mount && docker volume rm cd-rm-vol-test
```

### F.7 — Denylist también para DELETE

```bash
GW_ID=$(docker inspect lg-infra-backoffice-gateway -f '{{.Id}}')
code=$(curl -sS -o /dev/null -w "%{http_code}" -X DELETE \
  -H "Authorization: Bearer $ADMIN" \
  -H "X-Confirm-Resource: lg-infra-backoffice-gateway" \
  "http://localhost:8080/containers/api/containers/$GW_ID")
echo "gw_delete=$code"
# Esperado: 423
```

---

## Fase G · Audit pipeline E2E

`bff/tests/scripts/smoke-g.sh` — réplica del patrón de kafka-dashboard `smoke-f.sh`:

- G.1 Mount `backoffice-audit-logs` montado en BFF (rw).
- G.2 Filebeat reporta input `containers-dashboard-app` activo: `docker exec filebeat01 filebeat status` o `cat /usr/share/filebeat/data/registry/...`.
- G.3 Logstash branch presente: `docker exec logstash01 grep -c 'containers-dashboard-app' /usr/share/logstash/pipeline/logstash.conf`.
- G.4 50 requests con `X-Request-Id` distinto → todas en SQLite + en fichero rotating.
- G.5 Esperar 30s → todas en ES índice `backoffice-audit-*` con `audit_source=containers-dashboard-bff`.
- G.6 `original_uri = /containers/api/...` en cada doc (no `/oauth2/auth`).
- G.7 Verificar exec_open + exec_close llegan a ES (después de smoke E.1).
- G.8 Stream content de exec NO aparece en ES (grep `id; pwd; uid=0` en últimos 100 docs = 0 hits).
- G.9 No-regresión kafka-dashboard: `audit_source=kafka-dashboard-bff` sigue ingestando.
- G.10 No-regresión oauth2-proxy: docs sin regresión cuantitativa.

---

## Fase H · Documentación + CI

- H.1 Docs ES + EN existen y enlazan entre sí (mirror diff = comentarios + IDs preservados).
- H.2 README sub-stack + root README con bloque "Start with Containers Dashboard".
- H.3 Job CI `containers-dashboard-smoke` se dispara con workflow_dispatch y schedule.
- H.4 Versiones spec bumpeadas; `backlog.md` presente con ≥ 5 entradas.

---

## Helper de cierre — full E2E

```bash
bash bff/tests/scripts/smoke-c.sh && \
bash bff/tests/scripts/smoke-d.sh && \
bash bff/tests/scripts/smoke-f.sh && \
bash bff/tests/scripts/smoke-g.sh && \
bash bff/tests/scripts/smoke-i.sh && \
echo "✅ Containers Dashboard MVP+I smoke OK"
```

> Smoke E (exec) requiere `wscat` y se ejecuta opcionalmente; los demás cubren ≥ 90% del MVP+I.

---

## Smoke I — Projects view (Phase I)

**Objetivo:** Verificar el contrato de `/api/projects*` y la integración audit→ELK del nuevo router.

### Casos

| ID | User | Acción | Expected |
|---|---|---|---|
| I.1 | viewer | `GET /projects` | 200, body es array no vacío, cada item tiene `name`, `services`, `aggregate_status`, `containers_total`, `containers_running`, `networks`, `volumes` |
| I.2 | viewer | `GET /projects?include_unmanaged=true` | 200; si el host tiene containers sin label compose, debe aparecer `name="(unmanaged)"` en la lista |
| I.3 | viewer | `GET /projects/backoffice` | 200, schema completo: `services[]`, `networks[]`, `volumes[]`, `graph.nodes[]` (n ≥ 1), `graph.edges[]` |
| I.4 | viewer | `GET /projects/no-existe-foobar` | 404 |
| I.5 | viewer | `GET /projects` con `curl --max-time 2` | termina; informe del tiempo (target NFR-10 < 1s p95) |
| I.6 | viewer | `GET /projects/backoffice` | `graph.edges` incluye al menos un edge con `type=network`; si el compose tiene `depends_on`, también `type=depends_on` |
| I.7 | anon  | `GET /projects` | 401 |
| I.8 | n/a | tras los anteriores, `ES _search backoffice-audit-*` filtrado por `original_uri:/containers/api/projects*` | hits ≥ 6, `audit_source=containers-dashboard-bff` |

### Script

`bff/tests/scripts/smoke-i.sh` — sigue el patrón de smoke-c/d/f/g (sourcing `_lib.sh`, retry helper, ES auth).

### DoD smoke I

- 100% pass con stack `make backoffice-up && make elk-up`.
- 0 regresiones en smoke-{c,d,f,g}.sh.
- Sample de body de `/projects` y `/projects/{name}` adjunto al PR para revisión manual del schema.
