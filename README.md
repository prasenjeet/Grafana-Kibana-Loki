# Grafana · Kibana · Loki — Full Observability Demo Stack

A production-inspired monitoring sample project demonstrating unified observability with:

- **Metrics** → Prometheus → Grafana
- **Logs (stream)** → Promtail → Loki → Grafana
- **Logs (search)** → Filebeat → Elasticsearch → Kibana

The sample workload is a Flask-based e-commerce API that emits both Prometheus metrics and structured JSON logs, backed by a traffic generator that keeps dashboards alive with realistic data.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Observability Demo Stack                         │
│                                                                         │
│   ┌─────────────────┐                                                   │
│   │  ecommerce-api  │──── /metrics ──────────► Prometheus ──► Grafana  │
│   │  (Flask + gunicorn)                                                 │
│   │  port 5000      │──── stdout (JSON) ──────► Promtail  ──► Loki     │
│   └────────┬────────┘         │                                └──► Grafana
│            │                  │                                         │
│   ┌────────▼────────┐         └──── Docker log ─► Filebeat             │
│   │traffic-generator│                                └──► Elasticsearch │
│   └─────────────────┘                                        └──► Kibana│
│                                                                         │
│   Node Exporter ──────────────────────────────► Prometheus              │
│   cAdvisor ───────────────────────────────────► Prometheus              │
└─────────────────────────────────────────────────────────────────────────┘
```

### Service Map

| Service | Role | Port |
|---|---|---|
| `ecommerce-api` | Sample app – emits metrics + JSON logs | 5000 |
| `traffic-generator` | Drives realistic API traffic | – |
| **Prometheus** | Metrics scraper & TSDB | 9090 |
| **Grafana** | Unified dashboard (Prometheus + Loki) | 3000 |
| **Loki** | Log aggregation (like Elasticsearch but for streams) | 3100 |
| **Promtail** | Log shipper → Loki (like Filebeat → Elasticsearch) | 9080 |
| **Elasticsearch** | Full-text log search & analytics | 9200 |
| **Kibana** | Log exploration UI for Elasticsearch | 5601 |
| **Filebeat** | Log shipper → Elasticsearch | – |
| **Node Exporter** | Host-level OS metrics | 9100 |
| **cAdvisor** | Container-level metrics | 8080 |
| **es-setup** | One-shot: creates ES index template + Kibana data view | – |

---

## Prerequisites

- Docker ≥ 24 and Docker Compose v2
- ~4 GB of free RAM (Elasticsearch is memory-hungry)
- Linux: `vm.max_map_count` must be ≥ 262144

```bash
# Linux only – required for Elasticsearch
sudo sysctl -w vm.max_map_count=262144
# Persist across reboots:
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
```

---

## Quick Start

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd Grafana-Kibana-Loki

# 2. (Linux) Set vm.max_map_count
sudo sysctl -w vm.max_map_count=262144

# 3. Start the full stack
docker compose up -d --build

# 4. Wait ~2 minutes for all services to become healthy
docker compose ps
```

### Access the UIs

| UI | URL | Credentials |
|---|---|---|
| **Grafana** | http://localhost:3000 | admin / admin123 |
| **Kibana** | http://localhost:5601 | – (no auth in demo mode) |
| **Prometheus** | http://localhost:9090 | – |
| **ecommerce-api** | http://localhost:5000 | – |
| **cAdvisor** | http://localhost:8080 | – |

---

## Exploring the Stack

### Grafana (Metrics + Logs unified)

1. Open http://localhost:3000 and log in.
2. Navigate to **Dashboards → Monitoring Demo → E-Commerce Observability**.
3. The dashboard shows:
   - Request rate, error rate, p95 latency, active users, orders, errors (stat panels)
   - Request throughput and latency percentiles per endpoint (time series)
   - Business metrics: orders by category, status distribution, inventory gauge
   - Error breakdown by type and HTTP status code
   - Live application logs from Loki (errors/warnings + order events)
   - Host CPU, memory, and network I/O from Node Exporter

**LogQL queries to try in Explore:**
```logql
# All error logs
{job="ecommerce-api", level="ERROR"}

# Slow requests (> 200ms)
{job="ecommerce-api"} | json | extra_duration_ms > 200

# Orders created in the last 15 minutes
{job="ecommerce-api"} |= "Order created" | json | line_format "{{.extra_order_id}} – {{.extra_product_name}} – ${{.extra_total}}"

# Log volume by level over time
sum(count_over_time({job="ecommerce-api"}[1m])) by (level)
```

### Kibana (Full-text search on Elasticsearch)

