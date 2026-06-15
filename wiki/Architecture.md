# Architecture

A deep-dive into how the components connect, why they were configured the way they are, and the key design decisions.

---

## Full Component Graph

```
                        ┌─────────────────────────────────────┐
                        │           Docker Network             │
                        │          (172.20.0.0/16)             │
                        │                                      │
  ┌─────────────────────┤                                      │
  │  ecommerce-api      │  GET /metrics (port 5000)            │
  │  Flask + gunicorn   │◄────────────────────── Prometheus    │
  │                     │                             │        │
  │  • Prometheus client│  stdout (JSON logs)         │        │
  │  • JSON logger      │──────────────► Promtail     │        │
  │                     │                    │        │        │
  │  port 5000          │  Docker log driver │        │        │
  └─────────────────────┤──────────────► Filebeat     │        │
                        │                    │        │        │
  ┌─────────────────────┤                    │        │        │
  │  traffic-generator  │                    ▼        ▼        │
  │  (Python requests)  │               Elasticsearch  Loki    │
  └─────────────────────┤                    │        │        │
                        │                    ▼        │        │
  ┌─────────────────────┤                 Kibana      │        │
  │  node-exporter      │                             │        │
  │  cadvisor           │◄────────── Prometheus ◄─────┘        │
  └─────────────────────┤                 │                    │
                        │                 ▼                    │
                        │              Grafana                 │
                        │         (Prometheus + Loki)          │
                        └─────────────────────────────────────┘
```

---

## Data Flows

### Flow 1 — Prometheus Metrics

```
ecommerce-api
  └─ prometheus_client library
       └─ Counter, Histogram, Gauge objects updated on every request
            └─ /metrics endpoint (text/plain Prometheus exposition format)
                 └─ Prometheus scrapes every 10s
                      └─ TSDB (15-day retention, /prometheus volume)
                           └─ Grafana queries via PromQL
```

**Key insight:** Prometheus *pulls* metrics on a schedule. The application just needs to expose the `/metrics` endpoint; it never pushes to Prometheus.

### Flow 2 — Loki Log Stream

```
ecommerce-api (gunicorn stdout)
  └─ JsonFormatter → structured JSON per log line
       └─ Docker json-file log driver (max 10 MB / 3 files)
            └─ Promtail Docker SD discovers container by name
                 └─ pipeline_stages:
                      ├─ json: extract level, service, extra.* fields
                      ├─ labels: promote level, service, method, status_code
                      ├─ timestamp: parse app timestamp as @timestamp
                      └─ output: use message field as log line
                           └─ Loki HTTP push API (batch, 1s / 1 MB)
                                └─ TSDB chunks on /loki volume (7-day retention)
                                     └─ Grafana queries via LogQL
```

**Key insight:** Loki stores the raw log line + a small set of indexed labels. Querying first filters by labels (cheap), then scans matching chunks for content matches (linear over matching lines only).

### Flow 3 — Elasticsearch Full-Text

```
ecommerce-api (Docker log driver)
  └─ /var/lib/docker/containers/*/*.log
       └─ Filebeat container input (Docker SD autodiscover)
            └─ decode_json_fields processor: message → app.*
                 └─ output.elasticsearch → ecommerce-ingest pipeline
                      ├─ json processor: parse message again
                      ├─ date processor: app.timestamp → @timestamp
                      └─ set processors: promote level, service
                           └─ ecommerce-logs-YYYY.MM.DD index
                                ├─ ILM rollover: 1d / 1 GB → warm (3d) → delete (7d)
                                └─ Kibana data view: ecommerce-logs-*
```

**Key insight:** Every field in `app.*` is indexed by Elasticsearch. You can search any field instantly without scanning, but each document costs more storage.

---

## Component Responsibilities

### ecommerce-api
- The only application under observation
- Exposes `/metrics` in Prometheus exposition format via `prometheus_client`
- Writes structured JSON to stdout on every request and business event
- Never knows whether Loki or Elasticsearch is receiving its logs

