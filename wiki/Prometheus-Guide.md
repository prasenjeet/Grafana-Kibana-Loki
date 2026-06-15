# Prometheus Guide

Prometheus is the metrics backend. It scrapes targets on a schedule, stores time-series data in a local TSDB, and evaluates alert rules.

---

## Scrape Targets

Open http://localhost:9090/targets to see live scrape status.

| Job | Target | Interval | What it collects |
|---|---|---|---|
| `prometheus` | `localhost:9090` | 15s | Prometheus self-metrics |
| `ecommerce-api` | `ecommerce-api:5000` | **10s** | Application metrics |
| `node-exporter` | `node-exporter:9100` | 15s | Host CPU, memory, disk, network |
| `cadvisor` | `cadvisor:8080` | 20s | Per-container CPU, memory, network |
| `loki` | `loki:3100` | 15s | Loki internal metrics |

The `ecommerce-api` job uses a shorter 10-second interval because application metrics change quickly.

---

## PromQL Query Reference

### Request Throughput

```promql
# Requests per second (all endpoints)
sum(rate(http_requests_total[1m]))

# Requests per second by endpoint
sum(rate(http_requests_total[1m])) by (endpoint)

# Requests per second by HTTP method and status code
sum(rate(http_requests_total[1m])) by (method, status_code)
```

### Error Rate

```promql
# Overall error rate (5xx only)
sum(rate(http_requests_total{status_code=~"5.."}[5m]))
/ sum(rate(http_requests_total[5m]))

# 4xx rate
sum(rate(http_requests_total{status_code=~"4.."}[5m]))
/ sum(rate(http_requests_total[5m]))

# Errors by type
sum(rate(application_errors_total[5m])) by (error_type)
```

### Latency Percentiles

```promql
# p50 overall
histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))

# p95 overall
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))

# p99 per endpoint
histogram_quantile(0.99,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint)
)

# Payment processing p95
histogram_quantile(0.95, rate(payment_processing_duration_seconds_bucket[5m]))
```

### Business Metrics

```promql
# Order rate by category
sum(rate(orders_total{status="completed"}[5m])) by (category)

# Total completed orders (counter)
sum(orders_total{status="completed"})

# Inventory — items with stock below 30
inventory_items_total < 30

# Inventory per product (instant)
inventory_items_total
```

### Infrastructure

```promql
# CPU usage (as fraction 0–1)
1 - avg(rate(node_cpu_seconds_total{mode="idle"}[2m]))

# Memory used
node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes

# Memory usage percent
(node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes)
/ node_memory_MemTotal_bytes

# Disk usage per mount
1 - (node_filesystem_avail_bytes / node_filesystem_size_bytes)

# Network receive rate
sum(rate(node_network_receive_bytes_total[2m]))

# Container CPU per container (from cAdvisor)
sum(rate(container_cpu_usage_seconds_total{name!=""}[2m])) by (name)

# Container memory per container
sum(container_memory_usage_bytes{name!=""}) by (name)
```

### Loki Self-Monitoring

```promql
# Loki ingestion rate
sum(rate(loki_distributor_bytes_received_total[5m]))

# Active Loki streams
loki_ingester_streams_created_total - loki_ingester_streams_removed_total
```

---

## Alert Rules

Alert rules are defined in `prometheus/alert_rules.yml` and evaluated every 15 seconds.

### `HighErrorRate`

Fires when the application error rate exceeds 0.1 errors/second over 5 minutes, sustained for 2 minutes.

```yaml
expr: rate(application_errors_total[5m]) > 0.1
for: 2m
severity: warning
```

### `HighRequestLatency`

Fires when the 95th percentile request latency exceeds 1 second over 5 minutes, sustained for 3 minutes.

```yaml
expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 1.0
for: 3m
severity: warning
```

### `LowInventory`

Fires when any product's stock falls below 10 units.

```yaml
expr: inventory_items_total < 10
for: 1m
severity: info
```

### `ServiceDown`

Fires when `ecommerce-api` stops being scraped successfully for more than 1 minute.

```yaml
expr: up{job="ecommerce-api"} == 0
for: 1m
severity: critical
```

---

## Adding a New Alert Rule

Edit `prometheus/alert_rules.yml` and add to the `ecommerce_alerts` group:

```yaml
- alert: HighPaymentLatency
  expr: |
    histogram_quantile(0.95, rate(payment_processing_duration_seconds_bucket[5m])) > 2.0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Payment processing taking too long"
    description: "p95 payment latency is {{ $value | humanizeDuration }}"
```

Then reload Prometheus config without restarting:

```bash
curl -X POST http://localhost:9090/-/reload
```

---

## Prometheus Web UI Tips

- **Graph tab:** Interactive PromQL with time range selection
- **Table tab:** Instant vector — useful to see current label cardinality
- **http://localhost:9090/targets:** Live scrape status + last error
- **http://localhost:9090/rules:** Loaded alert rules + current state
- **http://localhost:9090/alerts:** Currently firing alerts
- **http://localhost:9090/config:** Active configuration (post-reload)
- **http://localhost:9090/tsdb-status:** Top metric names by series count

---

## Storage

Prometheus data is stored in the `prometheus_data` Docker volume at `/prometheus` inside the container. Retention is 15 days (`--storage.tsdb.retention.time=15d`).

To inspect TSDB metadata:
```bash
docker exec prometheus promtool tsdb analyze /prometheus
```
