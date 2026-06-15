# Elasticsearch Guide

Elasticsearch provides the full-text search and analytics backend for the Kibana pipeline. This guide covers the index setup, ILM lifecycle, ingest pipeline, and how Filebeat feeds data into it.

---

## Configuration

Config file: `elasticsearch/elasticsearch.yml`

### Key Settings

```yaml
# Single-node cluster – not for production
discovery.type: single-node

# Security disabled – demo only
xpack.security.enabled: false

# JVM heap: 512 MB each side
# Set via environment variable in docker-compose.yml:
# ES_JAVA_OPTS=-Xms512m -Xmx512m

# HTTP endpoint
http.port: 9200
```

> **Production note:** A production deployment would use at least 3 data nodes, enable TLS (`xpack.security.enabled: true`), and size the heap at 50% of available RAM (max 31 GB to stay below the JVM compressed pointer limit).

---

## Index Strategy

### Naming Convention

Indices follow a date-based pattern: `ecommerce-logs-YYYY.MM.DD`

One new index is created per day by Filebeat. This matches the ILM policy's 24-hour rollover period and makes it easy to delete old data.

### Sharding

| Setting | Value | Reason |
|---|---|---|
| `number_of_shards` | 1 | Demo scale; single node can't use more |
| `number_of_replicas` | 0 | Single node — no node to replicate to |

In production, typically 1 shard per 30–50 GB of data, with 1 replica per shard.

---

## Index Template

The template `ecommerce-logs` is created by `scripts/setup-elasticsearch.sh` and applies to all `ecommerce-logs-*` indices.

### Field Mappings

```json
{
  "mappings": {
    "properties": {
      "@timestamp":   { "type": "date" },
      "level":        { "type": "keyword" },
      "service":      { "type": "keyword" },
      "message":      { "type": "text",
                        "fields": { "keyword": { "type": "keyword", "ignore_above": 512 } } },
      "app": {
        "properties": {
          "level":        { "type": "keyword" },
          "message":      { "type": "text" },
          "service":      { "type": "keyword" },
          "extra": {
            "properties": {
              "method":       { "type": "keyword" },
              "path":         { "type": "keyword" },
              "status_code":  { "type": "integer" },
              "duration_ms":  { "type": "float" },
              "order_id":     { "type": "keyword" },
              "user_id":      { "type": "keyword" },
              "product_id":   { "type": "keyword" },
              "product_name": { "type": "keyword" },
              "quantity":     { "type": "integer" },
              "total":        { "type": "float" },
              "error_type":   { "type": "keyword" },
              "category":     { "type": "keyword" }
            }
          }
        }
      }
    }
  }
}
```

### Why These Types?

| Type | Fields | Reason |
|---|---|---|
| `keyword` | `level`, `method`, `error_type`, `order_id` | Exact-match filtering and aggregation |
| `text` | `message` | Full-text search with tokenisation |
| `integer` | `status_code`, `quantity` | Numeric range queries |
| `float` | `duration_ms`, `total` | Numeric aggregations (avg, p95) |
| `date` | `@timestamp` | Time range queries and date histograms |

---

## ILM Policy

The `ecommerce-logs-policy` manages index lifecycle automatically.

```
Day 0 ──────────────────────────── HOT
  Active writes
  Rollover when: age > 1d OR size > 1 GB
  Priority: 100 (first to recover after restart)

Day 3 ──────────────────────────── WARM
  Read-only (no writes)
  forcemerge: 1 segment per shard (reduces file handles)
  shrink: down to 1 shard (reduces overhead)
  Priority: 50

Day 7 ──────────────────────────── DELETE
  Index deleted permanently
```

### Checking ILM Status

