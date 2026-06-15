# Getting Started

This page walks you from a fresh clone to a fully running stack with live dashboards.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Docker | ≥ 24.0 | `docker --version` |
| Docker Compose | v2 (plugin) | `docker compose version` |
| Free RAM | ≥ 4 GB | Elasticsearch alone needs ~1.5 GB |
| Free disk | ≥ 5 GB | Images + volumes |
| OS | Linux / macOS / Windows WSL2 | |

### Linux-only: `vm.max_map_count`

Elasticsearch requires a higher virtual memory limit than the default:

```bash
# Apply immediately (lost on reboot)
sudo sysctl -w vm.max_map_count=262144

# Persist across reboots
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
```

---

## Step 1 — Clone

```bash
git clone https://github.com/prasenjeet/Grafana-Kibana-Loki.git
cd Grafana-Kibana-Loki
```

---

## Step 2 — Start the Stack

```bash
docker compose up -d --build
```

This will:
1. Build the `ecommerce-api` and `traffic-generator` images from `app/`
2. Pull all other images (first run takes a few minutes)
3. Start 11 containers in dependency order
4. Run `es-setup` once to create the Elasticsearch index template, ILM policy, ingest pipeline, and Kibana data view

---

## Step 3 — Wait for Health Checks

Services start in dependency order but Elasticsearch and Kibana can take 60–90 seconds to become fully ready. Poll until everything is healthy:

```bash
# Watch until all containers are "healthy" or "running"
watch -n 5 'docker compose ps --format "table {{.Name}}\t{{.Status}}"'
```

Expected output after ~2 minutes:

```
NAME                  STATUS
cadvisor              running
ecommerce-api         running (healthy)
elasticsearch         running (healthy)
es-setup              exited (0)
filebeat              running
grafana               running (healthy)
kibana                running (healthy)
loki                  running (healthy)
node-exporter         running
prometheus            running
promtail              running
traffic-generator     running
```

`es-setup` exiting with code 0 is **correct** — it is a one-shot initialisation container.

---

## Step 4 — Open the UIs

### Grafana
1. Open http://localhost:3000
2. Log in: `admin` / `admin123`
3. Go to **Dashboards → Monitoring Demo → E-Commerce Observability**

The pre-built dashboard should already show live data within 30 seconds of the traffic generator starting.

### Kibana
1. Open http://localhost:5601
2. Click **Discover** in the left sidebar
3. Select the `ecommerce-logs-*` data view from the dropdown
4. Set the time range to **Last 15 minutes**

### Prometheus
1. Open http://localhost:9090
2. Go to **Graph** and paste:
   ```promql
   sum(rate(http_requests_total[1m]))
   ```
3. Click **Execute** → switch to the **Graph** tab

---

## Step 5 — Send a Manual Request

```bash
# List all products
curl http://localhost:5000/api/products

# Place an order
curl -X POST http://localhost:5000/api/orders \
  -H "Content-Type: application/json" \
  -d '{"product_id": "p001", "quantity": 2, "user_id": "user_0001"}'

# Trigger a simulated error (watch it appear in Grafana Loki panel)
curl http://localhost:5000/api/simulate/error
```

---

## Stopping the Stack

```bash
# Stop containers, keep volumes (data persists)
docker compose down

# Stop and wipe all volumes (fresh start next time)
docker compose down -v

# Remove built images too
docker compose down -v --rmi local
```

---

## Re-running After a Stop

Volume data is preserved between `docker compose down` / `docker compose up` cycles (unless you used `-v`). The `es-setup` container will re-run but its operations are idempotent — safe to run multiple times.

```bash
docker compose up -d
```

---

## First-Run Checklist

- [ ] `vm.max_map_count` set to 262144 (Linux)
- [ ] `docker compose ps` shows all services healthy
- [ ] Grafana dashboard loads with data
- [ ] Kibana Discover shows log entries
- [ ] Prometheus graph shows `http_requests_total` increasing
