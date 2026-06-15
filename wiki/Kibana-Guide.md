# Kibana Guide

Kibana is the visualisation and exploration UI for Elasticsearch. In this stack it provides full-text search and structured analysis of the same logs that Loki streams — giving you a direct comparison between the two approaches.

---

## Accessing Kibana

URL: http://localhost:5601  
No authentication required in demo mode.

---

## Data View

The `es-setup` initialisation container automatically creates a Kibana **data view** named `ecommerce-logs-*` pointing at the `ecommerce-logs-YYYY.MM.DD` indices.

If the data view is missing:
1. Go to **Stack Management → Data Views**
2. Click **Create data view**
3. Name: `Ecommerce Logs`, Index pattern: `ecommerce-logs-*`, Timestamp: `@timestamp`

---

## Discover

**Discover** is Kibana's equivalent of Grafana Explore for Elasticsearch.

1. Click **Discover** in the left sidebar
2. Select `ecommerce-logs-*` from the data view dropdown
3. Set time range to **Last 15 minutes** (top-right corner)

You should see log documents flowing in from Filebeat.

### Document Structure

Each document has two field namespaces:

```
@timestamp            ← parsed from app.timestamp by the ingest pipeline
level                 ← promoted from app.level
service               ← promoted from app.service
message               ← original raw log line
app.level             ← from JSON decode
app.message           ← human-readable message
app.service           ← "ecommerce-api"
app.version           ← "1.0.0"
app.extra.method      ← HTTP method
app.extra.path        ← URL path
app.extra.status_code ← HTTP status code (integer)
app.extra.duration_ms ← request duration in milliseconds (float)
app.extra.order_id    ← order ID (on order events)
app.extra.user_id     ← user ID
app.extra.product_id  ← product ID
app.extra.total       ← order total (float)
app.extra.error_type  ← error category
docker.*              ← container metadata from Filebeat
host.*                ← host metadata
```

---

## KQL Query Reference

KQL (Kibana Query Language) is used in the search bar.

### Basic Field Queries

```kql
# Filter by log level
app.level: "ERROR"

# Multiple values (OR)
app.level: ("ERROR" or "WARNING")

# Exact service match
app.service: "ecommerce-api"
```

### Numeric Comparisons

```kql
# HTTP errors (4xx and 5xx)
app.extra.status_code >= 400

# Only 5xx
app.extra.status_code >= 500

# Slow requests (> 200ms)
app.extra.duration_ms > 200

# Slow requests that also errored
app.extra.duration_ms > 200 AND app.extra.status_code >= 400

# Orders above $100
app.extra.total > 100
```

### Wildcard and Text Search

```kql
# Orders (by order ID pattern)
app.extra.order_id: ORD-*

# Specific user
app.extra.user_id: "user_0042"

# Full-text search in the message field
app.message: "Order created"

# Any error type containing "timeout"
app.extra.error_type: *timeout*
```

### Boolean Logic

```kql
# POST requests that returned 400
app.extra.method: "POST" AND app.extra.status_code: 400

# Errors that are NOT simulated
app.level: "ERROR" AND NOT app.extra.simulated: true

# Orders in electronics or audio
app.extra.category: ("electronics" or "audio")
```

### Exists / Missing Checks

```kql
# Logs that have an order_id (i.e., order events)
app.extra.order_id: *

# Logs without a duration (non-HTTP events)
NOT app.extra.duration_ms: *
```

---

## Useful Saved Searches

Create these in Discover and save for quick access:

| Name | KQL | Useful for |
|---|---|---|
| All Errors | `app.level: "ERROR"` | Error monitoring |
| Slow Requests | `app.extra.duration_ms > 200` | Performance |
| Order Events | `app.extra.order_id: ORD-*` | Business events |
| 5xx Responses | `app.extra.status_code >= 500` | Server errors |
| Payment Events | `app.message: "payment"` | Payment processing |

---

## Dashboard (Lens)

Kibana's **Lens** editor can build dashboards from Elasticsearch aggregations.

### Example: Requests by Status Code Over Time

1. Go to **Dashboards → Create dashboard**
2. Click **Add panel → Lens**
3. Drag `@timestamp` to the X-axis, `Count` to the Y-axis
4. Add a **Break down by** → `app.extra.status_code` (keyword)
5. Choose **Bar stacked** chart type

### Example: Error Rate Table

1. **Lens → Table**
2. Rows: `app.extra.error_type`
3. Metric: **Count** → rename to "Error Count"
4. Add second metric: **Percentile** of `@timestamp` → rename to "Latest occurrence"

---

## Index Management

### View Indices

**Stack Management → Index Management → Indices**

You should see `ecommerce-logs-YYYY.MM.DD` indices. Each day gets a new index due to the Filebeat template pattern.

### View ILM Policy

**Stack Management → Index Lifecycle Policies → ecommerce-logs-policy**

The policy has three phases:
- **Hot** (day 0): Active writes, rollover at 1d or 1 GB
- **Warm** (day 3): Read-only, forcemerge to 1 segment, shrink to 1 shard
- **Delete** (day 7): Index deleted automatically

### View Index Template

**Stack Management → Index Management → Index Templates → ecommerce-logs**

The template defines:
- Field mappings (keyword, integer, float types for `app.extra.*`)
- Default number of shards (1) and replicas (0)
- ILM policy assignment

### Manually Refresh the Data View

If new fields appear and Kibana doesn't show them:

**Stack Management → Data Views → ecommerce-logs-* → Refresh field list**

---

## Direct Elasticsearch REST Queries

For exploration beyond Kibana:

```bash
ES=http://localhost:9200

# Cluster health
curl "$ES/_cluster/health?pretty"

# List indices
curl "$ES/_cat/indices/ecommerce-logs-*?v"

# Count documents
curl "$ES/ecommerce-logs-*/_count?pretty"

# Search – last 10 error documents
curl -s "$ES/ecommerce-logs-*/_search" \
  -H "Content-Type: application/json" \
  -d '{
    "size": 10,
    "sort": [{ "@timestamp": "desc" }],
    "query": {
      "term": { "level": "ERROR" }
    }
  }' | jq '.hits.hits[]._source.app.message'

# Aggregation – error count by type
curl -s "$ES/ecommerce-logs-*/_search" \
  -H "Content-Type: application/json" \
  -d '{
    "size": 0,
    "aggs": {
      "by_error_type": {
        "terms": { "field": "app.extra.error_type" }
      }
    }
  }' | jq '.aggregations.by_error_type.buckets'
```
