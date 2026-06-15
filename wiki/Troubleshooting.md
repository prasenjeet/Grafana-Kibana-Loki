# Troubleshooting

Common issues and how to fix them.

---

## Quick Diagnostics

```bash
# Overall service status
docker compose ps

# Tail logs from all services (Ctrl+C to stop)
docker compose logs -f

# Tail logs from a specific service
docker compose logs -f elasticsearch
docker compose logs -f kibana
docker compose logs -f loki
docker compose logs -f promtail
docker compose logs -f ecommerce-api

# Check which containers are unhealthy
docker compose ps --filter "health=unhealthy"
```

---

## Elasticsearch Issues

### `max virtual memory areas vm.max_map_count [65530] is too low`

**Cause:** Linux kernel default is too low for Elasticsearch.

**Fix (immediate):**
```bash
sudo sysctl -w vm.max_map_count=262144
```

**Fix (persistent across reboots):**
```bash
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

Then restart Elasticsearch:
```bash
docker compose restart elasticsearch
```

---

### Elasticsearch stays `starting` / never becomes `healthy`

**Check the logs:**
```bash
docker logs elasticsearch --tail=50
```

**Common causes:**
- Insufficient memory — Elasticsearch needs ~1.5 GB. Check `docker stats elasticsearch`
- `vm.max_map_count` too low (see above)
- Port 9200 already in use — `lsof -i :9200`

**Verify health directly:**
```bash
curl http://localhost:9200/_cluster/health?pretty
```

Expected:
```json
{
  "status": "yellow",   # or "green" — both are OK for single-node
  "number_of_nodes": 1,
  "active_shards": ...
}
```

---

### Kibana shows `Unable to connect` or `Kibana server is not ready`

**Cause:** Kibana starts before Elasticsearch is fully ready. The `depends_on: condition: service_healthy` in docker-compose should prevent this, but Elasticsearch startup can sometimes be slow.

**Fix:**
```bash
# Wait a bit longer, then restart Kibana
docker compose restart kibana

# Check Kibana logs
docker logs kibana --tail=30
```

---

### Kibana has no `ecommerce-logs-*` data view

**Cause:** `es-setup` container may have run before Kibana was ready.

**Fix:**
```bash
# Re-run the setup (it is idempotent)
docker compose run --rm es-setup
```

If that fails, create the data view manually:
1. Go to **Stack Management → Data Views → Create data view**
2. Name: `Ecommerce Logs`
3. Index pattern: `ecommerce-logs-*`
4. Timestamp field: `@timestamp`

---

### Kibana Discover shows no documents

**Check Filebeat is running and sending data:**
```bash
docker logs filebeat --tail=30
```

Look for lines like:
```
Events published: 150
```

**Check the index exists:**
```bash
curl http://localhost:9200/_cat/indices/ecommerce-logs-*?v
```

**Check the ingest pipeline:**
```bash
curl http://localhost:9200/_ingest/pipeline/ecommerce-ingest | jq .
```

**Check Kibana time range** — make sure it is set to `Last 15 minutes`, not a future or stale range.

---

## Loki / Promtail Issues

### Grafana Loki panels show "No data"

**Step 1 — Check Loki is ready:**
```bash
curl http://localhost:3100/ready
# Expected: "ready"
```

**Step 2 — Check Promtail can reach Docker socket:**
```bash
docker logs promtail --tail=30
```

Look for lines like:
```
level=info msg="Tailing new file" path="/var/log/..."
```

**Step 3 — Check what streams Loki knows about:**
```bash
curl "http://localhost:3100/loki/api/v1/labels" | jq .
```

If empty, Promtail hasn't sent anything yet.

**Step 4 — Verify the Grafana datasource:**
1. Go to **Configuration → Data Sources → Loki**
2. Scroll down → **Save & Test**
3. Should show "Data source connected and labels found"

---

### Promtail can't access Docker socket

**Symptom:** `promtail` logs contain `permission denied: /var/run/docker.sock`

**Fix:** Ensure the Docker socket is mounted correctly. Check `docker-compose.yml`:
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock:ro
```

On some systems, you may need to add the `promtail` user to the `docker` group:
```bash
docker exec promtail id
# Then adjust ownership if needed
```

---

## Prometheus Issues

### `ecommerce-api` target shows as `DOWN` in Prometheus

**Check the app is healthy:**
```bash
curl http://localhost:5000/health
curl http://localhost:5000/metrics | head -5
```

**Check Prometheus can reach the app:**
```bash
docker exec prometheus wget -qO- http://ecommerce-api:5000/metrics | head -5
```

**Check scrape config:**
```bash
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health, lastError: .lastError}'
```

---

## Grafana Issues

### Dashboard shows `No data`

1. Check datasources: **Configuration → Data Sources** → test each one
2. Check the time range (dashboard default: last 1 hour)
3. Check the traffic generator is running: `docker logs traffic-generator --tail=10`
4. Manually send a request: `curl http://localhost:5000/api/simulate/load`

### Dashboard doesn't appear in the menu

Grafana scans the provisioning directory every 30 seconds. Wait up to 30 seconds, then reload the Grafana page. If still missing:

```bash
docker compose restart grafana
```

### Can't log in to Grafana

Default credentials: `admin` / `admin123`

To reset the admin password:
```bash
docker exec grafana grafana-cli admin reset-admin-password newpassword123
```

---

## General Docker Issues

### Port already in use

```bash
# Find what's using a port (e.g., 9200)
lsof -i :9200

# Or
ss -tlnp | grep 9200
```

Stop the conflicting process or change the host port in `docker-compose.yml`.

### Out of disk space

```bash
# Check Docker disk usage
docker system df

# Remove unused images and stopped containers
docker system prune

# Remove all volumes (WARNING: deletes all data)
docker compose down -v
docker system prune -a --volumes
```

### Services restart in a loop

```bash
# Check exit code and reason
docker inspect <container-name> | jq '.[0].State'
```

An exit code of `137` means the container was OOM-killed. Increase Docker's memory limit in Docker Desktop settings or add swap on Linux.

---

## Complete Reset

If you want to start completely fresh:

```bash
# Stop and remove everything
docker compose down -v

# Remove built images
docker rmi grafana-kibana-loki-ecommerce-api grafana-kibana-loki-traffic-generator 2>/dev/null

# (Linux) Check vm.max_map_count again
sysctl vm.max_map_count  # should be 262144

# Start fresh
docker compose up -d --build
```
