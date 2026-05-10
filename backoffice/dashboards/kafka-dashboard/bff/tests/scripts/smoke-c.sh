#!/usr/bin/env bash
# Phase C smoke — SPA assets + role matrix on Topics endpoints.
# Run from anywhere. Tokens cached in /tmp/kd-token-{admin,operator,support,viewer}.
set -euo pipefail

KC=http://localhost:8083/keycloak/realms/lglabs/protocol/openid-connect/token
GW=http://localhost:8080
PREFIX=/kafka

echo "==> refreshing tokens"
for u in admin operator support viewer; do
  curl -s -X POST "$KC" \
    -d "grant_type=password&client_id=oauth2-proxy&client_secret=lgpass-oidc-secret-change-me&username=lglabs$u&password=lgpass" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])" > /tmp/kd-token-$u
done

T_ADMIN=$(cat /tmp/kd-token-admin)

echo
echo "==> C.1 SPA index served by FE"
docker exec lg-infra-backoffice-kafka-dashboard-fe sh -c 'wget -qO- http://127.0.0.1/ | head -3'

echo
echo "==> C.2 assets accessible via gateway under /kafka/"
for path in / assets/app.js assets/alpine.min.js assets/tailwind.min.js; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $T_ADMIN" "$GW$PREFIX/$path")
  echo "  $PREFIX/$path → $code"
done

echo
echo "==> C.3 SPA-consumed endpoints respond"
for ep in api/health api/whoami api/summary api/_owners; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $T_ADMIN" "$GW$PREFIX/$ep")
  echo "  $PREFIX/$ep → $code"
done

echo
echo "==> C.4 role matrix POST /api/topics"
for r in admin operator support viewer; do
  T=$(cat /tmp/kd-token-$r)
  body='{"name":"lglabs.smoke.cphase.'$r'","partitions":3,"replication_factor":3,"configs":{},"owner":"team-platform","description":"phase C smoke topic","environment":"dev"}'
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Authorization: Bearer $T" -H "Content-Type: application/json" -d "$body" "$GW$PREFIX/api/topics")
  echo "  POST as $r → $code (expected admin/operator=201, support/viewer=403)"
done

echo
echo "==> C.4 role matrix EXPORT (BFF enforces writer-only per design §7)"
for r in admin operator support viewer; do
  T=$(cat /tmp/kd-token-$r)
  code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $T" "$GW$PREFIX/api/topics/lglabs.smoke.cphase.admin/export")
  echo "  EXPORT as $r → $code (expected admin/operator=200, support/viewer=403)"
done

echo
echo "==> C.5 X-Confirm-Resource enforcement"
T=$T_ADMIN
curl -s -o /dev/null -w "  no header → %{http_code}\n" -X DELETE -H "Authorization: Bearer $T" "$GW$PREFIX/api/topics/lglabs.smoke.cphase.admin"
curl -s -o /dev/null -w "  wrong header → %{http_code}\n" -X DELETE -H "Authorization: Bearer $T" -H "X-Confirm-Resource: nope" "$GW$PREFIX/api/topics/lglabs.smoke.cphase.admin"
curl -s -o /dev/null -w "  correct → %{http_code}\n" -X DELETE -H "Authorization: Bearer $T" -H "X-Confirm-Resource: lglabs.smoke.cphase.admin" "$GW$PREFIX/api/topics/lglabs.smoke.cphase.admin"

echo
echo "==> C.4 role matrix DELETE (cleanup)"
for r in operator support viewer; do
  T=$(cat /tmp/kd-token-$r)
  code=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE -H "Authorization: Bearer $T" -H "X-Confirm-Resource: lglabs.smoke.cphase.$r" "$GW$PREFIX/api/topics/lglabs.smoke.cphase.$r")
  echo "  DELETE as $r → $code (expected operator=204, support/viewer=403)"
done

echo
echo "==> C.6 BackOffice regression check"
docker ps --filter "name=lg-infra-backoffice" --format "{{.Names}}: {{.Status}}"

# ============================================================
# Phase D — Schemas (Schema Registry proxy)
# Smoke fixture: lglabs.smoke.d.events-value (auto-evolves on each run)
# ============================================================
SUBJ=lglabs.smoke.d.events-value
T_OP=$(cat /tmp/kd-token-operator)

echo
echo "==> D.0 SR reachable + subject present"
curl -s -H "Authorization: Bearer $T_ADMIN" "$GW$PREFIX/api/health" | python3 -m json.tool | grep -E '"(status|kafka|registry)"'
curl -s -o /dev/null -w "  GET /schemas → %{http_code}\n" -H "Authorization: Bearer $T_ADMIN" "$GW$PREFIX/api/schemas"
curl -s -o /dev/null -w "  GET /schemas/$SUBJ → %{http_code}\n" -H "Authorization: Bearer $T_ADMIN" "$GW$PREFIX/api/schemas/$SUBJ"