```bash
# Current ILM policy
curl -s http://localhost:9200/_ilm/policy/ecommerce-logs-policy | jq .

# ILM status per index
curl -s "http://localhost:9200/ecommerce-logs-*/_ilm/explain" | jq '.indices | to_entries[] | {index: .key, phase: .value.phase, age: .value.age}'

# Manually trigger ILM (advances indices to next phase now)
curl -X POST http://localhost:9200/_ilm/move/ecommerce-logs-2024.06.15 \
  -H "Content-Type: application/json" \
  -d '{"current_step": {"phase": "hot", "action": "rollover", "name": "check-rollover-ready"}, "next_step": {"phase": "warm"}}'
```

---

## Ingest Pipeline

The `ecommerce-ingest` pipeline processes documents before indexing:

```json
{
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
      "set": { "field": "service", "value": "{{app.service}}" }
    },
    {
      "set": { "field": "level",   "value": "{{app.level}}" }
    }
  ]
}
```

**Processor order matters:**
1. Parse `message` JSON → `app.*`
2. Set `@timestamp` from `app.timestamp`
3. Promote `service` and `level` to top-level fields for Kibana filters

### Testing the Pipeline

```bash
# Simulate what the pipeline does to a document
curl -s -X POST http://localhost:9200/_ingest/pipeline/ecommerce-ingest/_simulate \
  -H "Content-Type: application/json" \
  -d '{
    "docs": [{
      "_source": {
        "message": "{\"timestamp\": \"2024-06-15T12:00:00Z\", \"level\": \"INFO\", \"message\": \"Order created\", \"service\": \"ecommerce-api\", \"extra\": {\"order_id\": \"ORD-ABCD1234\", \"total\": 89.97}}"
      }
    }]
  }' | jq '.docs[0].doc._source'
```

---

## Filebeat Configuration

Config file: `filebeat/filebeat.yml`

Filebeat reads from Docker container log files and ships to Elasticsearch.

### Key Settings

```yaml
output.elasticsearch:
  hosts: ["elasticsearch:9200"]
  index: "ecommerce-logs-%{+yyyy.MM.dd}"
  pipeline: "ecommerce-ingest"       # ← applies the ingest pipeline

setup.ilm:
  enabled: true
  rollover_alias: "ecommerce-logs"
  policy_name: "ecommerce-logs-policy"
```

### Filebeat Autodiscover

Filebeat watches the Docker socket for containers matching `image: ecommerce` and automatically starts collecting their logs when they appear.

### Checking Filebeat Status

```bash
# View Filebeat logs
docker logs filebeat --tail=50

# Check if Filebeat can reach Elasticsearch
docker exec filebeat filebeat test output

# Check Filebeat internal metrics
curl http://localhost:5066/stats | jq '.filebeat.events'
```

---

## Useful REST API Queries

```bash
ES=http://localhost:9200

# All indices with doc count and size
curl -s "$ES/_cat/indices/ecommerce-logs-*?v&h=index,docs.count,store.size"

# Top 10 error types by count
curl -s "$ES/ecommerce-logs-*/_search" \
  -H "Content-Type: application/json" \
  -d '{"size":0,"aggs":{"errors":{"terms":{"field":"app.extra.error_type","size":10}}}}' \
  | jq '.aggregations.errors.buckets'

# Average request duration over the last hour
curl -s "$ES/ecommerce-logs-*/_search" \
  -H "Content-Type: application/json" \
  -d '{
    "size": 0,
    "query": {
      "range": { "@timestamp": { "gte": "now-1h" } }
    },
    "aggs": {
      "avg_duration": { "avg": { "field": "app.extra.duration_ms" } },
      "p95_duration": { "percentiles": { "field": "app.extra.duration_ms", "percents": [95] } }
    }
  }' | jq '.aggregations'

# Count documents by HTTP status code
curl -s "$ES/ecommerce-logs-*/_search" \
  -H "Content-Type: application/json" \
  -d '{"size":0,"aggs":{"by_status":{"terms":{"field":"app.extra.status_code"}}}}' \
  | jq '.aggregations.by_status.buckets'
```

---

## Re-Running Setup

The setup script is idempotent and can be re-run at any time:

```bash
docker compose run --rm es-setup
```

This will recreate the ILM policy, index template, ingest pipeline, and Kibana data view without affecting existing data.