### Prometheus
- Scrapes 4 targets: `ecommerce-api`, `node-exporter`, `cadvisor`, `loki`
- Stores 15 days of time-series data
- Evaluates 4 alert rules every 15 seconds
- Does **not** alert anywhere in this demo (alertmanager is empty)

### Loki
- Single-binary deployment (stores everything locally in `/loki`)
- Schema v13 (TSDB object store)
- Streams stored as compressed chunks, indexed only by label set
- 7-day retention via compactor

### Promtail
- Discovers containers via the Docker socket
- Two scrape jobs: `ecommerce-api` (with full JSON parsing) + `containers` (system logs)
- Batches log entries up to 1 MB or 1 second before pushing

### Elasticsearch
- Single-node (`discovery.type: single-node`) – not production-grade
- Security disabled (`xpack.security.enabled: false`) – demo only
- JVM heap: 512 MB (`ES_JAVA_OPTS=-Xms512m -Xmx512m`)
- ILM policy: hot (active) → warm (day 3, forcemerge) → delete (day 7)

### Kibana
- Points to Elasticsearch via `ELASTICSEARCH_HOSTS`
- No authentication in demo mode
- `es-setup` creates the `ecommerce-logs-*` data view automatically

### Filebeat
- Runs as root to access Docker socket and container log files
- `--strict.perms=false` because the config file is mounted read-only and Filebeat checks permissions
- Autodiscover watches for containers matching `image: ecommerce`

### Grafana
- Auto-provisions both datasources (Prometheus + Loki) and the dashboard on startup
- Datasources defined in `grafana/provisioning/datasources/datasources.yml`
- Dashboard JSON in `grafana/provisioning/dashboards/ecommerce-overview.json`
- Admin credentials via environment variables (`GF_SECURITY_ADMIN_*`)

---

## Network Design

All services share a single Docker bridge network `observability` (`172.20.0.0/16`). Service names are DNS-resolvable within the network (e.g., `http://loki:3100`). No inter-service TLS in the demo.

Only ports that need external access are published:

| Container port | Host port | Reason |
|---|---|---|
| ecommerce-api:5000 | 5000 | Manual curl / browser testing |
| prometheus:9090 | 9090 | PromQL exploration |
| grafana:3000 | 3000 | Dashboard UI |
| loki:3100 | 3100 | Optional direct query |
| elasticsearch:9200 | 9200 | Optional direct REST |
| kibana:5601 | 5601 | Kibana UI |
| node-exporter:9100 | 9100 | Optional direct metrics |
| cadvisor:8080 | 8080 | Optional container view |

---

## Volume Strategy

| Volume | Contents | Mounted to |
|---|---|---|
| `prometheus_data` | TSDB blocks + WAL | `/prometheus` |
| `grafana_data` | SQLite DB, plugins, sessions | `/var/lib/grafana` |
| `loki_data` | Chunks, rules, compactor state | `/loki` |
| `elasticsearch_data` | ES index shards + translog | `/usr/share/elasticsearch/data` |

All config files are mounted read-only (`:ro`) from the host so you can edit them and `docker compose restart <service>` without rebuilding.

---

## Loki vs. Elasticsearch Design Comparison

| Dimension | Loki | Elasticsearch |
|---|---|---|
| Index strategy | Label set only | Every JSON field |
| Storage per GB of logs | ~0.05–0.1× compressed | ~1–3× raw (index overhead) |
| Query language | LogQL (label selectors + filters) | KQL / Lucene / ES DSL |
| First filter step | Label matcher (O(1) index lookup) | Inverted index (any field) |
| Aggregations | `count_over_time`, `rate`, `sum by` | Full aggregation framework |
| Metric extraction | Yes (via `metric_extraction` or LogQL) | Via scripted fields / runtime fields |
| Best query pattern | `{job="x"} \| json \| field > value` | `field: value AND other: *` |
| Kibana equivalent | Grafana Explore | Kibana Discover |
