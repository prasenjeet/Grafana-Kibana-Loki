# Grafana · Kibana · Loki — Observability Demo Stack

Welcome to the project wiki. This stack demonstrates **unified observability** for a sample e-commerce API using the two most popular open-source monitoring ecosystems running side-by-side.

---

## What This Project Shows

| Concern | Grafana Ecosystem | Elastic Ecosystem |
|---|---|---|
| **Metrics** | Prometheus → Grafana | *(Prometheus also scrapes)*  |
| **Log streaming** | Promtail → Loki → Grafana | – |
| **Log search** | – | Filebeat → Elasticsearch → Kibana |
| **Inspiration** | Prometheus pull model | Elasticsearch push model |

The same application emits the same log lines into **both** pipelines so you can compare query languages, storage costs, and UX side-by-side.

---

## Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Observability Demo Stack                        │
│                                                                     │
│  ┌──────────────────┐                                               │
│  │  ecommerce-api   │─── /metrics ────────► Prometheus ──► Grafana │
│  │  Flask · port 5000                                               │
│  │                  │─── stdout JSON ─────► Promtail  ──► Loki     │
│  └────────┬─────────┘         │                           └► Grafana│
│           │                   └── Docker log ─► Filebeat           │
│  ┌────────▼─────────┐                              └► Elasticsearch │
│  │traffic-generator │                                     └► Kibana │
│  └──────────────────┘                                               │
│  Node Exporter ────────────────────────────► Prometheus             │
│  cAdvisor ─────────────────────────────────► Prometheus             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Service Ports

| Service | URL | Credentials |
|---|---|---|
| **Grafana** | http://localhost:3000 | admin / admin123 |
| **Kibana** | http://localhost:5601 | *(none)* |
| **Prometheus** | http://localhost:9090 | *(none)* |
| **ecommerce-api** | http://localhost:5000 | *(none)* |
| **Elasticsearch** | http://localhost:9200 | *(none)* |
| **cAdvisor** | http://localhost:8080 | *(none)* |
| **Node Exporter** | http://localhost:9100 | *(none)* |
| **Loki** | http://localhost:3100 | *(none)* |

---

## Wiki Pages

| Page | What you'll find |
|---|---|
| [[Getting Started]] | Prerequisites, `docker compose up`, first-run checklist |
| [[Architecture]] | Component deep-dive, data flows, design decisions |
| [[Application API]] | All REST endpoints with curl examples |
| [[Prometheus Guide]] | Scrape config, PromQL queries, alert rules |
| [[Grafana Guide]] | Dashboard walkthrough, panel reference, LogQL in Explore |
| [[Loki Guide]] | Loki config, label schema, LogQL examples |
| [[Kibana Guide]] | Data view setup, KQL queries, index management |
| [[Elasticsearch Guide]] | Index template, ILM policy, ingest pipeline |
| [[Troubleshooting]] | Common issues and fixes |
| [[Configuration Reference]] | Every config file key explained |

---

## Quick Start (TL;DR)

```bash
# Linux prerequisite
sudo sysctl -w vm.max_map_count=262144

# Start everything
docker compose up -d --build

# Tail logs
docker compose logs -f ecommerce-api

# Stop
docker compose down
```

---

## Loki vs. Elasticsearch — The Core Insight

Loki was **deliberately designed to mirror Prometheus** for logs:

- Prometheus indexes by **labels** only, not metric values → very cheap storage  
- Loki indexes by **labels** only, not log content → very cheap storage  
- Elasticsearch indexes **every field** of every document → powerful search, higher cost

Running both lets you experience the trade-off directly.
