#!/usr/bin/env bash
# Containers Dashboard — Phase D smoke
# Mutations start/stop/restart with X-Confirm-Resource semantics.
# Pre-req: BackOffice + ELK up.
set -uo pipefail

API="http://localhost:8080/containers/api"
KC="http://localhost:8083/keycloak/realms/lglabs/protocol/openid-connect/token"
CS="lgpass-oidc-secret-change-me"
FAIL=0
TARGET="cd-smoke-d"

get_token() {
  curl -s -X POST "$KC" \
    -d "grant_type=password&client_id=oauth2-proxy&client_secret=$CS&username=$1&password=lgpass" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))"
}
ASSERT() {
  local label="$1" expected="$2" got="$3"
  if [ "$got" = "$expected" ]; then echo "  PASS $label -> $got"
  else echo "  FAIL $label -> got $got, expected $expected"; FAIL=$((FAIL+1)); fi
}

echo "=== Containers Dashboard · Smoke D (start/stop/restart) ==="

ADMIN=$(get_token lglabsadmin)
SUPP=$(get_token lglabssupport)
[ -z "$ADMIN" ] && { echo "FAIL: no admin token"; exit 1; }

# Setup: clean & start a fresh container
docker rm -f "$TARGET" 2>/dev/null >/dev/null
docker run -d --name "$TARGET" alpine sleep 3600 >/dev/null

# D.1 — support POST /stop  -> 403 gateway (writers = admin|operator only)
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  -H "Authorization: Bearer $SUPP" -H "X-Confirm-Resource: $TARGET" \
  "$API/containers/$TARGET/stop")
ASSERT "D.1 support POST /stop" 403 "$code"

# D.2 — admin POST /stop without X-Confirm-Resource -> 409 confirmation_required
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Authorization: Bearer $ADMIN" \
  "$API/containers/$TARGET/stop")
ASSERT "D.2 admin /stop no header" 409 "$code"

# D.3 — admin POST /stop with mismatched X-Confirm-Resource -> 409
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  -H "Authorization: Bearer $ADMIN" -H "X-Confirm-Resource: WRONG" \
  "$API/containers/$TARGET/stop")
ASSERT "D.3 admin /stop bad header" 409 "$code"

# D.4 — admin POST /stop  -> 200 (timeout small)
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  -H "Authorization: Bearer $ADMIN" -H "X-Confirm-Resource: $TARGET" \
  "$API/containers/$TARGET/stop?timeout_seconds=2")
ASSERT "D.4 admin /stop ok" 200 "$code"

# D.5 — admin POST /stop again on stopped -> 409 already_stopped
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  -H "Authorization: Bearer $ADMIN" -H "X-Confirm-Resource: $TARGET" \
  "$API/containers/$TARGET/stop")
ASSERT "D.5 already_stopped" 409 "$code"

# D.6 — admin POST /start (no header required)
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Authorization: Bearer $ADMIN" \
  "$API/containers/$TARGET/start")
ASSERT "D.6 admin /start ok" 200 "$code"

# D.7 — admin POST /start again -> 409 already_running
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Authorization: Bearer $ADMIN" \
  "$API/containers/$TARGET/start")
ASSERT "D.7 already_running" 409 "$code"

# D.8 — admin POST /restart -> 200
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  -H "Authorization: Bearer $ADMIN" -H "X-Confirm-Resource: $TARGET" \
  "$API/containers/$TARGET/restart?timeout_seconds=2")
ASSERT "D.8 admin /restart ok" 200 "$code"

# D.9 — admin POST /stop on denylisted -> 423 protected_resource
PROTECTED="lg-infra-backoffice-keycloak"
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  -H "Authorization: Bearer $ADMIN" -H "X-Confirm-Resource: $PROTECTED" \
  "$API/containers/$PROTECTED/stop")
ASSERT "D.9 protected -> 423" 423 "$code"

# Cleanup
docker rm -f "$TARGET" 2>/dev/null >/dev/null

echo
[ "$FAIL" = "0" ] && { echo "Smoke D: all PASS"; exit 0; } || { echo "Smoke D: $FAIL FAILED"; exit 1; }
