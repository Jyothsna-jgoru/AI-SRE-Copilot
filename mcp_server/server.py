from __future__ import annotations

from datetime import timedelta

from mcp.server.fastmcp import FastMCP
from sqlalchemy import desc, select

from backend.config import get_settings
from backend.db import SessionLocal, init_database
from backend.models import Deployment, Incident, KafkaEvent, KnowledgeDocument, LogRecord, Service

settings = get_settings()
mcp = FastMCP(
    "AI SRE Investigation Tools",
    instructions=(
        "Read-only operational evidence tools. Never execute remediation, deployment, shell, "
        "database write, or infrastructure mutation commands."
    ),
    host=settings.mcp_host,
    port=settings.mcp_port,
    json_response=True,
)


def _incident_and_service(db, incident_id: str) -> tuple[Incident, Service]:
    row = db.execute(
        select(Incident, Service)
        .join(Service, Incident.service_id == Service.id)
        .where(Incident.id == incident_id)
    ).one_or_none()
    if row is None:
        raise ValueError(f"Unknown incident: {incident_id}")
    return row[0], row[1]


@mcp.tool(structured_output=True)
def search_logs(incident_id: str, limit: int = 20) -> dict:
    """Return structured error and warning logs for one incident."""
    with SessionLocal() as db:
        incident, service = _incident_and_service(db, incident_id)
        records = db.scalars(
            select(LogRecord)
            .where(LogRecord.incident_id == incident_id, LogRecord.level.in_(["ERROR", "WARN"]))
            .order_by(desc(LogRecord.timestamp))
            .limit(min(limit, 50))
        ).all()
        return {
            "tool": "search_logs",
            "incident_id": incident_id,
            "service": service.name,
            "evidence": [
                {
                    "evidence_id": f"log:{incident_id}:{record.id}",
                    "source_type": "log",
                    "summary": f"{record.level}: {record.message}",
                    "timestamp": record.timestamp.isoformat(),
                    "source_ref": f"logs/{record.id}?trace_id={record.trace_id}",
                }
                for record in records
            ],
            "window_start": (incident.alert_time - timedelta(minutes=30)).isoformat(),
        }


@mcp.tool(structured_output=True)
def get_kafka_status(incident_id: str) -> dict:
    """Return persisted Kafka events and consumer-lag snapshots for one incident."""
    with SessionLocal() as db:
        _incident_and_service(db, incident_id)
        events = db.scalars(
            select(KafkaEvent)
            .where(KafkaEvent.incident_id == incident_id)
            .order_by(desc(KafkaEvent.timestamp))
            .limit(30)
        ).all()
        max_lag = max((event.lag for event in events), default=0)
        return {
            "tool": "get_kafka_status",
            "incident_id": incident_id,
            "max_consumer_lag": max_lag,
            "evidence": [
                {
                    "evidence_id": f"kafka:{incident_id}:{event.id}",
                    "source_type": "kafka",
                    "summary": (
                        f"topic={event.topic} group={event.consumer_group} partition={event.partition} "
                        f"offset={event.offset} lag={event.lag} event={event.event_type}"
                    ),
                    "timestamp": event.timestamp.isoformat(),
                    "source_ref": f"kafka-events/{event.id}",
                }
                for event in events
            ],
        }


@mcp.tool(structured_output=True)
def check_deployment(incident_id: str) -> dict:
    """Return recent deployments for the incident's affected service."""
    with SessionLocal() as db:
        incident, service = _incident_and_service(db, incident_id)
        records = db.scalars(
            select(Deployment)
            .where(
                Deployment.service_id == service.id,
                Deployment.deployed_at <= incident.alert_time,
                Deployment.deployed_at >= incident.alert_time - timedelta(hours=24),
            )
            .order_by(desc(Deployment.deployed_at))
            .limit(5)
        ).all()
        return {
            "tool": "check_deployment",
            "incident_id": incident_id,
            "evidence": [
                {
                    "evidence_id": f"deployment:{incident_id}:{record.id}",
                    "source_type": "deployment",
                    "summary": (
                        f"{service.name} {record.version} deployed by {record.author}: "
                        f"{record.change_summary}"
                    ),
                    "timestamp": record.deployed_at.isoformat(),
                    "source_ref": f"deployments/{record.id}",
                }
                for record in records
            ],
        }


@mcp.tool(structured_output=True)
def retrieve_runbook(incident_id: str, query: str = "") -> dict:
    """Retrieve runbooks and service documents using ChromaDB, with a read-only DB fallback."""
    with SessionLocal() as db:
        incident, service = _incident_and_service(db, incident_id)
        search_text = query or f"{incident.title}. {incident.alert_summary}"
        matches: list[dict] = []
        retrieval_mode = "chromadb-minilm"
        try:
            from rag.store import get_knowledge_store

            matches = get_knowledge_store().query(search_text, service_name=service.name, limit=5)
        except Exception:
            retrieval_mode = "keyword-fallback"
            documents = db.scalars(
                select(KnowledgeDocument)
                .where(KnowledgeDocument.service_name == service.name)
                .limit(5)
            ).all()
            matches = [
                {
                    "id": document.id,
                    "content": document.content,
                    "metadata": {
                        "document_type": document.document_type,
                        "title": document.title,
                        "service_name": document.service_name,
                    },
                    "distance": None,
                }
                for document in documents
            ]
        return {
            "tool": "retrieve_runbook",
            "incident_id": incident_id,
            "retrieval_mode": retrieval_mode,
            "evidence": [
                {
                    "evidence_id": item["id"],
                    "source_type": (
                        "historical_rca"
                        if item["metadata"].get("document_type") == "historical_rca"
                        else "runbook"
                    ),
                    "summary": item["content"],
                    "timestamp": None,
                    "source_ref": f"knowledge/{item['id']}",
                }
                for item in matches
            ],
        }


@mcp.tool(structured_output=True)
def find_similar_incidents(incident_id: str) -> dict:
    """Return historical RCAs with matching service or observable symptoms."""
    with SessionLocal() as db:
        _incident, service = _incident_and_service(db, incident_id)
        documents = db.scalars(
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.document_type == "historical_rca",
                KnowledgeDocument.service_name == service.name,
            )
            .limit(5)
        ).all()
        return {
            "tool": "find_similar_incidents",
            "incident_id": incident_id,
            "evidence": [
                {
                    "evidence_id": document.id,
                    "source_type": "historical_rca",
                    "summary": document.content,
                    "timestamp": None,
                    "source_ref": f"knowledge/{document.id}",
                }
                for document in documents
            ],
        }


@mcp.tool(structured_output=True)
def get_service_health(incident_id: str) -> dict:
    """Return alert-time service health derived from stored metrics."""
    with SessionLocal() as db:
        incident, service = _incident_and_service(db, incident_id)
        metrics = incident.metrics
        return {
            "tool": "get_service_health",
            "incident_id": incident_id,
            "evidence": [
                {
                    "evidence_id": f"health:{incident_id}",
                    "source_type": "health",
                    "summary": (
                        f"{service.name} error_rate={metrics.get('error_rate_current')}%, "
                        f"p95_latency={metrics.get('p95_latency_ms_current')}ms, "
                        f"availability={metrics.get('availability')}%"
                    ),
                    "timestamp": incident.alert_time.isoformat(),
                    "source_ref": f"incidents/{incident_id}/metrics",
                }
            ],
        }


if __name__ == "__main__":
    init_database()
    mcp.run(transport="streamable-http")
