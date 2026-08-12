from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone


SERVICES = [
    {
        "name": "api-gateway",
        "owner": "platform",
        "description": "Public request routing, authentication, and rate limiting.",
        "dependencies": ["order-service", "payment-service"],
    },
    {
        "name": "order-service",
        "owner": "commerce",
        "description": "Order creation, lifecycle, and orchestration.",
        "dependencies": ["inventory-service", "payment-service"],
    },
    {
        "name": "payment-service",
        "owner": "payments",
        "description": "Payment authorization and transaction persistence.",
        "dependencies": ["postgres-payments", "notification-service"],
    },
    {
        "name": "inventory-service",
        "owner": "supply",
        "description": "Inventory availability and reservation.",
        "dependencies": ["postgres-inventory"],
    },
    {
        "name": "notification-service",
        "owner": "engagement",
        "description": "Consumes Kafka events and sends customer notifications.",
        "dependencies": ["kafka", "email-provider"],
    },
]


SCENARIOS = {
    "api_timeout": {
        "root_cause_category": "downstream_timeout_budget_exhausted",
        "service": "inventory-service",
        "title": "Checkout API timeout",
        "severity": "SEV-2",
        "cause": "A slow inventory dependency exhausted the upstream request timeout budget.",
        "symptom": "p95 latency increased from 240 ms to 8.4 s and checkout requests timed out",
        "error": "upstream inventory reservation exceeded 8000ms deadline",
        "fix": "Reduce traffic pressure, restore inventory latency, then tune the timeout budget.",
        "rollback": "Rollback only if the latency began after the latest inventory release.",
    },
    "kafka_consumer_lag": {
        "root_cause_category": "poison_message_deserialization",
        "service": "notification-service",
        "title": "Notification Kafka consumer lag",
        "severity": "SEV-2",
        "cause": "Poison messages repeatedly failed and prevented the notification consumer from advancing.",
        "symptom": "consumer lag grew above 18,000 messages while processing throughput collapsed",
        "error": "deserialization failure; offset not committed; retry budget exhausted",
        "fix": "Quarantine the poison message, repair the schema handler, and restart the consumer.",
        "rollback": "Rollback the consumer only when the incompatible schema arrived with its release.",
    },
    "deployment_regression": {
        "root_cause_category": "invalid_provider_configuration",
        "service": "payment-service",
        "title": "Payment error-rate regression after deployment",
        "severity": "SEV-1",
        "cause": "Release v2.4 introduced an invalid payment provider configuration key.",
        "symptom": "HTTP 500 rate increased from 0.4% to 18% immediately after deployment",
        "error": "provider configuration missing required merchant_account_id",
        "fix": "Restore the previous configuration and verify payment authorization health.",
        "rollback": "Recommend rollback to the previous healthy release; human approval is mandatory.",
    },
    "database_exhaustion": {
        "root_cause_category": "transaction_connection_leak",
        "service": "order-service",
        "title": "Order database connection exhaustion",
        "severity": "SEV-1",
        "cause": "A leaked transaction path exhausted the order-service database connection pool.",
        "symptom": "available database connections reached zero and order latency spiked",
        "error": "QueuePool limit reached; connection timed out after 30 seconds",
        "fix": "Stop the leaking path, shed load, and restore pool capacity before tuning limits.",
        "rollback": "Rollback if the connection leak correlates with the most recent release.",
    },
    "authentication_failure": {
        "root_cause_category": "expired_signing_key_configuration",
        "service": "api-gateway",
        "title": "Authentication API failure",
        "severity": "SEV-2",
        "cause": "An expired signing-key configuration caused valid access tokens to be rejected.",
        "symptom": "valid users received HTTP 401 responses across protected endpoints",
        "error": "JWT signature verification failed: active key id not found",
        "fix": "Restore the active signing key, refresh configuration, and validate token rotation.",
        "rollback": "No application rollback is needed unless the bad key reference shipped with a release.",
    },
}


def _knowledge_documents() -> list[dict]:
    documents: list[dict] = []
    for scenario, definition in SCENARIOS.items():
        service = definition["service"]
        documents.extend(
            [
                {
                    "id": f"runbook:{scenario}",
                    "document_type": "runbook",
                    "service_name": service,
                    "scenario": scenario,
                    "title": f"Runbook: {definition['title']}",
                    "content": (
                        f"Confirm the alert window for {service}. Correlate error logs, dependency health, "
                        f"consumer state, and the latest deployment. Expected remediation pattern: "
                        f"{definition['fix']} {definition['rollback']} Never execute a rollback automatically."
                    ),
                },
                {
                    "id": f"service:{scenario}",
                    "document_type": "service_doc",
                    "service_name": service,
                    "scenario": scenario,
                    "title": f"{service} dependencies and signals",
                    "content": (
                        f"Primary failure signature for {scenario}: {definition['symptom']}. "
                        f"The owning team is responsible for verifying logs and downstream health."
                    ),
                },
                {
                    "id": f"historical:{scenario}",
                    "document_type": "historical_rca",
                    "service_name": service,
                    "scenario": scenario,
                    "title": f"Historical RCA: {definition['title']}",
                    "content": (
                        f"A previous incident presented as {definition['symptom']}. Evidence showed: "
                        f"{definition['error']}. Confirmed cause: {definition['cause']}"
                    ),
                },
            ]
        )
    return documents


