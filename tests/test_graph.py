from agents.graph import build_investigation_graph
from backend.schemas import RCAReport


class FakeTools:
    async def call(self, tool_name: str, arguments: dict) -> dict:
        incident_id = arguments["incident_id"]
        return {
            "tool": tool_name,
            "evidence": [
                {
                    "evidence_id": f"{tool_name}:{incident_id}",
                    "source_type": "log" if tool_name == "search_logs" else "runbook",
                    "summary": f"Evidence returned by {tool_name}",
                    "timestamp": None,
                    "source_ref": f"test/{tool_name}",
                }
            ],
        }


class FakeLLM:
    async def generate(self, incident: dict, evidence: list[dict]) -> RCAReport:
        return RCAReport(
            issue_summary="Test incident",
            affected_service=incident["service_name"],
            probable_root_cause="Evidence-backed test cause",
            root_cause_category="test_category",
            confidence_score=0.8,
            evidence_ids=[evidence[0]["evidence_id"]],
            suggested_fix="Review the proposed fix.",
            rollback_recommendation="No rollback without approval.",
            prevention_action="Add a regression test.",
            human_review_required=True,
        )


async def test_graph_collects_evidence_and_validates_safety():
    graph = build_investigation_graph(FakeTools(), FakeLLM())
    result = await graph.ainvoke(
        {
            "incident": {
                "id": "INC-TEST",
                "title": "Kafka consumer lag",
                "service_name": "notification-service",
                "alert_summary": "Kafka consumer lag increased",
                "metrics": {},
            },
            "trace": [],
        }
    )
    assert len(result["evidence"]) == 6
    assert result["report"]["human_review_required"] is True
    assert result["trace"][-1]["step"] == "safety_validation"