1. Open http://localhost:5601.
2. Go to **Discover** → select the `ecommerce-logs-*` data view.
3. Useful KQL queries:
   ```
   app.level: "ERROR"
   app.extra.status_code >= 400
   app.extra.order_id: ORD-*
   app.extra.duration_ms > 100 AND app.extra.method: "POST"
   ```
4. Go to **Stack Management → Index Management** to see the ILM-managed index.

### Prometheus (PromQL)

Open http://localhost:9090/graph and try:
```promql
# 95th percentile latency per endpoint
histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint))

# Order completion rate
sum(rate(orders_total{status="completed"}[5m])) by (category)

# Error budget burn rate
sum(rate(application_errors_total[5m])) / sum(rate(http_requests_total[5m]))

# Inventory below threshold
inventory_items_total < 30
```

---

## Triggering Demo Events

The traffic generator runs automatically. You can also trigger events manually:

```bash
BASE=http://localhost:5000

# Browse products
curl "$BASE/api/products"
curl "$BASE/api/products?category=electronics"
curl "$BASE/api/products/p001"

# Place an order
curl -X POST "$BASE/api/orders" \
  -H "Content-Type: application/json" \
  -d '{"product_id": "p001", "quantity": 1, "user_id": "user_0042"}'

# Simulate load burst
curl "$BASE/api/simulate/load"

# Trigger an application error (appears in error panels + Loki)
curl "$BASE/api/simulate/error"
```

---

## Project Layout

```
.
├── app/
│   ├── app.py                  # Flask e-commerce API (metrics + structured logging)
│   ├── traffic_generator.py    # Continuous traffic simulator
│   ├── requirements.txt
│   └── Dockerfile
├── prometheus/
│   ├── prometheus.yml          # Scrape config (app, node-exporter, cadvisor, loki)
│   └── alert_rules.yml         # Example alerting rules
├── grafana/
│   └── provisioning/
│       ├── datasources/
│       │   └── datasources.yml # Prometheus + Loki datasources (auto-provisioned)
│       └── dashboards/
│           ├── dashboard.yml   # Dashboard provider config
│           └── ecommerce-overview.json  # Pre-built dashboard
├── loki/
│   └── loki-config.yml         # Loki single-binary config (TSDB, filesystem storage)
├── promtail/
│   └── promtail-config.yml     # Docker SD → JSON parse pipeline → Loki
├── elasticsearch/
│   └── elasticsearch.yml       # ES single-node config
├── kibana/
│   └── kibana.yml              # Kibana config (points to ES, no auth)
├── filebeat/
│   └── filebeat.yml            # Container log collection → ES ingest pipeline
├── scripts/
│   └── setup-elasticsearch.sh  # Creates ILM policy, index template, ingest pipeline
└── docker-compose.yml          # Wires all services together
```

---

## Design Decisions

### Loki vs. Elasticsearch — When to use each

| | **Loki (+ Grafana)** | **Elasticsearch (+ Kibana)** |
|---|---|---|
| Inspired by | Prometheus (label-based index) | Traditional search (inverted index) |
| Storage cost | Very low – stores raw log lines | Higher – indexes every field |
| Query model | LogQL – label filters first, then line filters | KQL / Lucene – full-text search anywhere |
| Best for | Tailing logs, correlating with metrics | Analysing structured fields, ad-hoc search |
| Setup complexity | Minimal | Higher (ILM, mappings, pipelines) |

This project runs **both** so you can compare them side-by-side with the same log stream.

### Prometheus-inspired patterns in Loki

- Loki uses **labels** (not full-text index) as the primary index, just like Prometheus uses labels for metrics.
- `promtail` mirrors `node_exporter` / `blackbox_exporter` in the Prometheus ecosystem – it is a dedicated agent that scrapes and forwards data.
- LogQL mirrors PromQL: start with label matchers `{job="..."}`, then apply filters and aggregations.

---

## Stopping the Stack

```bash
# Stop and remove containers (keeps volumes)
docker compose down

# Stop and remove everything including volumes
docker compose down -v
```

---

## Troubleshooting

**Elasticsearch fails to start with `max virtual memory areas` error:**
```bash
sudo sysctl -w vm.max_map_count=262144
```

**Grafana shows "No data" on Loki panels:**
- Ensure Promtail can reach the Docker socket: `docker logs promtail`
- Check Loki is ready: `curl http://localhost:3100/ready`

**Kibana shows no index:**
- Wait for `es-setup` to complete: `docker logs es-setup`
- Manually trigger setup: `docker compose run --rm es-setup`

**Check service health at a glance:**
```bash
docker compose ps
docker compose logs --tail=50 <service-name>
```
