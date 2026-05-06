import requests
import requests
import time
import random

components = [
    "DB_PRIMARY",
    "API_GATEWAY",
    "CACHE_LAYER",
    "MESSAGE_QUEUE",
    "AUTH_SERVICE"
]

errors = {
    "DB_PRIMARY": [
        "connection timeout",
        "replication lag",
        "disk full"
    ],

    "API_GATEWAY": [
        "502 bad gateway",
        "latency spike",
        "service unavailable"
    ],

    "CACHE_LAYER": [
        "cache miss storm",
        "redis disconnected",
        "memory pressure"
    ],

    "MESSAGE_QUEUE": [
        "queue backlog",
        "consumer timeout",
        "message retry flood"
    ],

    "AUTH_SERVICE": [
        "token validation failed",
        "oauth timeout",
        "login spike"
    ]
}

print("Sending sample signals...\n")

while True:

    component = random.choice(components)

    signal = {
        "component_id": component,
        "error": random.choice(errors[component]),
        "timestamp": time.time()
    }

    try:

        response = requests.post(
            "http://127.0.0.1:8000/ingest",
            json=signal
        )

        print(f"Sent: {signal}")
        print(f"Response: {response.json()}")
        print("-" * 50)

    except Exception as e:
        print(f"Error sending signal: {e}")

    time.sleep(1)
