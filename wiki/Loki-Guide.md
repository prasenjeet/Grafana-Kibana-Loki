# Loki Guide

Loki is the log aggregation system. It is designed to be **"like Prometheus, but for logs"**: it indexes only labels (not content), making it cheap to store and operate. Logs are queried using **LogQL**.

---

## Key Concepts

| Concept | Loki | Prometheus analogy |
|---|---|---|
| **Stream** | Set of logs sharing the same label set | Time series (metric + label set) |
| **Label** | Key-value attached to a stream | Label on a metric |
| **Chunk** | Compressed block of log lines | TSDB block |
| **LogQL** | Query language | PromQL |
| **Promtail** | Log shipper agent | Prometheus exporter |

---

## How Labels Work

Loki's index only contains the **label set** for each stream. A label set is a set of key=value pairs assigned by Promtail during ingestion.

In this project, the `ecommerce-api` stream has these labels:

```
{
  job        = "ecommerce-api",
  container  = "ecommerce-api",
  image      = "...",
  level      = "INFO" | "WARNING" | "ERROR",
  service    = "ecommerce-api",
  method     = "GET" | "POST",
  status_code = "200" | "201" | "400" | "404" | "409" | "500"
}
```

**Why keep labels few?**  
Each unique label combination creates a new stream. High-cardinality labels (e.g., `user_id`, `order_id`, `request_id`) would create millions of streams and defeat the index. Those fields exist in the log body and are accessed via `| json` at query time.

---

## Loki Configuration

Config file: `loki/loki-config.yml`

### Key Settings

```yaml
# Single-binary mode (all components in one process)
# No auth – demo only
auth_enabled: false

server:
  http_listen_port: 3100

# Storage – filesystem (production would use S3/GCS)
common:
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules

# Schema v13 with TSDB index (recommended from Loki 2.8+)
schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb
      object_store: filesystem
      schema: v13
      index:
        prefix: index_
        period: 24h   # one index file per day

# 7-day log retention
limits_config:
  retention_period: 168h

# Compactor runs retention deletion
compactor:
  retention_enabled: true
```

---

## Promtail Configuration

Config file: `promtail/promtail-config.yml`

Promtail discovers containers via the Docker socket and ships their logs to Loki.

### Pipeline for `ecommerce-api`

```yaml
pipeline_stages:
  # 1. Parse the stdout JSON
  - json:
      expressions:
        level:       level
        message:     message
        service:     service
        timestamp:   timestamp
        method:      "extra.method"
        status_code: "extra.status_code"
        duration_ms: "extra.duration_ms"
        order_id:    "extra.order_id"

  # 2. Promote parsed fields to Loki labels
  - labels:
      level:
      service:
      method:
      status_code:

  # 3. Set @timestamp from the app's own timestamp
  - timestamp:
      source: timestamp
      format: RFC3339Nano

  # 4. Use the "message" field as the log line body
  - output:
      source: message
```

The result: each log line is stored as the human-readable `message` string, but it is tagged with `level`, `service`, `method`, and `status_code` labels for fast filtering.

---

## LogQL Query Reference

### Label Selectors (always required)

```logql
# All app logs
{job="ecommerce-api"}

# Errors only
{job="ecommerce-api", level="ERROR"}

# POST requests
{job="ecommerce-api", method="POST"}

# 4xx responses
{job="ecommerce-api", status_code=~"4.."}

# Multiple label matchers
{job="ecommerce-api", level=~"ERROR|WARNING", method="POST"}
```

### Line Filters (fast, no parsing needed)

```logql
# Contains keyword
{job="ecommerce-api"} |= "Order created"

# Does not contain
{job="ecommerce-api"} != "/health"

# Regex match
{job="ecommerce-api"} |~ "ORD-[A-Z0-9]+"

# Not matching regex
{job="ecommerce-api"} !~ "simulate"
```

### JSON Parsing and Field Filters

```logql
# Parse the log body as JSON, then filter
{job="ecommerce-api"} | json | extra_duration_ms > 200

# Filter by extracted field value
{job="ecommerce-api"} | json | extra_status_code >= 400

# Multiple field filters
{job="ecommerce-api"} | json | extra_status_code >= 400 | extra_duration_ms > 100

# Specific user's activity
{job="ecommerce-api"} | json | extra_user_id = "user_0042"

# Specific order
{job="ecommerce-api"} | json | extra_order_id = "ORD-A1B2C3D4"
```

### Formatting Log Lines

```logql
# Reformat log output
{job="ecommerce-api"} |= "Order created"
| json
| line_format "{{.extra_order_id}} | {{.extra_user_id}} | {{.extra_product_name}} | ${{.extra_total}}"

# Show only relevant fields
{job="ecommerce-api", level="ERROR"}
| json
| line_format "[{{.level}}] {{.message}} — error_type={{.extra_error_type}}"
```

### Metric Queries

These return a time-series that Grafana can graph:

```logql
# Log volume by level per minute
sum(count_over_time({job="ecommerce-api"}[1m])) by (level)

# Error rate (lines/sec)
sum(rate({job="ecommerce-api", level="ERROR"}[5m]))

# Request rate from logs (by method)
sum(rate({job="ecommerce-api"}[1m])) by (method)

# Average request duration (from JSON body)
avg_over_time(
  {job="ecommerce-api"}
  | json
  | unwrap extra_duration_ms [1m]
)

# p95 request duration from logs
quantile_over_time(0.95,
  {job="ecommerce-api"}
  | json
  | unwrap extra_duration_ms [5m]
)
```

---

## Loki Health & Metrics

```bash
# Ready check
curl http://localhost:3100/ready

# Loki's own metrics (scraped by Prometheus)
curl http://localhost:3100/metrics | grep -E "^loki_(ingester|distributor|compactor)"

# List all active streams (labels)
curl "http://localhost:3100/loki/api/v1/labels"

# List values for the 'level' label
curl "http://localhost:3100/loki/api/v1/label/level/values"

# Query via API (last 15 minutes of errors)
curl -G http://localhost:3100/loki/api/v1/query_range \
  --data-urlencode 'query={job="ecommerce-api", level="ERROR"}' \
  --data-urlencode 'start='$(date -d '15 minutes ago' +%s%N) \
  --data-urlencode 'end='$(date +%s%N) \
  --data-urlencode 'limit=20' | jq .
```

---

## Common Pitfalls

**"Stream selector is required" error:**  
Every LogQL query must start with `{label="value"}`. There is no way to query across all streams without a label selector.

**High cardinality labels:**  
Never put high-cardinality values (user IDs, request IDs, trace IDs, order IDs) as Loki labels. Use `| json` to access them in the log body at query time.

**"Too many outstanding requests" or slow queries:**  
Add more specific label filters to reduce the number of chunks that need to be scanned. A query like `{job="ecommerce-api", level="ERROR"}` scans far fewer chunks than `{job="ecommerce-api"}`.

**Timestamps out of order:**  
Loki rejects log lines with timestamps older than the ingestion time minus the `reject_old_samples_max_age` limit (default 1 week). Ensure the app's clock is accurate.
