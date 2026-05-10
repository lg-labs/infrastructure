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

echo
echo "==> done"
