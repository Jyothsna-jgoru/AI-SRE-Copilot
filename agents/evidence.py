from __future__ import annotations

from backend.schemas import RCAReport


def flatten_evidence(tool_results: dict[str, dict]) -> list[dict]:
    seen: set[str] = set()
    evidence: list[dict] = []
    for result in tool_results.values():
        for item in result.get("evidence", []):
            evidence_id = item.get("evidence_id")
            if evidence_id and evidence_id not in seen:
                seen.add(evidence_id)
                evidence.append(item)
    return evidence


def validate_evidence_citations(report: RCAReport, evidence: list[dict]) -> None:
    available = {item["evidence_id"] for item in evidence}
    cited = set(report.evidence_ids)
    missing = cited - available
    if missing:
        raise ValueError(f"RCA cites evidence that was not retrieved: {sorted(missing)}")
    if not cited:
        raise ValueError("RCA must cite at least one evidence item")
    if not report.human_review_required:
        raise ValueError("Every recommendation must require human review")


def contains_unsafe_execution_claim(report: RCAReport) -> bool:
    text = " ".join(
        [
            report.suggested_fix,
            report.rollback_recommendation,
            report.probable_root_cause,
        ]
    ).lower()
    forbidden = [
        "i executed",
        "we executed",
        "rollback completed",
        "deployment was rolled back",
        "command executed",
    ]
    return any(phrase in text for phrase in forbidden)

