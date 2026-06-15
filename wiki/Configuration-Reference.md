# Configuration Reference

Every configuration file in the project explained key-by-key.

---

## `docker-compose.yml`

The root orchestration file. All services share the `observability` bridge network (`172.20.0.0/16`).

### Global logging defaults

```yaml
x-logging: &default-logging
  driver: json-file
  options:
    max-size: "10m"   # rotate log file when it exceeds 10 MB
    max-file: "3"     # keep at most 3 rotated files (30 MB total per container)
```

Applied to every service via `logging: *default-logging`.

### Named volumes

```yaml
volumes:
  prometheus_data:      # TSDB blocks for Prometheus
  grafana_data:         # Grafana SQLite DB, plugins, sessions
  loki_data:            # Loki chunks + TSDB index
  elasticsearch_data:   # Elasticsearch shards + translog
```

### `ecommerce-api`

```yaml
environment:
  PYTHONUNBUFFERED: "1"   # Disable Python output buffering – essential so logs
                           # appear immediately in Docker's log stream
labels:
  logging: "promtail"     # Hint used by Promtail Docker SD
  service: "ecommerce-api"
```

### `elasticsearch`

```yaml
environment:
  ES_JAVA_OPTS: "-Xms512m -Xmx512m"   # JVM heap – min and max must match
  xpack.security.enabled: "false"       # No TLS/auth in demo
ulimits:
  memlock:
    soft: -1
    hard: -1           # Disable swap for Elasticsearch (best practice)
  nofile:
    soft: 65536
    hard: 65536        # Enough file handles for many shards
```

---

## `prometheus/prometheus.yml`

### Global defaults

```yaml
global:
  scrape_interval: 15s        # Default pull frequency for all jobs
  evaluation_interval: 15s    # How often alert rules are evaluated
  external_labels:
    environment: "demo"       # Appended to all metrics (useful in multi-cluster setups)
    stack: "grafana-kibana-loki"
```

### Per-job overrides

The `ecommerce-api` job overrides `scrape_interval: 10s` because application metrics change faster than infrastructure metrics.

---

## `loki/loki-config.yml`

### `auth_enabled: false`

Disables multi-tenancy. In production, set to `true` and send `X-Scope-OrgID` headers to isolate tenants.

### Schema v13 (TSDB)

```yaml
schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb          # Recommended index store from Loki 2.8+
      object_store: filesystem
      schema: v13          # Current schema version (don't change existing data)
      index:
        period: 24h        # One TSDB index file per day
```

Changing the schema requires a new config entry with a future `from` date — you cannot modify historical schema entries.

### Retention

```yaml
limits_config:
  retention_period: 168h     # 7 days

compactor:
  retention_enabled: true    # Compactor is responsible for deleting old chunks
```

### Ingestion limits

```yaml
limits_config:
  ingestion_rate_mb: 16          # Max MB/s per tenant
  ingestion_burst_size_mb: 32    # Allowed burst before rate limiting
  max_label_names_per_series: 30 # Prevent accidental label explosion
```

---

## `promtail/promtail-config.yml`

### Docker SD

```yaml
docker_sd_configs:
  - host: unix:///var/run/docker.sock
    refresh_interval: 5s    # How often to re-scan for new/removed containers
    filters:
      - name: name
        values: ["ecommerce-api"]   # Only watch this container
```

### Pipeline stages (in order)

| Stage | Purpose |
|---|---|
| `json` | Parse stdout JSON into fields |
| `labels` | Promote specific fields to Loki labels (indexed) |
| `timestamp` | Set `@timestamp` from the parsed `timestamp` field |
| `output` | Replace the log line with just the `message` field |

### Why `output: source: message`?

Without this stage, Promtail sends the full JSON string as the log line. With it, Grafana's log panel shows the human-readable `message` field, while all the structured data is still accessible via `| json` at query time.

---

## `elasticsearch/elasticsearch.yml`

### `action.destructive_requires_name: true`

