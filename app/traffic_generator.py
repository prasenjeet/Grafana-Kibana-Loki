"""
Continuous traffic generator – simulates realistic e-commerce API usage.
Runs as a sidecar container to keep dashboards populated with live data.
"""

import random
import time

import requests

BASE_URL = "http://ecommerce-api:5000"
PRODUCT_IDS = ["p001", "p002", "p003", "p004", "p005", "p006", "p007", "p008"]
USER_IDS = [f"user_{i:04d}" for i in range(1, 51)]


def weighted_choice(choices):
    population, weights = zip(*choices)
    return random.choices(population, weights=weights, k=1)[0]


def run():
    print("Traffic generator starting…", flush=True)
    time.sleep(15)  # Wait for app to be ready

    session = requests.Session()

    while True:
        action = weighted_choice([
            ("list_products", 30),
            ("get_product", 25),
            ("create_order", 20),
            ("user_activity", 10),
            ("simulate_load", 10),
            ("simulate_error", 5),
        ])

        try:
            if action == "list_products":
                category = random.choice([None, "electronics", "accessories", "audio", "office"])
                params = {"category": category} if category else {}
                session.get(f"{BASE_URL}/api/products", params=params, timeout=5)

            elif action == "get_product":
                pid = random.choice(PRODUCT_IDS)
                session.get(f"{BASE_URL}/api/products/{pid}", timeout=5)

            elif action == "create_order":
                session.post(
                    f"{BASE_URL}/api/orders",
                    json={
                        "product_id": random.choice(PRODUCT_IDS),
                        "quantity": random.randint(1, 3),
                        "user_id": random.choice(USER_IDS),
                    },
                    timeout=10,
                )

            elif action == "user_activity":
                uid = random.choice(USER_IDS)
                act = random.choice(["login", "logout", "view"])
                session.post(f"{BASE_URL}/api/users/{uid}/activity", json={"action": act}, timeout=5)

            elif action == "simulate_load":
                session.get(f"{BASE_URL}/api/simulate/load", timeout=10)

            elif action == "simulate_error":
                session.get(f"{BASE_URL}/api/simulate/error", timeout=5)

        except requests.RequestException as exc:
            print(f"[traffic-gen] request failed: {exc}", flush=True)

        time.sleep(random.uniform(0.3, 1.5))


if __name__ == "__main__":
    run()
