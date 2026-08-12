from __future__ import annotations

import json
import time

from kafka import KafkaProducer

from backend.config import get_settings
from simulator.generator import build_dataset


def publish_alerts() -> int:
    settings = get_settings()
    producer = KafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        value_serializer=lambda value: json.dumps(value, default=str).encode(),
        retries=5,
    )
    count = 0
    for incident in build_dataset()["incidents"]:
        producer.send("service-alerts", incident)
        count += 1
    producer.flush(timeout=30)
    producer.close()
    return count


if __name__ == "__main__":
    for attempt in range(20):
        try:
            print({"published": publish_alerts()})
            break
        except Exception as exc:
            if attempt == 19:
                raise
            print(f"Kafka not ready ({exc}); retrying")
            time.sleep(3)