echo
echo "==> D.1/D.2 register a compatible new version (adds optional field with default)"
# Discover next field index so the schema is always backward-compatible AND new
NEXT=$(curl -s -H "Authorization: Bearer $T_ADMIN" "$GW$PREFIX/api/schemas/$SUBJ" \
  | python3 -c "
import sys, json
d = json.load(sys.stdin)
last = d['versions'][-1]['schema']
s = json.loads(last)
fields = s.get('fields', [])
n = sum(1 for f in fields if f['name'].startswith('note_'))
print(n + 1)
")
echo "  next field: note_$NEXT"
export NEXT
NEW_SCHEMA=$(curl -s -H "Authorization: Bearer $T_ADMIN" "$GW$PREFIX/api/schemas/$SUBJ" \
  | python3 -c "
import sys, json, os
d = json.load(sys.stdin)
last = d['versions'][-1]['schema']
s = json.loads(last)
n = int(os.environ['NEXT'])
s['fields'].append({'name': f'note_{n}', 'type': ['null','string'], 'default': None})
print(json.dumps(s))
")
export NEW_SCHEMA
PAYLOAD=$(python3 -c "import json,os;print(json.dumps({'schema': os.environ['NEW_SCHEMA'], 'schema_type':'AVRO'}))")
RESP=$(curl -s -X POST -H "Authorization: Bearer $T_OP" -H "Content-Type: application/json" \
  -d "$PAYLOAD" "$GW$PREFIX/api/schemas/$SUBJ/versions")
echo "  POST as operator → $RESP"

echo
echo "==> D.3 register an INCOMPATIBLE schema → expect 409 incompatible_schema"
# Ensure compat=BACKWARD so removing a field is genuinely incompatible
curl -s -o /dev/null -X PUT -H "Authorization: Bearer $T_OP" -H "Content-Type: application/json" \
  -d '{"compatibility_level":"BACKWARD"}' "$GW$PREFIX/api/schemas/$SUBJ/config"
export BAD='{"type":"record","name":"Event","namespace":"lglabs.smoke.d","fields":[{"name":"only_required","type":"string"}]}'
BADPAYLOAD=$(python3 -c "import json,os;print(json.dumps({'schema': os.environ['BAD'], 'schema_type':'AVRO'}))")
curl -s -o /tmp/kd-d3.json -w "  HTTP %{http_code}\n" -X POST -H "Authorization: Bearer $T_OP" \
  -H "Content-Type: application/json" -d "$BADPAYLOAD" "$GW$PREFIX/api/schemas/$SUBJ/versions"
python3 -c "import json;d=json.load(open('/tmp/kd-d3.json'));print('  error=',d.get('error'),'  sr_message present=',bool(d.get('details',{}).get('sr_message')))"

echo
echo "==> D.4 set compatibility level (operator)"
for L in FORWARD BACKWARD; do
  code=$(curl -s -o /dev/null -w "%{http_code}" -X PUT -H "Authorization: Bearer $T_OP" \
    -H "Content-Type: application/json" -d "{\"compatibility_level\":\"$L\"}" \
    "$GW$PREFIX/api/schemas/$SUBJ/config")
  echo "  PUT compat=$L → $code"
done

echo
echo "==> D.5 export subject (admin)"
curl -s -o /tmp/kd-d5.json -w "  HTTP %{http_code}\n" -H "Authorization: Bearer $T_ADMIN" \
  "$GW$PREFIX/api/schemas/$SUBJ/export"
python3 -c "import json;d=json.load(open('/tmp/kd-d5.json'));print('  subject=',d.get('subject'),' versions=',len(d.get('versions',[])))"

echo
echo "==> D.6 role matrix on schemas mutating endpoints"
for r in admin operator support viewer; do
  T=$(cat /tmp/kd-token-$r)
  c1=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $T" "$GW$PREFIX/api/schemas")
  c2=$(curl -s -o /dev/null -w "%{http_code}" -X PUT -H "Authorization: Bearer $T" \
    -H "Content-Type: application/json" -d '{"compatibility_level":"BACKWARD"}' \
    "$GW$PREFIX/api/schemas/$SUBJ/config")
  c3=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $T" \
    "$GW$PREFIX/api/schemas/$SUBJ/export")
  echo "  $r → LIST=$c1  SET_COMPAT=$c2  EXPORT=$c3"
done

echo
echo "==> done"
