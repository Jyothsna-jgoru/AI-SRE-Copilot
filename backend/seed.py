from __future__ import annotations

import logging

from sqlalchemy import func, select

from backend.db import SessionLocal, init_database
from backend.models import (
    Deployment,
    EvaluationCase,
    Incident,
    KafkaEvent,
    KnowledgeDocument,
    LogRecord,
    Service,
    User,
)
from backend.security import hash_password
from simulator.generator import build_dataset


logger = logging.getLogger(__name__)


def seed_database(index_rag: bool = False) -> dict[str, int | str]:
    init_database()
    dataset = build_dataset()
    with SessionLocal() as db:
        if (db.scalar(select(func.count()).select_from(Incident)) or 0) > 0:
            rag_status = "skipped"
            if index_rag:
                try:
                    from rag.store import get_knowledge_store

                    existing = db.scalars(select(KnowledgeDocument)).all()
                    get_knowledge_store().index(
                        [
                            {
                                "id": document.id,
                                "document_type": document.document_type,
                                "service_name": document.service_name,
                                "scenario": document.scenario,
                                "title": document.title,
                                "content": document.content,
                            }
                            for document in existing
                        ]
                    )
                    rag_status = "indexed"
                except Exception as exc:
                    logger.warning("RAG indexing deferred: %s", exc)
                    rag_status = "deferred"
            return {"status": "already_seeded", "rag": rag_status}

        users = [
            User(email="viewer@local.dev", password_hash=hash_password("viewer123"), role="viewer"),
            User(email="analyst@local.dev", password_hash=hash_password("analyst123"), role="analyst"),
            User(email="commander@local.dev", password_hash=hash_password("commander123"), role="commander"),
        ]
        db.add_all(users)
        services = {item["name"]: Service(**item) for item in dataset["services"]}
        db.add_all(services.values())
        db.flush()

        db.add_all(
            [
                Incident(
                    id=item["id"],
                    title=item["title"],
                    service_id=services[item["service_name"]].id,
                    scenario=item["scenario"],
                    severity=item["severity"],
                    status=item["status"],
                    alert_time=item["alert_time"],
                    alert_summary=item["alert_summary"],
                    metrics=item["metrics"],
                )
                for item in dataset["incidents"]
            ]
        )
        db.add_all(
            [
                LogRecord(
                    incident_id=item["incident_id"],
                    service_id=services[item["service_name"]].id,
                    timestamp=item["timestamp"],
                    level=item["level"],
                    message=item["message"],
                    trace_id=item["trace_id"],
                )
                for item in dataset["logs"]
            ]
        )
        db.add_all([KafkaEvent(**item) for item in dataset["kafka_events"]])
        db.add_all(
            [
                Deployment(
                    incident_id=item["incident_id"],
                    service_id=services[item["service_name"]].id,
                    version=item["version"],
                    deployed_at=item["deployed_at"],
                    author=item["author"],
                    change_summary=item["change_summary"],
                    status=item["status"],
                )
                for item in dataset["deployments"]
            ]
        )
        db.add_all(
            [
                KnowledgeDocument(
                    id=item["id"],
                    document_type=item["document_type"],
                    service_name=item["service_name"],
                    scenario=item["scenario"],
                    title=item["title"],
                    content=item["content"],
                    metadata_json={},
                )
                for item in dataset["knowledge_documents"]
            ]
        )
        db.add_all([EvaluationCase(**item) for item in dataset["evaluation_cases"]])
        db.commit()

    rag_status = "skipped"
    if index_rag:
        try:
            from rag.store import get_knowledge_store

            get_knowledge_store().index(dataset["knowledge_documents"])
            rag_status = "indexed"
        except Exception as exc:
            logger.warning("RAG indexing deferred: %s", exc)
            rag_status = "deferred"
    return {
        "status": "seeded",
        "incidents": len(dataset["incidents"]),
        "logs": len(dataset["logs"]),
        "knowledge_documents": len(dataset["knowledge_documents"]),
        "rag": rag_status,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(seed_database(index_rag=True))
