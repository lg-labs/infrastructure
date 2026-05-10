#!/bin/sh
# setup-audit.sh — idempotent setup for BackOffice audit pipeline (E3)
#
# Creates:
#   1. ILM policy `backoffice-audit-ilm` (hot 7d / warm 30d / delete 365d)
#   2. Index template `backoffice-audit` matching `backoffice-audit-*`
#   3. Kibana data view `backoffice-audit-*`
#
# Idempotent: PUT operations overwrite; data view creation tolerates "already exists".

set -eu

ES_URL="${ES_URL:-https://es01:9200}"
KIBANA_URL="${KIBANA_URL:-http://kibana:5601}"
ES_USER="${ES_USER:-elastic}"
ES_PASS="${ES_PASS:?ES_PASS required}"
CA_CERT="${CA_CERT:-/certs/ca/ca.crt}"

CURL_ES="curl -sS --cacert ${CA_CERT} -u ${ES_USER}:${ES_PASS}"
CURL_KB="curl -sS -u ${ES_USER}:${ES_PASS} -H kbn-xsrf:true -H Content-Type:application/json"

echo "[setup-audit] Waiting for Elasticsearch at ${ES_URL}..."
until ${CURL_ES} -o /dev/null -w "%{http_code}" "${ES_URL}/_cluster/health" | grep -qE "200"; do
  sleep 3
done
echo "[setup-audit] ES up."

echo "[setup-audit] Waiting for Kibana at ${KIBANA_URL}..."
until curl -sS -o /dev/null -w "%{http_code}" "${KIBANA_URL}/api/status" | grep -qE "200"; do
  sleep 3
done
echo "[setup-audit] Kibana up."

# 1. ILM policy
echo "[setup-audit] Applying ILM policy backoffice-audit-ilm..."
${CURL_ES} -X PUT "${ES_URL}/_ilm/policy/backoffice-audit-ilm" \
  -H "Content-Type: application/json" -d '{
    "policy": {
      "phases": {
        "hot":  { "min_age": "0ms",  "actions": { "set_priority": { "priority": 100 }, "rollover": { "max_age": "7d", "max_primary_shard_size": "10gb" } } },
        "warm": { "min_age": "7d",   "actions": { "set_priority": { "priority": 50  }, "shrink": { "number_of_shards": 1 }, "forcemerge": { "max_num_segments": 1 } } },
        "delete": { "min_age": "365d", "actions": { "delete": {} } }
      }
    }
  }' | grep -q '"acknowledged":true' && echo "  ILM ok"

# 2. Index template
echo "[setup-audit] Applying index template backoffice-audit..."
${CURL_ES} -X PUT "${ES_URL}/_index_template/backoffice-audit" \
  -H "Content-Type: application/json" -d '{
    "index_patterns": ["backoffice-audit-*"],
    "priority": 200,
    "template": {
      "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "index.lifecycle.name": "backoffice-audit-ilm"
      },
      "mappings": {
        "properties": {
          "ts":          { "type": "date", "format": "yyyy/MM/dd HH:mm:ss||strict_date_optional_time" },
          "client_ip":   { "type": "ip" },
          "user":        { "type": "keyword" },
          "method":      { "type": "keyword" },
          "upstream":    { "type": "keyword" },
          "path":        { "type": "keyword" },
          "protocol":    { "type": "keyword" },
          "status":      { "type": "short" },
          "bytes":       { "type": "long" },
          "duration":    { "type": "float" },
          "audit_type":  { "type": "keyword" },
          "message":     { "type": "text" },
          "file":        { "type": "keyword" },
          "source":      { "type": "keyword" }
        }
      }
    }
  }' | grep -q '"acknowledged":true' && echo "  template ok"

# 3. Kibana data view (idempotent: ignore 409)
echo "[setup-audit] Creating Kibana data view backoffice-audit-*..."
RESP=$(${CURL_KB} -X POST "${KIBANA_URL}/api/data_views/data_view" -d '{
  "data_view": {
    "id":            "backoffice-audit",
    "title":         "backoffice-audit-*",
    "name":          "BackOffice Audit",
    "timeFieldName": "@timestamp"
  },
  "override": true
}')
echo "  ${RESP}" | head -c 300
echo

# 4. Saved search "BackOffice Audit" with columns user/method/path/upstream/status
# (idempotent: overwrite=true)
echo "[setup-audit] Creating saved search 'BackOffice Audit'..."
RESP=$(${CURL_KB} -X POST "${KIBANA_URL}/api/saved_objects/search/backoffice-audit-search?overwrite=true" -d '{
  "attributes": {
    "title":   "BackOffice Audit",
    "description": "Access log de oauth2-proxy (BackOffice). Columnas: user, method, path, upstream, status.",
    "columns": ["user", "method", "path", "upstream", "status", "client_ip", "duration"],
    "sort":    [["@timestamp", "desc"]],
    "kibanaSavedObjectMeta": {
      "searchSourceJSON": "{\"query\":{\"query\":\"audit_type:request\",\"language\":\"kuery\"},\"filter\":[],\"indexRefName\":\"kibanaSavedObjectMeta.searchSourceJSON.index\"}"
    }
  },
  "references": [
    { "id": "backoffice-audit", "name": "kibanaSavedObjectMeta.searchSourceJSON.index", "type": "index-pattern" }
  ]
}')
echo "  ${RESP}" | head -c 300
echo
echo "[setup-audit] Done."
