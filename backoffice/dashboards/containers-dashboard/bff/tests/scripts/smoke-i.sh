#!/usr/bin/env bash
# Containers Dashboard — Phase I smoke (Projects view)
# Verifies /api/projects* contract + RBAC + audit pipeline E2E.
# Pre-req: BackOffice + ELK stacks up.
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

assert_code() {
  local label="$1" expected="$2" got="$3"
  if [ "$got" = "$expected" ]; then echo "  PASS $label  -> $got"
  else echo "  FAIL $label  -> got $got, expected $expected"; FAIL=$((FAIL+1)); fi
}

call_code() {
  curl -s -o /dev/null -w "%{http_code}" "$@"
}

echo "=== Containers Dashboard · Smoke I (Projects view) ==="

VIEW=$(get_token lglabsviewer)
[ -z "$VIEW" ] && { echo "FAIL: no viewer token (Keycloak down?)"; exit 1; }

# I.1 — viewer GET /projects → 200, non-empty
echo ">>> I.1 viewer GET /projects"
body=$(curl -s -H "Authorization: Bearer $VIEW" "$API/projects")
total=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d) if isinstance(d,list) else 0)" 2>/dev/null)
if [ "${total:-0}" -ge 1 ]; then echo "  PASS I.1 GET /projects -> $total projects"
else echo "  FAIL I.1 GET /projects -> body=$body"; FAIL=$((FAIL+1)); fi

# Validate schema of first project
schema_ok=$(echo "$body" | python3 -c "
import sys,json
try:
  d=json.load(sys.stdin)
  if not isinstance(d,list) or not d: print('NO'); sys.exit(0)
  p=d[0]
  required=['name','services','containers_total','containers_running','networks','volumes','aggregate_status','is_unmanaged']
  print('YES' if all(k in p for k in required) else 'NO')
except Exception as e: print('ERR')" 2>/dev/null)
if [ "$schema_ok" = "YES" ]; then echo "  PASS I.1.schema all required fields present"
else echo "  FAIL I.1.schema -> $schema_ok"; FAIL=$((FAIL+1)); fi

# I.2 — include_unmanaged=true returns same or more projects
echo ">>> I.2 viewer GET /projects?include_unmanaged=true"
body2=$(curl -s -H "Authorization: Bearer $VIEW" "$API/projects?include_unmanaged=true")
total2=$(echo "$body2" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null)
if [ "${total2:-0}" -ge "${total:-0}" ]; then echo "  PASS I.2 unmanaged-included -> $total2 (>= $total)"
else echo "  FAIL I.2 unmanaged-included -> $total2 < $total"; FAIL=$((FAIL+1)); fi

# I.3 — detail of a known project (use first project from I.1)
PROJECT=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['name'] if d else '')" 2>/dev/null)
[ -z "$PROJECT" ] && { echo "  SKIP I.3..I.6 (no project to test)"; PROJECT=""; }

if [ -n "$PROJECT" ]; then
  echo ">>> I.3 viewer GET /projects/$PROJECT"
  detail=$(curl -s -H "Authorization: Bearer $VIEW" "$API/projects/$(python3 -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$PROJECT")")
  detail_ok=$(echo "$detail" | python3 -c "
import sys,json
try:
  d=json.load(sys.stdin)
  required=['name','services','networks','volumes','graph','aggregate_status']
  graph_ok='nodes' in d.get('graph',{}) and 'edges' in d.get('graph',{})
  print('YES' if all(k in d for k in required) and graph_ok else 'NO')
except: print('ERR')" 2>/dev/null)
  if [ "$detail_ok" = "YES" ]; then echo "  PASS I.3 detail schema valid"
  else echo "  FAIL I.3 detail -> $detail_ok"; FAIL=$((FAIL+1)); fi

  # I.6 — graph has at least 1 edge of type=network on multi-service project
  echo ">>> I.6 graph edges for $PROJECT"
  edge_types=$(echo "$detail" | python3 -c "
import sys,json
try:
  d=json.load(sys.stdin)
  s=d.get('services',[])
  edges=d.get('graph',{}).get('edges',[])
  types=sorted(set(e['type'] for e in edges))
  print(f'svc={len(s)} edges={len(edges)} types={types}')
except Exception as e: print('ERR:'+str(e))" 2>/dev/null)
  echo "  INFO I.6 $edge_types"
  has_net=$(echo "$detail" | python3 -c "
import sys,json
try:
  d=json.load(sys.stdin)
  print('YES' if any(e['type']=='network' for e in d.get('graph',{}).get('edges',[])) else 'NO')
except: print('ERR')" 2>/dev/null)
  if [ "$has_net" = "YES" ]; then echo "  PASS I.6 has network edges"
  else echo "  WARN I.6 no network edges (single-service project?)"; fi
fi

# I.4 — 404 on unknown project
echo ">>> I.4 viewer GET /projects/no-existe-foobar"
code=$(call_code -H "Authorization: Bearer $VIEW" "$API/projects/no-existe-foobar")
assert_code "I.4 unknown project -> 404" 404 "$code"

# I.5 — perf (informational; not a hard fail)
echo ">>> I.5 timing /projects (NFR-10 < 1s p95)"
t=$(curl -sk -o /dev/null -w "%{time_total}" -H "Authorization: Bearer $VIEW" --max-time 3 "$API/projects?include_unmanaged=true")
echo "  INFO I.5 list took ${t}s"

# I.7 — anon → 401 (oauth2-proxy challenges; bearer-only paths return 401)
echo ">>> I.7 anon GET /projects (no Authorization header)"
code=$(call_code "$API/projects")
case "$code" in 401|302|403) echo "  PASS I.7 anon -> $code (auth challenge)";;
  *) echo "  FAIL I.7 anon -> $code"; FAIL=$((FAIL+1));;
esac

# I.8 — ES audit pipeline: at least one doc routed to backoffice-audit-* with original_uri matching /containers/api/projects*
echo ">>> I.8 ES audit pipeline for projects"
sleep 8   # filebeat poll + logstash flush
ELASTIC_PASSWORD=$(docker exec es01 sh -c 'echo $ELASTIC_PASSWORD' 2>/dev/null)
if [ -z "$ELASTIC_PASSWORD" ]; then
  echo "  SKIP I.8 (es01 not reachable for password)"
else
  query='{"query":{"bool":{"must":[{"match":{"audit_source":"containers-dashboard-bff"}},{"match_phrase":{"path":"/api/projects"}}]}}}'
  resp=$(docker exec es01 curl -sk -u "elastic:$ELASTIC_PASSWORD" \
    -H "Content-Type: application/json" \
    "https://localhost:9200/backoffice-audit-*/_search?size=1" \
    -d "$query" 2>/dev/null)
  total=$(echo "$resp" | python3 -c "
import sys,json
try: print(json.load(sys.stdin).get('hits',{}).get('total',{}).get('value',0))
except: print(0)" 2>/dev/null)
  if [ "${total:-0}" -ge 1 ]; then echo "  PASS I.8 ES has $total /projects audit docs"
  else echo "  FAIL I.8 ES has 0 /projects docs"; FAIL=$((FAIL+1)); fi
fi

echo
[ "$FAIL" = "0" ] && { echo "Smoke I: all PASS"; exit 0; } || { echo "Smoke I: $FAIL FAILED"; exit 1; }
