#!/usr/bin/env bash
# Containers Dashboard — Phase C smoke
# Read-only RBAC + listing endpoints through nginx-gateway.
# Pre-req: BackOffice stack up (make elk-up && make backoffice-up).
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
  if [ "$got" = "$expected" ]; then
    echo "  PASS $label  -> $got"
  else
    echo "  FAIL $label  -> got $got, expected $expected"
    FAIL=$((FAIL+1))
  fi
}

call_code() {
  curl -s -o /dev/null -w "%{http_code}" "$@"
}

echo "=== Containers Dashboard · Smoke C (read-only + RBAC) ==="

ADMIN=$(get_token lglabsadmin)
OPER=$(get_token lglabsoperator)
SUPP=$(get_token lglabssupport)
VIEW=$(get_token lglabsviewer)
[ -z "$ADMIN" ] && { echo "FAIL: no admin token (Keycloak down?)"; exit 1; }

# C.1 — anonymous → 401/302 (oauth2-proxy redirects)
code=$(call_code "$API/health")
case "$code" in 200|302|401) echo "  PASS C.1 anon /health -> $code (auth challenge or 200)";;
  *) echo "  FAIL C.1 anon /health -> $code"; FAIL=$((FAIL+1));;
esac

# C.2 — admin GET /containers
code=$(call_code -H "Authorization: Bearer $ADMIN" "$API/containers?include_stopped=true")
assert_code "C.2 admin GET /containers" 200 "$code"

# C.3 — operator GET /containers
code=$(call_code -H "Authorization: Bearer $OPER" "$API/containers")
assert_code "C.3 operator GET /containers" 200 "$code"

# C.4 — support GET /containers
code=$(call_code -H "Authorization: Bearer $SUPP" "$API/containers")
assert_code "C.4 support GET /containers" 200 "$code"

# C.5 — viewer GET /containers
code=$(call_code -H "Authorization: Bearer $VIEW" "$API/containers")
assert_code "C.5 viewer GET /containers" 200 "$code"

# C.6 — admin GET /images, /volumes, /networks
for path in images volumes networks summary; do
  code=$(call_code -H "Authorization: Bearer $ADMIN" "$API/$path")
  assert_code "C.6.$path admin GET /$path" 200 "$code"
done

# C.7 — denylist container reports is_protected: true
PROTECTED_NAME="lg-infra-backoffice-keycloak"
out=$(curl -s -H "Authorization: Bearer $ADMIN" "$API/containers/$PROTECTED_NAME")
proto=$(echo "$out" | python3 -c "import sys,json; print(json.load(sys.stdin).get('is_protected'))" 2>/dev/null)
if [ "$proto" = "True" ]; then echo "  PASS C.7 keycloak.is_protected=True"
else echo "  FAIL C.7 keycloak.is_protected=$proto (raw=$out)"; FAIL=$((FAIL+1)); fi

# C.8 — env redaction (any container with PASSWORD/SECRET/TOKEN/KEY env)
out=$(curl -s -H "Authorization: Bearer $ADMIN" "$API/containers/lg-infra-backoffice-keycloak")
red=$(echo "$out" | python3 -c "
import sys,json
d=json.load(sys.stdin)
env=d.get('env') or []
hits=[e for e in env if e.get('value')=='<redacted>']
print(len(hits))" 2>/dev/null)
if [ "${red:-0}" -gt 0 ]; then echo "  PASS C.8 env redaction ($red entries redacted)"
else echo "  FAIL C.8 env redaction (no <redacted> values)"; FAIL=$((FAIL+1)); fi

# C.9 — gateway blocks WS exec for non-admin (operator)
code=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "Authorization: Bearer $OPER" \
  -H "Upgrade: websocket" -H "Connection: Upgrade" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" -H "Sec-WebSocket-Version: 13" \
  "$API/containers/lg-infra-backoffice-keycloak/exec?shell=sh")
case "$code" in 403) echo "  PASS C.9 operator WS exec -> 403";;
  *) echo "  FAIL C.9 operator WS exec -> $code"; FAIL=$((FAIL+1));;
esac

echo
[ "$FAIL" = "0" ] && { echo "Smoke C: all PASS"; exit 0; } || { echo "Smoke C: $FAIL FAILED"; exit 1; }