def build_dataset(incident_count: int = 50, seed: int = 42) -> dict:
    """Build deterministic data. Ground truth is returned separately from observable incidents."""
    if incident_count < 5:
        raise ValueError("At least five incidents are required to cover every scenario")
    rng = random.Random(seed)
    base_time = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    scenario_names = list(SCENARIOS)
    incidents: list[dict] = []
    logs: list[dict] = []
    kafka_events: list[dict] = []
    deployments: list[dict] = []
    evaluation_cases: list[dict] = []

    for index in range(incident_count):
        scenario = scenario_names[index % len(scenario_names)]
        definition = SCENARIOS[scenario]
        incident_id = f"INC-{index + 1:03d}"
        alert_time = base_time + timedelta(hours=index * 6)
        error_rate = round(0.4 + (index % 4) * 0.2, 1)
        latency_ms = 240 + (index % 6) * 15
        incidents.append(
            {
                "id": incident_id,
                "title": definition["title"],
                "service_name": definition["service"],
                "scenario": scenario,
                "severity": definition["severity"],
                "status": "open",
                "alert_time": alert_time,
                "alert_summary": f"{definition['service']}: {definition['symptom']}",
                "metrics": {
                    "error_rate_before": error_rate,
                    "error_rate_current": 18.0 if definition["severity"] == "SEV-1" else 7.6,
                    "p95_latency_ms_before": latency_ms,
                    "p95_latency_ms_current": 8400 if scenario == "api_timeout" else 1280,
                    "availability": 91.2 if definition["severity"] == "SEV-1" else 97.4,
                },
            }
        )
        trace_id = f"trace-{index + 1:03d}"
        for log_index in range(22):
            is_signal = log_index >= 18
            logs.append(
                {
                    "incident_id": incident_id,
                    "service_name": definition["service"],
                    "timestamp": alert_time - timedelta(minutes=22 - log_index),
                    "level": "ERROR" if is_signal else rng.choice(["INFO", "INFO", "WARN"]),
                    "message": definition["error"] if is_signal else "request completed within normal operating range",
                    "trace_id": trace_id if is_signal else f"trace-{index + 1:03d}-{log_index:02d}",
                }
            )
        for event_index in range(6):
            lag = (event_index + 1) * 3000 if scenario == "kafka_consumer_lag" else event_index * 3
            kafka_events.append(
                {
                    "incident_id": incident_id,
                    "topic": "notification-events" if scenario == "kafka_consumer_lag" else "service-alerts",
                    "partition": event_index % 3,
                    "offset": index * 100 + event_index,
                    "event_type": "consumer_failure" if scenario == "kafka_consumer_lag" else "health_snapshot",
                    "payload": {"service": definition["service"], "scenario": scenario, "sequence": event_index},
                    "consumer_group": f"{definition['service']}-consumer",
                    "lag": lag,
                    "timestamp": alert_time - timedelta(minutes=6 - event_index),
                }
            )
        version_major = 2 + index // 20
        version = f"v{version_major}.{index % 10}.{index % 3}"
        if scenario == "deployment_regression" and index == 2:
            version = "v2.4.1"
        deployments.append(
            {
                "incident_id": incident_id,
                "service_name": definition["service"],
                "version": version,
                "deployed_at": alert_time - timedelta(minutes=20 if scenario == "deployment_regression" else 480),
                "author": "release-bot",
                "change_summary": (
                    "Updated provider configuration loader"
                    if scenario == "deployment_regression"
                    else "Routine dependency and observability updates"
                ),
                "status": "completed",
            }
        )
        evaluation_cases.append(
            {
                "incident_id": incident_id,
                "expected_root_cause_category": definition["root_cause_category"],
                "expected_root_cause": definition["cause"],
                "required_evidence_ids": [f"log:{incident_id}", f"runbook:{scenario}"],
            }
        )

    return {
        "services": SERVICES,
        "incidents": incidents,
        "logs": logs,
        "kafka_events": kafka_events,
        "deployments": deployments,
        "knowledge_documents": _knowledge_documents(),
        "evaluation_cases": evaluation_cases,
    }
