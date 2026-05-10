#!/usr/bin/env bash
# Phase F smoke — audit pipeline E2E.
#
# Verifica que el BFF emite eventos a:
#   1. stdout (heredado de uvicorn / docker logs)
#   2. fichero NDJSON en /var/log/backoffice/kafka-dashboard-app.log
#      (volumen `backoffice-audit-logs` compartido con filebeat)
#   3. tabla `audit_log` en SQLite con las nuevas columnas (request_id,
#      duration_ms, audit_source, original_uri)
#   4. índice ES `backoffice-audit-*` con tag `kafka-dashboard-app`
#      (Filebeat → Logstash → ES)
#
# Requiere: backoffice + kafka-dashboard + ELK stack arriba.
# Tokens cacheados por smoke-c.sh en /tmp/kd-token-*.

set -euo pipefail

GW=http://localhost:8080
PREFIX=/kafka
BFF=lg-infra-backoffice-kafka-dashboard-bff
ES=es01
ELK_ENV="/Users/luis.quiroga/Documents/lg/labs/ai/infrastructure/elk/.env"

ES_PASS=$(grep ELASTIC_PASSWORD "$ELK_ENV" | cut -d= -f2)

# Refrescar tokens siempre (los caches de smoke-c.sh expiran en ~5min).
KC=http://localhost:8083/keycloak/realms/lglabs/protocol/openid-connect/token
echo "==> refreshing tokens"
for u in admin operator support viewer; do
  curl -s -X POST "$KC" \
    -d "grant_type=password&client_id=oauth2-proxy&client_secret=lgpass-oidc-secret-change-me&username=lglabs$u&password=lgpass" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])" > /tmp/kd-token-$u
done
T_ADMIN=$(cat /tmp/kd-token-admin)
T_OP=$(cat /tmp/kd-token-operator)
T_SU=$(cat /tmp/kd-token-support)
T_VW=$(cat /tmp/kd-token-viewer)

REQ_ID="phase-f-$(date +%s%N)"

echo "==> F.1 BFF tiene volumen backoffice-audit-logs montado"
docker inspect "$BFF" --format '{{range .Mounts}}{{.Name}} -> {{.Destination}}{{"\n"}}{{end}}' \
  | grep -E "backoffice-audit-logs.*/var/log/backoffice" \
  && echo "  ✓ mount OK" || (echo "  ✗ mount MISSING"; exit 1)

echo
echo "==> F.2 Filebeat tiene input kafka-dashboard-app"
docker exec filebeat01 grep -A2 "id: kafka-dashboard-app" /usr/share/filebeat/filebeat.yml | head -5

echo
echo "==> F.3 Logstash tiene branch para tag kafka-dashboard-app"
docker exec logstash01 grep -A1 "kafka-dashboard-app" /usr/share/logstash/pipeline/logstash.conf | head -5

echo
echo "==> F.4 generar 25 eventos a /api/summary con X-Request-Id distinto"
for i in $(seq 1 25); do
  for ROLE in admin operator support viewer; do
    TOK=$(cat /tmp/kd-token-$ROLE)
    curl -s -o /dev/null -H "Authorization: Bearer $TOK" \
      "$GW$PREFIX/api/summary" \
      -H "X-Request-Id: ${REQ_ID}-${i}-${ROLE}"
  done
done
echo "  ✓ 100 requests enviados"

echo
echo "==> F.5 evento llega al fichero NDJSON dentro del BFF"
sleep 2
LINES=$(docker exec "$BFF" wc -l /var/log/backoffice/kafka-dashboard-app.log | awk '{print $1}')
echo "  archivo tiene $LINES líneas (esperado >= 100)"
docker exec "$BFF" tail -1 /var/log/backoffice/kafka-dashboard-app.log \
  | python3 -m json.tool 2>&1 | head -10

echo
echo "==> F.6 fila persistida en SQLite con nuevas columnas"
docker exec "$BFF" python -c "
import sqlite3
c = sqlite3.connect('/data/kafka-dashboard.sqlite')
row = c.execute(
  'SELECT request_id, audit_source, original_uri, duration_ms, status, method, path '
  'FROM audit_log WHERE request_id LIKE \"${REQ_ID}%\" '
  'ORDER BY id DESC LIMIT 1'
).fetchone()
print('  fila:', row)
assert row is not None, 'no se encontró ninguna fila con el request_id de prueba'
assert row[1] == 'kafka-dashboard-bff', f'audit_source inesperado: {row[1]}'
assert row[2] == '/kafka/api/summary', f'original_uri inesperado: {row[2]}'
assert row[3] is not None, 'duration_ms vacío'
print('  ✓ schema 002 + middleware OK')
"

echo
echo "==> F.7 evento llega a Elasticsearch con tag kafka-dashboard-app"
sleep 10  # Filebeat batch + Logstash + ES refresh interval (1s)
# request_id está mapeado dinámicamente como text, por lo que usamos
# match_phrase_prefix en lugar de prefix (que requiere keyword).
COUNT=$(docker exec "$ES" curl -sk -u elastic:$ES_PASS \
  "https://localhost:9200/backoffice-audit-*/_count" \
  -H "Content-Type: application/json" \
  -d "{\"query\":{\"match_phrase_prefix\":{\"request_id\":\"${REQ_ID}\"}}}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin).get('count',0))")
echo "  docs con request_id ${REQ_ID}*: $COUNT (esperado >= 1)"
[ "$COUNT" -ge 1 ] || (echo "  ✗ no hay docs en ES"; exit 1)

echo
echo "==> F.8 doc de ES tiene los campos esperados (audit_source, original_uri, tag)"
docker exec "$ES" curl -sk -u elastic:$ES_PASS \
  "https://localhost:9200/backoffice-audit-*/_search" \
  -H "Content-Type: application/json" \
  -d "{\"size\":1,\"query\":{\"match_phrase_prefix\":{\"request_id\":\"${REQ_ID}\"}}}" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
hits = d.get('hits', {}).get('hits', [])
assert hits, 'sin hits'
src = hits[0]['_source']
assert src.get('audit_source') == 'kafka-dashboard-bff', f'audit_source: {src.get(\"audit_source\")}'
assert src.get('original_uri', '').startswith('/kafka/'), f'original_uri: {src.get(\"original_uri\")}'
assert 'kafka-dashboard-app' in src.get('tags', []), f'tags: {src.get(\"tags\")}'
assert src.get('audit_type') == 'request', f'audit_type: {src.get(\"audit_type\")}'
assert isinstance(src.get('duration_ms'), int), f'duration_ms: {src.get(\"duration_ms\")}'
print('  ✓ campos OK:', {k: src.get(k) for k in ('audit_source','original_uri','status','method','duration_ms')})
"

echo
echo "==> F.9 oauth2-proxy sigue llegando con tag backoffice-audit (no regresión)"
PROXY_COUNT=$(docker exec "$ES" curl -sk -u elastic:$ES_PASS \
  "https://localhost:9200/backoffice-audit-*/_count" \
  -H "Content-Type: application/json" \
  -d '{"query":{"match":{"source":"backoffice-audit"}}}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin).get('count',0))")
echo "  docs oauth2-proxy: $PROXY_COUNT (esperado > 0)"
[ "$PROXY_COUNT" -gt 0 ] || (echo "  ✗ no llegan docs de oauth2-proxy"; exit 1)

echo
echo "==> done"
