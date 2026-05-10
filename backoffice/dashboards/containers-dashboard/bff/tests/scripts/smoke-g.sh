#!/usr/bin/env bash
# Containers Dashboard — Phase G smoke
# E2E audit pipeline: BFF → /var/log/backoffice → Filebeat → Logstash → Elasticsearch.
# Pre-req: BackOffice + ELK up, Filebeat configured with containers-dashboard-app input.
set -uo pipefail

API="http://localhost:8080/containers/api"
KC="http://localhost:8083/keycloak/realms/lglabs/protocol/openid-connect/token"
CS="lgpass-oidc-secret-change-me"
FAIL=0

get_token() {
  curl -s -X POST "$KC" \
    -d "grant_type=password&client_id=oauth2-proxy&client_secret=$CS&username=$1&password=lgpass" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))"
}

echo "=== Containers Dashboard · Smoke G (audit pipeline E2E) ==="

ADMIN=$(get_token lglabsadmin)
[ -z "$ADMIN" ] && { echo "FAIL: no admin token"; exit 1; }

MARK="cd-smoke-g-$(date +%s)-$RANDOM"
docker rm -f "$MARK" 2>/dev/null >/dev/null
docker run -d --name "$MARK" alpine sleep 5 >/dev/null
sleep 6

echo ">>> fire DELETE for marker=$MARK"
code=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
  -H "Authorization: Bearer $ADMIN" -H "X-Confirm-Resource: $MARK" \
  "$API/containers/$MARK")
[ "$code" = "204" ] || { echo "FAIL: DELETE returned $code"; exit 1; }
echo "    DELETE -> $code"

# G.1 — local file has the event
echo ">>> G.1 verify event in BFF log file"
sleep 2
hits_file=$(docker exec lg-infra-backoffice-containers-dashboard-bff \
  grep -c "$MARK" /var/log/backoffice/containers-dashboard-app.log 2>/dev/null || echo 0)
if [ "${hits_file:-0}" -ge 1 ]; then echo "  PASS G.1 BFF logfile has $hits_file hits"
else echo "  FAIL G.1 BFF logfile has 0 hits"; FAIL=$((FAIL+1)); fi

# G.2 — SQLite audit_log has the event
echo ">>> G.2 verify event in SQLite audit_log"
hits_db=$(docker exec lg-infra-backoffice-containers-dashboard-bff python3 -c "
import sqlite3
c=sqlite3.connect('/data/containers-dashboard.sqlite')
n=c.execute(\"SELECT COUNT(*) FROM audit_log WHERE resource_id=?\", ('$MARK',)).fetchone()[0]
print(n)" 2>/dev/null || echo 0)
if [ "${hits_db:-0}" -ge 1 ]; then echo "  PASS G.2 SQLite has $hits_db rows"
else echo "  FAIL G.2 SQLite has 0 rows"; FAIL=$((FAIL+1)); fi

# G.3 — Elasticsearch backoffice-audit-* has the event with audit_source set
echo ">>> G.3 wait 12s for Filebeat→Logstash→ES, then query"
sleep 12
ELASTIC_PASSWORD=$(docker exec es01 sh -c 'echo $ELASTIC_PASSWORD' 2>/dev/null)
[ -z "$ELASTIC_PASSWORD" ] && ELASTIC_PASSWORD="lgpass"

resp=$(docker exec es01 curl -sk -u "elastic:$ELASTIC_PASSWORD" \
  "https://localhost:9200/backoffice-audit-*/_search?size=1&q=resource_id:$MARK")
total=$(echo "$resp" | python3 -c "
import sys,json
try: d=json.load(sys.stdin); print(d.get('hits',{}).get('total',{}).get('value',0))
except: print(0)" 2>/dev/null)
src=$(echo "$resp" | python3 -c "
import sys,json
try:
  d=json.load(sys.stdin); h=d.get('hits',{}).get('hits',[])
  print(h[0]['_source'].get('audit_source','?')) if h else print('NO_HITS')
except: print('PARSE_ERR')" 2>/dev/null)
ouri=$(echo "$resp" | python3 -c "
import sys,json
try:
  d=json.load(sys.stdin); h=d.get('hits',{}).get('hits',[])
  print(h[0]['_source'].get('original_uri','?')) if h else print('NO_HITS')
except: print('PARSE_ERR')" 2>/dev/null)

if [ "${total:-0}" -ge 1 ]; then echo "  PASS G.3 ES has $total docs"
else echo "  FAIL G.3 ES has 0 docs"; FAIL=$((FAIL+1)); fi

if [ "$src" = "containers-dashboard-bff" ]; then echo "  PASS G.4 audit_source=$src"
else echo "  FAIL G.4 audit_source=$src"; FAIL=$((FAIL+1)); fi

case "$ouri" in
  /containers/api/*) echo "  PASS G.5 original_uri=$ouri (mitigates L2)";;
  *) echo "  FAIL G.5 original_uri=$ouri"; FAIL=$((FAIL+1));;
esac

# G.6 — non-regression: kafka-dashboard docs still present
echo ">>> G.6 non-regression — verify kafka-dashboard-bff still indexed"
kd_total=$(docker exec es01 curl -sk -u "elastic:$ELASTIC_PASSWORD" \
  "https://localhost:9200/backoffice-audit-*/_search?size=0&q=audit_source:kafka-dashboard-bff" \
  | python3 -c "
import sys,json
try: print(json.load(sys.stdin).get('hits',{}).get('total',{}).get('value',0))
except: print(0)" 2>/dev/null)
if [ "${kd_total:-0}" -ge 1 ]; then echo "  PASS G.6 kafka-dashboard docs still indexed ($kd_total)"
else echo "  WARN G.6 kafka-dashboard docs=0 (may be empty cluster — not necessarily a regression)"; fi

echo
[ "$FAIL" = "0" ] && { echo "Smoke G: all PASS"; exit 0; } || { echo "Smoke G: $FAIL FAILED"; exit 1; }
