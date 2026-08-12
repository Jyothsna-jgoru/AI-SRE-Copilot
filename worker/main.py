from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from agents.graph import build_investigation_graph
from agents.llm import OllamaRCAClient
from agents.tools import MCPInvestigationClient
from backend.db import SessionLocal, init_database
from backend.models import Diagnosis, Incident, Service, ToolCall

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("ai-sre-worker")


def _claim_job() -> tuple[int, dict] | None:
    with SessionLocal() as db:
        diagnosis = db.scalar(
            select(Diagnosis)
            .where(Diagnosis.status == "queued")
            .order_by(Diagnosis.created_at)
            .with_for_update(skip_locked=True)
        )
        if diagnosis is None:
            return None
        row = db.execute(
            select(Incident, Service)
            .join(Service, Incident.service_id == Service.id)
            .where(Incident.id == diagnosis.incident_id)
        ).one()
        incident, service = row[0], row[1]
        diagnosis.status = "running"
        diagnosis.started_at = datetime.now(UTC)
        diagnosis.trace = [
            {
                "timestamp": diagnosis.started_at.isoformat(),
                "step": "queue",
                "status": "started",
                "detail": "Diagnosis worker claimed the request.",
            }
        ]
        db.commit()
        return diagnosis.id, {
            "id": incident.id,
            "title": incident.title,
            "service_name": service.name,
            "alert_summary": incident.alert_summary,
            "metrics": incident.metrics,
        }


async def _process(diagnosis_id: int, incident: dict) -> None:
    graph = build_investigation_graph(MCPInvestigationClient(), OllamaRCAClient())
    try:
        result = await graph.ainvoke({"incident": incident, "trace": []})
        completed_at = datetime.now(UTC)
        with SessionLocal() as db:
            diagnosis = db.get(Diagnosis, diagnosis_id)
            if diagnosis is None:
                return
            diagnosis.status = "awaiting_review"
            diagnosis.completed_at = completed_at
            diagnosis.report = result["report"]
            diagnosis.root_cause = result["report"]["probable_root_cause"]
            diagnosis.root_cause_category = result["report"]["root_cause_category"]
            diagnosis.confidence = result["report"]["confidence_score"]
            diagnosis.trace = [*diagnosis.trace, *result["trace"]]
            for tool_name, output in result["tool_results"].items():
                db.add(
                    ToolCall(
                        diagnosis_id=diagnosis.id,
                        tool_name=tool_name,
                        input_json={"incident_id": incident["id"]},
                        output_json=output,
                        duration_ms=0,
                        status="completed",
                    )
                )
            db.commit()
        logger.info("Diagnosis %s awaits human review", diagnosis_id)
    except Exception as exc:
        logger.exception("Diagnosis %s failed", diagnosis_id)
        with SessionLocal() as db:
            diagnosis = db.get(Diagnosis, diagnosis_id)
            if diagnosis:
                diagnosis.status = "failed"
                diagnosis.completed_at = datetime.now(UTC)
                diagnosis.error = str(exc)
                diagnosis.trace = [
                    *diagnosis.trace,
                    {
                        "timestamp": diagnosis.completed_at.isoformat(),
                        "step": "failure",
                        "status": "failed",
                        "detail": str(exc),
                    },
                ]
                db.commit()


async def run_worker() -> None:
    init_database()
    logger.info("Worker started")
    while True:
        job = await asyncio.to_thread(_claim_job)
        if job is None:
            await asyncio.sleep(2)
            continue
        await _process(*job)


if __name__ == "__main__":
    asyncio.run(run_worker())
