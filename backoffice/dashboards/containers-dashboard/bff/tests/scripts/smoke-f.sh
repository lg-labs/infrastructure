#!/usr/bin/env bash
# Containers Dashboard — Phase F smoke
# DELETE matrix: containers / images / volumes / networks.
# Pre-req: BackOffice + ELK up.
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
ASSERT() {
  local label="$1" expected="$2" got="$3"
  if [ "$got" = "$expected" ]; then echo "  PASS $label -> $got"
  else echo "  FAIL $label -> got $got, expected $expected"; FAIL=$((FAIL+1)); fi
}
CALL() { curl -s -o /dev/null -w "%{http_code}" "$@"; }

echo "=== Containers Dashboard · Smoke F (DELETE matrix) ==="

ADMIN=$(get_token lglabsadmin)
OPER=$(get_token lglabsoperator)
[ -z "$ADMIN" ] && { echo "FAIL: no admin token"; exit 1; }

# ---- Fixtures ----
docker rm -f cd-smoke-f-running cd-smoke-f-stopped cd-smoke-f-vol-user cd-smoke-f-net-user 2>/dev/null >/dev/null
docker volume rm cd-smoke-f-vol cd-smoke-f-vol-mounted 2>/dev/null >/dev/null
docker network rm cd-smoke-f-net cd-smoke-f-net-attached 2>/dev/null >/dev/null

docker run -d --name cd-smoke-f-running alpine sleep 3600 >/dev/null
docker run -d --name cd-smoke-f-stopped alpine sleep 1 >/dev/null
sleep 2
docker volume create cd-smoke-f-vol >/dev/null
docker volume create cd-smoke-f-vol-mounted >/dev/null
docker run -d --name cd-smoke-f-vol-user -v cd-smoke-f-vol-mounted:/data alpine sleep 3600 >/dev/null
docker network create cd-smoke-f-net >/dev/null
docker network create cd-smoke-f-net-attached >/dev/null
docker run -d --name cd-smoke-f-net-user --network cd-smoke-f-net-attached alpine sleep 3600 >/dev/null

H_A=(-H "Authorization: Bearer $ADMIN")
H_O=(-H "Authorization: Bearer $OPER")

# F.1 — operator DELETE container -> 403 (gateway)
code=$(CALL -X DELETE "${H_O[@]}" -H "X-Confirm-Resource: cd-smoke-f-stopped" \
  "$API/containers/cd-smoke-f-stopped")
ASSERT "F.1 operator DELETE container" 403 "$code"

# F.2 — admin DELETE running w/o force -> 409 container_running
code=$(CALL -X DELETE "${H_A[@]}" -H "X-Confirm-Resource: cd-smoke-f-running" \
  "$API/containers/cd-smoke-f-running")
ASSERT "F.2 admin DELETE running w/o force" 409 "$code"

# F.3 — admin DELETE without confirm header -> 409 confirmation_required
code=$(CALL -X DELETE "${H_A[@]}" "$API/containers/cd-smoke-f-stopped")
ASSERT "F.3 admin DELETE no confirm" 409 "$code"

# F.4 — admin DELETE protected -> 423
code=$(CALL -X DELETE "${H_A[@]}" -H "X-Confirm-Resource: lg-infra-backoffice-keycloak" \
  "$API/containers/lg-infra-backoffice-keycloak")
ASSERT "F.4 admin DELETE protected" 423 "$code"

# F.5 — admin DELETE stopped -> 204
code=$(CALL -X DELETE "${H_A[@]}" -H "X-Confirm-Resource: cd-smoke-f-stopped" \
  "$API/containers/cd-smoke-f-stopped")
ASSERT "F.5 admin DELETE stopped" 204 "$code"

# F.6 — admin DELETE running with ?force=true -> 204
code=$(CALL -X DELETE "${H_A[@]}" -H "X-Confirm-Resource: cd-smoke-f-running" \
  "$API/containers/cd-smoke-f-running?force=true")
ASSERT "F.6 admin DELETE running force=true" 204 "$code"

# F.7 — operator DELETE volume -> 403
code=$(CALL -X DELETE "${H_O[@]}" -H "X-Confirm-Resource: cd-smoke-f-vol" \
  "$API/volumes/cd-smoke-f-vol")
ASSERT "F.7 operator DELETE volume" 403 "$code"

# F.8 — admin DELETE volume in-use -> 409 volume_in_use
code=$(CALL -X DELETE "${H_A[@]}" -H "X-Confirm-Resource: cd-smoke-f-vol-mounted" \
  "$API/volumes/cd-smoke-f-vol-mounted")
ASSERT "F.8 admin DELETE volume in-use" 409 "$code"

# F.9 — admin DELETE volume free -> 204
code=$(CALL -X DELETE "${H_A[@]}" -H "X-Confirm-Resource: cd-smoke-f-vol" \
  "$API/volumes/cd-smoke-f-vol")
ASSERT "F.9 admin DELETE volume free" 204 "$code"

# F.10 — admin DELETE bridge (builtin) -> 403
code=$(CALL -X DELETE "${H_A[@]}" -H "X-Confirm-Resource: bridge" \
  "$API/networks/bridge")
ASSERT "F.10 admin DELETE bridge" 403 "$code"

# F.11 — admin DELETE network with attached -> 409
code=$(CALL -X DELETE "${H_A[@]}" -H "X-Confirm-Resource: cd-smoke-f-net-attached" \
  "$API/networks/cd-smoke-f-net-attached")
ASSERT "F.11 admin DELETE net attached" 409 "$code"

# F.12 — admin DELETE empty network -> 204
code=$(CALL -X DELETE "${H_A[@]}" -H "X-Confirm-Resource: cd-smoke-f-net" \
  "$API/networks/cd-smoke-f-net")
ASSERT "F.12 admin DELETE net empty" 204 "$code"

# F.13 — admin DELETE alpine (in use) w/o force -> 409 image_in_use
code=$(CALL -X DELETE "${H_A[@]}" -H "X-Confirm-Resource: alpine" \
  "$API/images/alpine")
ASSERT "F.13 admin DELETE alpine in-use" 409 "$code"

# Cleanup
docker rm -f cd-smoke-f-vol-user cd-smoke-f-net-user 2>/dev/null >/dev/null
docker volume rm cd-smoke-f-vol-mounted 2>/dev/null >/dev/null
docker network rm cd-smoke-f-net-attached 2>/dev/null >/dev/null

echo
[ "$FAIL" = "0" ] && { echo "Smoke F: all PASS (13/13)"; exit 0; } || { echo "Smoke F: $FAIL FAILED"; exit 1; }
