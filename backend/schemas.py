from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class IncidentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    scenario: str
    severity: str
    status: str
    alert_time: datetime
    alert_summary: str
    metrics: dict
    service_name: str


class EvidenceItem(BaseModel):
    evidence_id: str
    source_type: Literal["log", "kafka", "deployment", "runbook", "historical_rca", "health"]
    summary: str
    timestamp: datetime | None = None
    source_ref: str


class RCAReport(BaseModel):
    issue_summary: str
    affected_service: str
    probable_root_cause: str
    root_cause_category: str
    confidence_score: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(min_length=1)
    suggested_fix: str
    rollback_recommendation: str
    prevention_action: str
    human_review_required: bool = True


class DiagnosisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    incident_id: str
    status: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    report: dict | None
    trace: list[dict]
    review_status: str
    error: str | None


class ReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str = ""


class EvaluationSummary(BaseModel):
    total_cases: int
    completed_diagnoses: int
    root_cause_accuracy: float
    evidence_coverage: float
    structured_output_validity: float
    unsafe_action_count: int
    average_latency_seconds: float

