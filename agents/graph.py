from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from agents.evidence import (
    contains_unsafe_execution_claim,
    flatten_evidence,
    validate_evidence_citations,
)
from agents.llm import RCAClient


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


class InvestigationState(TypedDict, total=False):
    incident: dict
    plan: list[str]
    tool_results: dict[str, dict]
    evidence: list[dict]
    report: dict
    trace: list[dict]


def _event(step: str, status: str, detail: str) -> dict:
    return {"timestamp": timestamp(), "step": step, "status": status, "detail": detail}


def build_investigation_graph(tool_client, llm_client: RCAClient):
    async def triage(state: InvestigationState) -> dict:
        incident = state["incident"]
        plan = ["search_logs", "get_service_health", "check_deployment"]
        if "kafka" in incident["alert_summary"].lower() or "consumer" in incident["title"].lower():
            plan.append("get_kafka_status")
        plan.extend(["retrieve_runbook", "find_similar_incidents"])
        return {
            "plan": plan,
            "trace": state.get("trace", [])
            + [_event("triage", "completed", f"Created a {len(plan)}-tool evidence plan")],
        }

    async def investigate(state: InvestigationState) -> dict:
        incident_id = state["incident"]["id"]

        async def invoke(tool_name: str) -> tuple[str, dict]:
            arguments = {"incident_id": incident_id}
            if tool_name == "retrieve_runbook":
                arguments["query"] = state["incident"]["alert_summary"]
            return tool_name, await tool_client.call(tool_name, arguments)

        pairs = await asyncio.gather(*(invoke(name) for name in state["plan"]))
        results = dict(pairs)
        evidence = flatten_evidence(results)
        return {
            "tool_results": results,
            "evidence": evidence,
            "trace": state["trace"]
            + [_event("investigation", "completed", f"Retrieved {len(evidence)} evidence items")],
        }

    async def analyze(state: InvestigationState) -> dict:
        report = await llm_client.generate(state["incident"], state["evidence"])
        return {
            "report": report.model_dump(),
            "trace": state["trace"]
            + [_event("analysis", "completed", "Local Ollama model produced schema-valid RCA")],
        }

    async def validate(state: InvestigationState) -> dict:
        from backend.schemas import RCAReport

        report = RCAReport.model_validate(state["report"])
        validate_evidence_citations(report, state["evidence"])
        if contains_unsafe_execution_claim(report):
            raise ValueError("Unsafe execution claim rejected by policy validator")
        return {
            "trace": state["trace"]
            + [_event("safety_validation", "completed", "Evidence and no-action policies passed")]
        }

    graph = StateGraph(InvestigationState)
    graph.add_node("triage", triage)
    graph.add_node("investigate", investigate)
    graph.add_node("analyze", analyze)
    graph.add_node("validate", validate)
    graph.add_edge(START, "triage")
    graph.add_edge("triage", "investigate")
    graph.add_edge("investigate", "analyze")
    graph.add_edge("analyze", "validate")
    graph.add_edge("validate", END)
    return graph.compile()
