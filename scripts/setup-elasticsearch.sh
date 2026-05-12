#!/usr/bin/env bash
# Sets up Elasticsearch index template, ILM policy, and ingest pipeline for demo.
set -euo pipefail

ES_URL="${ELASTICSEARCH_URL:-http://elasticsearch:9200}"
MAX_RETRIES=30
RETRY_INTERVAL=5

echo "Waiting for Elasticsearch at ${ES_URL}…"
for i in $(seq 1 $MAX_RETRIES); do
  if curl -sf "${ES_URL}/_cluster/health" > /dev/null 2>&1; then
    echo "Elasticsearch is ready."
    break
  fi
  echo "  attempt ${i}/${MAX_RETRIES} – retrying in ${RETRY_INTERVAL}s"
  sleep "$RETRY_INTERVAL"
done

# ── ILM Policy ──────────────────────────────────────────────────────────────
echo "Creating ILM policy…"
curl -sf -X PUT "${ES_URL}/_ilm/policy/ecommerce-logs-policy" \
  -H 'Content-Type: application/json' \
  -d '{
    "policy": {
      "phases": {
        "hot": {
          "min_age": "0ms",
          "actions": {
            "rollover": { "max_age": "1d", "max_size": "1gb" },
            "set_priority": { "priority": 100 }
          }
        },
        "warm": {
          "min_age": "3d",
          "actions": {
            "shrink": { "number_of_shards": 1 },
            "forcemerge": { "max_num_segments": 1 },
            "set_priority": { "priority": 50 }
          }
        },
        "delete": {
          "min_age": "7d",
          "actions": { "delete": {} }
        }
      }
    }
  }'
echo " ✓ ILM policy created"

# ── Index Template ───────────────────────────────────────────────────────────
echo "Creating index template…"
curl -sf -X PUT "${ES_URL}/_index_template/ecommerce-logs" \
  -H 'Content-Type: application/json' \
  -d '{
    "index_patterns": ["ecommerce-logs-*"],
    "template": {
      "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
        "index.lifecycle.name": "ecommerce-logs-policy",
        "index.lifecycle.rollover_alias": "ecommerce-logs"
      },
      "mappings": {
        "properties": {
          "@timestamp":   { "type": "date" },
          "level":        { "type": "keyword" },
          "service":      { "type": "keyword" },
          "message":      { "type": "text", "fields": { "keyword": { "type": "keyword", "ignore_above": 512 } } },
          "app": {
            "properties": {
              "level":        { "type": "keyword" },
              "message":      { "type": "text" },
              "service":      { "type": "keyword" },
              "version":      { "type": "keyword" },
              "extra": {
                "properties": {
                  "method":          { "type": "keyword" },
                  "path":            { "type": "keyword" },
                  "status_code":     { "type": "integer" },
                  "duration_ms":     { "type": "float" },
                  "order_id":        { "type": "keyword" },
                  "user_id":         { "type": "keyword" },
                  "product_id":      { "type": "keyword" },
                  "product_name":    { "type": "keyword" },
                  "quantity":        { "type": "integer" },
                  "total":           { "type": "float" },
                  "error_type":      { "type": "keyword" },
                  "category":        { "type": "keyword" }
                }
              }
            }
          }
        }
      }
    }
  }'
echo " ✓ Index template created"

# ── Ingest Pipeline ──────────────────────────────────────────────────────────
echo "Creating ingest pipeline…"
curl -sf -X PUT "${ES_URL}/_ingest/pipeline/ecommerce-ingest" \
  -H 'Content-Type: application/json' \
  -d '{
    "description": "Parse ecommerce-api JSON logs",
    "processors": [
      {
        "json": {
          "field": "message",
          "target_field": "app",
          "ignore_failure": true
        }
      },
      {
        "date": {
          "field": "app.timestamp",
          "target_field": "@timestamp",
          "formats": ["ISO8601"],
          "ignore_failure": true
        }
      },
      {
        "set": {
          "field": "service",
          "value": "{{app.service}}",
          "ignore_failure": true
        }
      },
      {
        "set": {
          "field": "level",
          "value": "{{app.level}}",
          "ignore_failure": true
        }
      }
    ]
  }'
echo " ✓ Ingest pipeline created"

# ── Kibana Index Pattern ──────────────────────────────────────────────────────
KIBANA_URL="${KIBANA_URL:-http://kibana:5601}"
echo "Waiting for Kibana…"
for i in $(seq 1 $MAX_RETRIES); do
  if curl -sf "${KIBANA_URL}/api/status" > /dev/null 2>&1; then
    echo "Kibana is ready."
    break
  fi
  echo "  attempt ${i}/${MAX_RETRIES} – retrying in ${RETRY_INTERVAL}s"
  sleep "$RETRY_INTERVAL"
done

echo "Creating Kibana data view…"
curl -sf -X POST "${KIBANA_URL}/api/data_views/data_view" \
  -H 'Content-Type: application/json' \
  -H 'kbn-xsrf: true' \
  -d '{
    "data_view": {
      "title": "ecommerce-logs-*",
      "name": "Ecommerce Logs",
      "timeFieldName": "@timestamp"
    }
  }' || echo "  (data view may already exist)"
echo " ✓ Kibana data view ready"

echo "Setup complete!"
