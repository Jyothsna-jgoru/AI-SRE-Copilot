import pytest

from agents.evidence import contains_unsafe_execution_claim, validate_evidence_citations
from backend.schemas import RCAReport


def report(**overrides) -> RCAReport:
    values = {
        "issue_summary": "Payment errors rose after deployment.",
        "affected_service": "payment-service",
        "probable_root_cause": "Configuration regression.",
        "root_cause_category": "invalid_provider_configuration",
        "confidence_score": 0.91,
        "evidence_ids": ["log:1"],
        "suggested_fix": "Restore the previous configuration after review.",
        "rollback_recommendation": "Recommend rollback after approval.",
        "prevention_action": "Validate configuration in CI.",
        "human_review_required": True,
    }
    values.update(overrides)
    return RCAReport(**values)


def test_rejects_unretrieved_citations():
    with pytest.raises(ValueError, match="not retrieved"):
        validate_evidence_citations(report(), [{"evidence_id": "log:2"}])


def test_rejects_disabled_human_review():
    with pytest.raises(ValueError, match="human review"):
        validate_evidence_citations(
            report(human_review_required=False),
            [{"evidence_id": "log:1"}],
        )


def test_flags_execution_claims():
    unsafe = report(rollback_recommendation="Rollback completed successfully.")
    assert contains_unsafe_execution_claim(unsafe)
    assert not contains_unsafe_execution_claim(report())