Prevents `DELETE *` or `DELETE _all` from wiping every index. Deletion must specify an explicit index name pattern.

### `http.cors.*`

Enables cross-origin REST API access. Useful for browser-based ES tools but should be restricted in production.

```yaml
http.cors.enabled: true
http.cors.allow-origin: "*"   # Restrict to specific origin in production
```

---

## `kibana/kibana.yml`

### Encryption keys

```yaml
xpack.encryptedSavedObjects.encryptionKey: "changeme-32-char-random-string-here"
xpack.reporting.encryptionKey: "changeme-32-char-random-string-here2"
xpack.security.encryptionKey: "changeme-32-char-random-string-here3"
```

These must be random 32+ character strings in production. They are used to encrypt saved objects (dashboards, alerts) in Kibana's `.kibana` index.

### `xpack.fleet.enabled: false`

Fleet is Elastic Agent management. Disabled here because we use Filebeat directly.

---

## `filebeat/filebeat.yml`

### `--strict.perms=false`

Required because the config file is mounted read-only from the host. Filebeat normally refuses to start if the config file has permissive permissions (to prevent tampering), but in Docker the mounted file is owned by root on the host.

### `user: root` in docker-compose.yml

Filebeat needs root access to:
- Read `/var/lib/docker/containers/*/*.log`
- Connect to `/var/run/docker.sock`

### Autodiscover

```yaml
filebeat.autodiscover:
  providers:
    - type: docker
      hints.enabled: true
      templates:
        - condition:
            contains:
              docker.container.image: "ecommerce"
          config:
            - type: container
              paths:
                - "/var/lib/docker/containers/${data.docker.container.id}/*.log"
```

This template automatically activates whenever a container whose image name contains `"ecommerce"` starts, without needing to restart Filebeat.

---

## `grafana/provisioning/datasources/datasources.yml`

### `uid` field

The `uid` field gives each datasource a stable identifier used in dashboard JSON. If you delete and recreate a datasource, keeping the same `uid` means all dashboards continue to work.

```yaml
- name: Prometheus
  uid: prometheus    # Referenced in panel targets as {"uid": "prometheus"}
```

### `isDefault: true`

Only Prometheus is marked as the default. When creating new panels without choosing a datasource, Prometheus is pre-selected.

---

## `grafana/provisioning/dashboards/dashboard.yml`

### `updateIntervalSeconds: 30`

Grafana rescans the provisioning directory every 30 seconds. Editing the JSON file and waiting 30 seconds is enough to update the dashboard without restarting Grafana.

### `allowUiUpdates: true`

Allows editing provisioned dashboards in the Grafana UI. Without this, any UI edit would show "This dashboard cannot be modified". Changes made in the UI are not written back to the JSON file — export manually if you want to persist UI changes.

---

## Environment Variables Summary

| Variable | Service | Value | Effect |
|---|---|---|---|
| `GF_SECURITY_ADMIN_USER` | Grafana | `admin` | Admin username |
| `GF_SECURITY_ADMIN_PASSWORD` | Grafana | `admin123` | Admin password |
| `GF_USERS_ALLOW_SIGN_UP` | Grafana | `false` | Disable self-registration |
| `GF_INSTALL_PLUGINS` | Grafana | `grafana-clock-panel,...` | Auto-install plugins |
| `ES_JAVA_OPTS` | Elasticsearch | `-Xms512m -Xmx512m` | JVM heap size |
| `ELASTICSEARCH_HOSTS` | Kibana | `http://elasticsearch:9200` | ES backend |
| `XPACK_SECURITY_ENABLED` | Kibana | `false` | No auth |
| `XPACK_FLEET_ENABLED` | Kibana | `false` | Disable Fleet |
| `PYTHONUNBUFFERED` | App | `1` | Immediate log output |
| `ELASTICSEARCH_URL` | es-setup | `http://elasticsearch:9200` | Setup target |
| `KIBANA_URL` | es-setup | `http://kibana:5601` | Kibana target |
