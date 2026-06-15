# Application API

The sample **ecommerce-api** is a Flask application that serves as the workload under observation. Every request emits Prometheus metrics and a structured JSON log line.

Base URL: `http://localhost:5000`

---

## Endpoints

### `GET /health`

Returns service health status. Used by Docker healthcheck.

```bash
curl http://localhost:5000/health
```

```json
{
  "status": "healthy",
  "timestamp": "2024-06-15T12:00:00.000000"
}
```

---

### `GET /metrics`

Prometheus metrics in text exposition format. Scraped automatically by Prometheus every 10 seconds.

```bash
curl http://localhost:5000/metrics
```

```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{endpoint="list_products",method="GET",status_code="200"} 142.0
...
```

---

### `GET /api/products`

List all products. Optional `category` filter.

**Query parameters:**

| Parameter | Type | Values |
|---|---|---|
| `category` | string (optional) | `electronics`, `accessories`, `audio`, `office` |

```bash
# All products
curl http://localhost:5000/api/products

# Filtered by category
curl "http://localhost:5000/api/products?category=electronics"
```

```json
{
  "products": [
    {
      "id": "p001",
      "name": "Laptop Pro",
      "price": 1299.99,
      "category": "electronics",
      "stock": 42
    }
  ],
  "total": 1
}
```

---

### `GET /api/products/:id`

Get a single product by ID.

**Path parameters:** `id` — one of `p001` through `p008`

```bash
curl http://localhost:5000/api/products/p001
```

```json
{
  "id": "p001",
  "name": "Laptop Pro",
  "price": 1299.99,
  "category": "electronics",
  "stock": 42
}
```

**404 response:**
```json
{ "error": "Product not found" }
```

---

### `POST /api/orders`

Place an order. Simulates payment processing (50–300 ms sleep), decrements stock, and emits a business event log.

**Request body:**

| Field | Type | Required | Notes |
|---|---|---|---|
| `product_id` | string | yes | `p001`–`p008` |
| `quantity` | integer | no | default `1` |
| `user_id` | string | no | default `user_XXXX` (random) |

```bash
curl -X POST http://localhost:5000/api/orders \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": "p002",
    "quantity": 3,
    "user_id": "user_0042"
  }'
```

**201 — success:**
```json
{
  "order_id": "ORD-A1B2C3D4",
  "status": "confirmed",
  "total": 89.97
}
```

**400 — invalid product:**
```json
{ "error": "Invalid product" }
```

**409 — out of stock:**
```json
{ "error": "Insufficient stock" }
```

---

### `POST /api/users/:user_id/activity`

Record a user activity event. Adjusts the `active_users_total` Prometheus gauge.

**Path parameters:** `user_id` — any string

**Request body:**

| Field | Type | Values |
|---|---|---|
| `action` | string | `login` (+1 gauge), `logout` (-1 gauge), `view` (no change) |

```bash
curl -X POST http://localhost:5000/api/users/user_0001/activity \
  -H "Content-Type: application/json" \
  -d '{"action": "login"}'
```

```json
{
  "user_id": "user_0001",
  "action": "login",
  "recorded": true
}
```

---

### `GET /api/simulate/load`

Triggers 5–15 random product view events in a single call. Useful for generating burst traffic to make graphs more interesting.

```bash
curl http://localhost:5000/api/simulate/load
```

```json
{
  "simulated_operations": 11,
  "results": [
    { "product": "p003", "viewed": true },
    ...
  ]
}
```

---

### `GET /api/simulate/error`

Triggers a random application error (one of `database_timeout`, `cache_miss`, `validation_error`, `external_api_failure`). Returns HTTP 500. Increments `application_errors_total` and writes an ERROR log.

```bash
curl http://localhost:5000/api/simulate/error
```

```json
{
  "error": "database_timeout",
  "message": "Simulated database_timeout"
}
```

---

## Prometheus Metrics Emitted

| Metric | Type | Labels | Description |
|---|---|---|---|
| `http_requests_total` | Counter | `method`, `endpoint`, `status_code` | Every HTTP response |
| `http_request_duration_seconds` | Histogram | `method`, `endpoint` | Request latency (10 buckets, 5ms–5s) |
| `active_users_total` | Gauge | *(none)* | Current logged-in users |
| `orders_total` | Counter | `status`, `category` | Orders by outcome and product category |
| `inventory_items_total` | Gauge | `product` | Current stock level per product |
| `application_errors_total` | Counter | `error_type` | Application-level errors |
| `payment_processing_duration_seconds` | Histogram | *(none)* | Payment simulation latency |

---

## Log Format

Every log line is a single JSON object on stdout:

```json
{
  "timestamp": "2024-06-15T12:00:00.123456Z",
  "level": "INFO",
  "logger": "ecommerce-api",
  "message": "Order created",
  "service": "ecommerce-api",
  "version": "1.0.0",
  "extra": {
    "order_id": "ORD-A1B2C3D4",
    "user_id": "user_0042",
    "product_id": "p002",
    "product_name": "Wireless Mouse",
    "quantity": 3,
    "total": 89.97,
    "payment_duration_ms": 143.2
  }
}
```

### Log Levels Used

| Level | When |
|---|---|
| `INFO` | Every request, order created, user activity, load simulation |
| `WARNING` | Product not found, out-of-stock rejection |
| `ERROR` | Invalid product in order, simulated errors |

---

## Product Catalogue

| ID | Name | Category | Price |
|---|---|---|---|
| p001 | Laptop Pro | electronics | $1,299.99 |
| p002 | Wireless Mouse | accessories | $29.99 |
| p003 | Mechanical Keyboard | accessories | $89.99 |
| p004 | 4K Monitor | electronics | $449.99 |
| p005 | USB-C Hub | accessories | $39.99 |
| p006 | Noise Cancelling Headphones | audio | $249.99 |
| p007 | Webcam HD | electronics | $79.99 |
| p008 | Desk Lamp LED | office | $34.99 |
