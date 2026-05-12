"""
Sample e-commerce API that emits Prometheus metrics and structured JSON logs,
demonstrating the full Grafana + Loki + Prometheus / Kibana + Elasticsearch stack.
"""

import json
import logging
import random
import time
import uuid
from datetime import datetime

from flask import Flask, jsonify, request
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST

# ---------------------------------------------------------------------------
# Structured JSON logger (picked up by Promtail → Loki AND Filebeat → Elasticsearch)
# ---------------------------------------------------------------------------

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": "ecommerce-api",
            "version": "1.0.0",
        }
        if hasattr(record, "extra"):
            log_entry.update(record.extra)
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    return logger


log = get_logger("ecommerce-api")

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)
ACTIVE_USERS = Gauge("active_users_total", "Number of currently active users")
ORDER_COUNTER = Counter(
    "orders_total",
    "Total orders placed",
    ["status", "category"],
)
INVENTORY_GAUGE = Gauge("inventory_items_total", "Current inventory count", ["product"])
ERROR_COUNTER = Counter(
    "application_errors_total",
    "Total application errors",
    ["error_type"],
)
PAYMENT_HISTOGRAM = Histogram(
    "payment_processing_duration_seconds",
    "Payment processing duration",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)

PRODUCTS = [
    {"id": "p001", "name": "Laptop Pro", "price": 1299.99, "category": "electronics", "stock": 42},
    {"id": "p002", "name": "Wireless Mouse", "price": 29.99, "category": "accessories", "stock": 150},
    {"id": "p003", "name": "Mechanical Keyboard", "price": 89.99, "category": "accessories", "stock": 75},
    {"id": "p004", "name": "4K Monitor", "price": 449.99, "category": "electronics", "stock": 28},
    {"id": "p005", "name": "USB-C Hub", "price": 39.99, "category": "accessories", "stock": 200},
    {"id": "p006", "name": "Noise Cancelling Headphones", "price": 249.99, "category": "audio", "stock": 60},
    {"id": "p007", "name": "Webcam HD", "price": 79.99, "category": "electronics", "stock": 90},
    {"id": "p008", "name": "Desk Lamp LED", "price": 34.99, "category": "office", "stock": 120},
]

# Seed inventory gauges
for p in PRODUCTS:
    INVENTORY_GAUGE.labels(product=p["name"]).set(p["stock"])


# ---------------------------------------------------------------------------
# Middleware – latency + request count
# ---------------------------------------------------------------------------

@app.before_request
def start_timer():
    request._start_time = time.time()


@app.after_request
def record_metrics(response):
    latency = time.time() - getattr(request, "_start_time", time.time())
    endpoint = request.endpoint or "unknown"
    REQUEST_LATENCY.labels(method=request.method, endpoint=endpoint).observe(latency)
    REQUEST_COUNT.labels(
        method=request.method, endpoint=endpoint, status_code=response.status_code
    ).inc()
    log.info(
        "HTTP request",
        extra={
            "extra": {
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration_ms": round(latency * 1000, 2),
                "request_id": str(uuid.uuid4()),
                "user_agent": request.headers.get("User-Agent", ""),
            }
        },
    )
    return response


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/health")
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()})


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


@app.route("/api/products")
def list_products():
    category = request.args.get("category")
    products = PRODUCTS if not category else [p for p in PRODUCTS if p["category"] == category]
    log.info("Products listed", extra={"extra": {"count": len(products), "category": category}})
    return jsonify({"products": products, "total": len(products)})


@app.route("/api/products/<product_id>")
def get_product(product_id):
    product = next((p for p in PRODUCTS if p["id"] == product_id), None)
    if not product:
        ERROR_COUNTER.labels(error_type="product_not_found").inc()
        log.warning("Product not found", extra={"extra": {"product_id": product_id}})
        return jsonify({"error": "Product not found"}), 404
    return jsonify(product)


@app.route("/api/orders", methods=["POST"])
def create_order():
    data = request.get_json(silent=True) or {}
    product_id = data.get("product_id")
    quantity = data.get("quantity", 1)
    user_id = data.get("user_id", f"user_{random.randint(1000, 9999)}")

    product = next((p for p in PRODUCTS if p["id"] == product_id), None)
    if not product:
        ERROR_COUNTER.labels(error_type="invalid_product").inc()
        log.error("Order failed – invalid product", extra={"extra": {"product_id": product_id, "user_id": user_id}})
        return jsonify({"error": "Invalid product"}), 400

    if product["stock"] < quantity:
        ORDER_COUNTER.labels(status="rejected", category=product["category"]).inc()
        log.warning(
            "Order rejected – insufficient stock",
            extra={"extra": {"product_id": product_id, "requested": quantity, "available": product["stock"]}},
        )
        return jsonify({"error": "Insufficient stock"}), 409

    # Simulate payment processing
    payment_start = time.time()
    time.sleep(random.uniform(0.05, 0.3))
    payment_duration = time.time() - payment_start
    PAYMENT_HISTOGRAM.observe(payment_duration)

    product["stock"] -= quantity
    INVENTORY_GAUGE.labels(product=product["name"]).set(product["stock"])

    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"
    total = round(product["price"] * quantity, 2)
    ORDER_COUNTER.labels(status="completed", category=product["category"]).inc()

    log.info(
        "Order created",
        extra={
            "extra": {
                "order_id": order_id,
                "user_id": user_id,
                "product_id": product_id,
                "product_name": product["name"],
                "quantity": quantity,
                "total": total,
                "payment_duration_ms": round(payment_duration * 1000, 2),
            }
        },
    )
    return jsonify({"order_id": order_id, "status": "confirmed", "total": total}), 201


@app.route("/api/users/<user_id>/activity", methods=["POST"])
def user_activity(user_id):
    action = (request.get_json(silent=True) or {}).get("action", "view")
    delta = 1 if action == "login" else (-1 if action == "logout" else 0)
    ACTIVE_USERS.inc(delta)
    log.info("User activity", extra={"extra": {"user_id": user_id, "action": action}})
    return jsonify({"user_id": user_id, "action": action, "recorded": True})


@app.route("/api/simulate/load")
def simulate_load():
    """Drive random traffic for demo purposes."""
    operations = random.randint(5, 15)
    results = []
    for _ in range(operations):
        product = random.choice(PRODUCTS)
        results.append({"product": product["id"], "viewed": True})
        ORDER_COUNTER.labels(status="viewed", category=product["category"]).inc()
    log.info("Load simulation run", extra={"extra": {"operations": operations}})
    return jsonify({"simulated_operations": operations, "results": results})


@app.route("/api/simulate/error")
def simulate_error():
    """Trigger a random error for demo purposes."""
    error_types = ["database_timeout", "cache_miss", "validation_error", "external_api_failure"]
    error_type = random.choice(error_types)
    ERROR_COUNTER.labels(error_type=error_type).inc()
    log.error("Simulated error occurred", extra={"extra": {"error_type": error_type, "simulated": True}})
    return jsonify({"error": error_type, "message": f"Simulated {error_type}"}), 500


if __name__ == "__main__":
    log.info("Starting ecommerce-api", extra={"extra": {"port": 5000}})
    app.run(host="0.0.0.0", port=5000, debug=False)
