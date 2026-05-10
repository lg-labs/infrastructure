#!/usr/bin/env bash
# B.7 smoke matrix — run from anywhere
set -euo pipefail

GW=http://localhost:8080

call() {  # role method path [body]
  local role=$1 method=$2 path=$3 body=${4:-}
  local tok
  tok=$(cat /tmp/kd-token-$role)
  if [ -n "$body" ]; then
    curl -sS -o /dev/null -w "%{http_code}" -X "$method" \
      -H "Authorization: Bearer $tok" \
      -H "Content-Type: application/json" \
      -d "$body" "$GW$path"
  else
    curl -sS -o /dev/null -w "%{http_code}" -X "$method" \
      -H "Authorization: Bearer $tok" "$GW$path"
  fi
}

call_show() {  # role method path [body]   – prints status + body
  local role=$1 method=$2 path=$3 body=${4:-}
  local tok
  tok=$(cat /tmp/kd-token-$role)
  echo "--- $role $method $path ---"
  if [ -n "$body" ]; then
    curl -sS -w "\nHTTP=%{http_code}\n" -X "$method" \
      -H "Authorization: Bearer $tok" \
      -H "Content-Type: application/json" \
      -d "$body" "$GW$path"
  else
    curl -sS -w "\nHTTP=%{http_code}\n" -X "$method" \
      -H "Authorization: Bearer $tok" "$GW$path"
  fi
  echo
}

echo "=== Read endpoints (all 4 roles should get 200) ==="
printf "%-50s %-6s %-6s %-6s %-6s %-6s\n" "endpoint" "method" admin operator support viewer
echo "--------------------------------------------------------------------------------------"
for ep in "GET /kafka/api/topics" "GET /kafka/api/_owners" "GET /kafka/api/summary"; do
  m=${ep%% *}; p=${ep##* }
  printf "%-50s %-6s " "$p" "$m"
  for r in admin operator support viewer; do
    printf "%-9s " "$(call $r $m $p)"
  done
  echo
done

echo
echo "=== POST /kafka/api/topics — create lglabs.smoke.b7 (writers should 201; readers 403) ==="
PAYLOAD='{"name":"lglabs.smoke.b7","partitions":3,"replication_factor":3,"cleanup_policy":"delete","retention_ms":600000,"min_insync_replicas":2,"description":"phase B7 smoke test topic","owner":"team-platform"}'

# attempt as viewer (expect 403)
echo "  viewer   -> $(call viewer POST /kafka/api/topics "$PAYLOAD")"
# attempt as support (expect 403)
echo "  support  -> $(call support POST /kafka/api/topics "$PAYLOAD")"
# attempt as operator (expect 201 first time; 409 on retry)
echo "  operator -> $(call operator POST /kafka/api/topics "$PAYLOAD")"

echo
echo "=== GET /kafka/api/topics/lglabs.smoke.b7 as viewer ==="
call_show viewer GET /kafka/api/topics/lglabs.smoke.b7

echo "=== PATCH retention_ms as operator ==="
call_show operator PATCH /kafka/api/topics/lglabs.smoke.b7 '{"retention_ms":300000}'

echo "=== Export as operator ==="
echo "--- operator GET /export ---"
curl -sS -o /tmp/kd-export.json -w "HTTP=%{http_code}\n" \
  -H "Authorization: Bearer $(cat /tmp/kd-token-operator)" \
  $GW/kafka/api/topics/lglabs.smoke.b7/export
echo "exported file ($(wc -c < /tmp/kd-export.json) bytes):"
head -c 200 /tmp/kd-export.json; echo

echo
echo "=== DELETE without confirm header (expect 409) ==="
echo "  operator -> $(call operator DELETE /kafka/api/topics/lglabs.smoke.b7)"

echo
echo "=== DELETE with correct confirm header as operator (expect 204) ==="
TOK=$(cat /tmp/kd-token-operator)
curl -sS -o /dev/null -w "HTTP=%{http_code}\n" -X DELETE \
  -H "Authorization: Bearer $TOK" \
  -H "X-Confirm-Resource: lglabs.smoke.b7" \
  $GW/kafka/api/topics/lglabs.smoke.b7

echo
echo "=== Internal topic delete protected (expect 403 internal_topic_protected) ==="
TOK=$(cat /tmp/kd-token-admin)
curl -sS -w "\nHTTP=%{http_code}\n" -X DELETE \
  -H "Authorization: Bearer $TOK" \
  -H "X-Confirm-Resource: __consumer_offsets" \
  $GW/kafka/api/topics/__consumer_offsets

echo
echo "=== Audit log persisted in SQLite ==="
docker exec lg-infra-backoffice-kafka-dashboard-bff sh -c \
  "sqlite3 /data/kafka-dashboard.sqlite 'SELECT user, method, status, resource FROM audit_log ORDER BY id DESC LIMIT 8;' 2>/dev/null || echo 'sqlite3 not in image — checking via python:'; \
   python3 -c \"import sqlite3; c=sqlite3.connect('/data/kafka-dashboard.sqlite'); [print(r) for r in c.execute('SELECT user,method,status,resource FROM audit_log ORDER BY id DESC LIMIT 8').fetchall()]\""

echo
echo "=== DONE ==="
