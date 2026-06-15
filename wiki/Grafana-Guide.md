# Grafana Guide

Grafana is the unified visualisation layer for both **Prometheus metrics** and **Loki logs**. It is pre-configured with auto-provisioned datasources and a ready-to-use dashboard.

---

## Logging In

URL: http://localhost:3000  
Username: `admin`  
Password: `admin123`

---

## Pre-Built Dashboard

Navigate to **Dashboards → Monitoring Demo → E-Commerce Observability**.

The dashboard refreshes every 30 seconds and contains the following sections:

### 📊 Key Metrics (row 1)

Six stat panels showing current values with colour-coded thresholds:

| Panel | Metric | Thresholds |
|---|---|---|
| Request Rate | `sum(rate(http_requests_total[1m]))` | green < 50 req/s, red > 100 |
| Error Rate | 5xx / total ratio | green < 5%, red > 10% |
| p95 Latency | `histogram_quantile(0.95, ...)` | green < 500ms, red > 1s |
| Active Users | `active_users_total` | blue (informational) |
| Total Orders | `sum(orders_total{status="completed"})` | green |
| Total Errors | `sum(application_errors_total)` | green < 5, red > 20 |

### 📈 Request Throughput & Latency (row 2)

- **HTTP Request Rate by Endpoint** — smoothed line chart, `rate([1m])`, legend shows mean + max
- **Request Latency Percentiles** — p50, p95, p99 per endpoint

### 🛒 Business Metrics (row 3)

- **Orders by Category** — stacked area bars showing `rate(orders_total{status="completed"}[5m])` by category
- **Order Status Distribution** — donut pie chart: completed vs. rejected vs. viewed
- **Inventory Levels** — gauge panel per product; turns red below 20 units

### 🔴 Errors & Reliability (row 4)

- **Application Errors by Type** — stacked bar chart of `increase(application_errors_total[5m])` by `error_type`
- **HTTP Error Rate by Status Code** — 4xx and 5xx as percentage of total traffic

### 📋 Logs (Loki) (row 5)

- **Application Logs — Error & Warning** — live Loki log panel filtered to `level=~"ERROR|WARNING"`
- **Log Volume by Level** — stacked bar chart of log line counts per minute by level
- **Recent Order Events** — log panel filtered to lines containing `"Order created"`

### 🖥️ Infrastructure (row 6)

- **CPU Usage** — host CPU utilisation from Node Exporter
- **Memory Usage** — used vs. total memory
- **Network I/O** — receive and transmit bytes/sec

---

## Explore — Ad-Hoc Queries

Click the compass icon (Explore) in the left sidebar to run free-form queries without a dashboard.

### Using Prometheus in Explore

Select the `Prometheus` datasource. Example queries:

```promql
# Active orders over time
sum(rate(orders_total[5m])) by (status)

# Payment processing latency heatmap
rate(payment_processing_duration_seconds_bucket[5m])
```

### Using Loki in Explore

Select the `Loki` datasource. **Always start with a label selector** — Loki requires at least one label filter.

#### Basic queries

```logql
# All logs from the app
{job="ecommerce-api"}

# Errors only
{job="ecommerce-api", level="ERROR"}

# Filter by keyword
{job="ecommerce-api"} |= "Order created"

# Exclude health check noise
{job="ecommerce-api"} != "/health"
```

#### JSON parsing and field filters

```logql
# Parse JSON and filter on a nested field
{job="ecommerce-api"} | json | extra_status_code >= 400

# Slow requests (> 200ms)
{job="ecommerce-api"} | json | extra_duration_ms > 200

# Orders for a specific user
{job="ecommerce-api"} | json | extra_user_id = "user_0042"

# Orders for a specific product
{job="ecommerce-api"} | json | extra_product_id = "p001"
```

#### Formatting output

```logql
# Extract key fields into a readable line
{job="ecommerce-api"} |= "Order created"
| json
| line_format "{{.extra_order_id}} user={{.extra_user_id}} product={{.extra_product_name}} total=${{.extra_total}}"
```

#### Metric queries (LogQL → Grafana graphs)

```logql
# Log volume per minute by level
sum(count_over_time({job="ecommerce-api"}[1m])) by (level)

# Error rate from logs (lines per second containing "ERROR")
sum(rate({job="ecommerce-api", level="ERROR"}[5m]))

# Average request duration extracted from logs (approximate)
avg_over_time(
  {job="ecommerce-api"}
  | json
  | unwrap extra_duration_ms [1m]
)
```

---

## Creating a New Panel

1. Open the **E-Commerce Observability** dashboard
2. Click **Add → Visualization**
3. Select datasource (`Prometheus` or `Loki`)
4. Enter your query
5. Choose a visualization type (Time series, Stat, Gauge, Logs, etc.)
6. Set a title and save

Example — add a panel for payment latency p99:

- **Datasource:** Prometheus  
- **Query:** `histogram_quantile(0.99, rate(payment_processing_duration_seconds_bucket[5m]))`  
- **Legend:** `p99 payment`  
- **Unit:** seconds (`s`)  
- **Visualization:** Time series

---

## Correlating Metrics and Logs

Grafana's real power is correlating time-series anomalies with log events:

1. Spot a latency spike on the **Request Latency Percentiles** panel
2. Click the spike to set the time range
3. Open **Explore** with the same time range
4. Query Loki: `{job="ecommerce-api", level="ERROR"} | json | extra_duration_ms > 500`

This workflow is the "metrics → logs drill-down" pattern that Grafana + Loki is designed for.

---

## Datasource Configuration

Datasources are provisioned from `grafana/provisioning/datasources/datasources.yml`. They are read-only in the UI (`editable: false`).

| UID | Type | URL |
|---|---|---|
| `prometheus` | Prometheus | `http://prometheus:9090` |
| `loki` | Loki | `http://loki:3100` |

To add a new datasource (e.g., Elasticsearch), add it to the YAML file and restart Grafana:
```bash
docker compose restart grafana
```

---

## Dashboard Provisioning

The dashboard JSON lives in `grafana/provisioning/dashboards/ecommerce-overview.json`. Changes to this file are picked up automatically every 30 seconds (no restart needed — the provider polls).

To export a dashboard you've modified in the UI:
1. Open the dashboard
2. Click the share icon → **Export** → **Save to file**
3. Replace `grafana/provisioning/dashboards/ecommerce-overview.json` with the exported file
