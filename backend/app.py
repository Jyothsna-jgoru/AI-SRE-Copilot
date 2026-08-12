from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agents.evidence import contains_unsafe_execution_claim
from backend.config import get_settings
from backend.db import get_db, init_database
from backend.models import Diagnosis, EvaluationCase, Incident, Service, User
from backend.schemas import (
    DiagnosisResponse,
    EvaluationSummary,
    IncidentSummary,
    LoginRequest,
    RCAReport,
    ReviewRequest,
    TokenResponse,
)
from backend.security import create_token, current_user, require_roles, verify_password
from backend.seed import seed_database

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_database()
    if settings.auto_seed:
        seed_database(index_rag=False)
    yield


app = FastAPI(
    title="AI SRE Copilot API",
    version="0.1.0",
    description="Evidence-grounded local incident diagnosis. Recommendations are never executed.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


def _incident_summary(incident: Incident, service: Service) -> IncidentSummary:
    return IncidentSummary(
        id=incident.id,
        title=incident.title,
        scenario=incident.scenario,
        severity=incident.severity,
        status=incident.status,
        alert_time=incident.alert_time,
        alert_summary=incident.alert_summary,
        metrics=incident.metrics,
        service_name=service.name,
    )


@app.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.email, User.active.is_(True)))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(access_token=create_token(user), role=user.role)


@app.get("/incidents", response_model=list[IncidentSummary])
def list_incidents(
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[IncidentSummary]:
    rows = db.execute(
        select(Incident, Service)
        .join(Service, Incident.service_id == Service.id)
        .order_by(Incident.alert_time.desc())
    ).all()
    return [_incident_summary(row[0], row[1]) for row in rows]


@app.get("/incidents/{incident_id}", response_model=IncidentSummary)
def get_incident(
    incident_id: str,
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> IncidentSummary:
    row = db.execute(
        select(Incident, Service)
        .join(Service, Incident.service_id == Service.id)
        .where(Incident.id == incident_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return _incident_summary(row[0], row[1])


@app.post("/incidents/{incident_id}/diagnose", response_model=DiagnosisResponse, status_code=202)
def request_diagnosis(
    incident_id: str,
    user: User = Depends(require_roles("analyst", "commander")),
    db: Session = Depends(get_db),
) -> Diagnosis:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    active = db.scalar(
        select(Diagnosis)
        .where(
            Diagnosis.incident_id == incident_id,
            Diagnosis.status.in_(["queued", "running", "awaiting_review"]),
        )
        .order_by(Diagnosis.id.desc())
    )
    if active:
        return active
    diagnosis = Diagnosis(incident_id=incident_id, requested_by=user.id, status="queued", trace=[])
    db.add(diagnosis)
    db.commit()
    db.refresh(diagnosis)
    return diagnosis


@app.get("/incidents/{incident_id}/diagnosis", response_model=DiagnosisResponse)
def latest_diagnosis(
    incident_id: str,
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Diagnosis:
    diagnosis = db.scalar(
        select(Diagnosis)
        .where(Diagnosis.incident_id == incident_id)
        .order_by(Diagnosis.id.desc())
    )
    if diagnosis is None:
        raise HTTPException(status_code=404, detail="No diagnosis requested")
    return diagnosis


@app.get("/incidents/{incident_id}/trace")
def diagnosis_trace(
    incident_id: str,
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    diagnosis = db.scalar(
        select(Diagnosis)
        .where(Diagnosis.incident_id == incident_id)
        .order_by(Diagnosis.id.desc())
    )
    if diagnosis is None:
        raise HTTPException(status_code=404, detail="No diagnosis requested")
    return {"diagnosis_id": diagnosis.id, "status": diagnosis.status, "trace": diagnosis.trace}


@app.post("/diagnoses/{diagnosis_id}/review", response_model=DiagnosisResponse)
def review_diagnosis(
    diagnosis_id: int,
    payload: ReviewRequest,
    user: User = Depends(require_roles("commander")),
    db: Session = Depends(get_db),
) -> Diagnosis:
    diagnosis = db.get(Diagnosis, diagnosis_id)
    if diagnosis is None:
        raise HTTPException(status_code=404, detail="Diagnosis not found")
    if diagnosis.status != "awaiting_review":
        raise HTTPException(status_code=409, detail="Diagnosis is not awaiting review")
    diagnosis.review_status = payload.decision
    diagnosis.review_note = payload.note
    diagnosis.reviewed_by = user.id
    diagnosis.reviewed_at = datetime.now(UTC)
    diagnosis.status = "completed"
    diagnosis.trace = [
        *diagnosis.trace,
        {
            "timestamp": diagnosis.reviewed_at.isoformat(),
            "step": "human_review",
            "status": payload.decision,
            "detail": "Recommendation recorded; no remediation was executed.",
        },
    ]
    db.commit()
    db.refresh(diagnosis)
    return diagnosis


@app.get("/evaluations/summary", response_model=EvaluationSummary)
def evaluation_summary(
    _user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EvaluationSummary:
    cases = db.scalars(select(EvaluationCase)).all()
    diagnoses = db.scalars(
        select(Diagnosis).where(Diagnosis.report.is_not(None)).order_by(Diagnosis.id.desc())
    ).all()
    latest_by_incident: dict[str, Diagnosis] = {}
    for diagnosis in diagnoses:
        latest_by_incident.setdefault(diagnosis.incident_id, diagnosis)
    correct = 0
    covered = 0
    valid = 0
    unsafe = 0
    latencies: list[float] = []
    case_map = {case.incident_id: case for case in cases}
    for incident_id, diagnosis in latest_by_incident.items():
        case = case_map.get(incident_id)
        if not case or not diagnosis.report:
            continue
        try:
            report = RCAReport.model_validate(diagnosis.report)
            valid += 1
            correct += int(report.root_cause_category == case.expected_root_cause_category)
            available_prefixes = {item.split(":", 1)[0] for item in report.evidence_ids}
            required_prefixes = {item.split(":", 1)[0] for item in case.required_evidence_ids}
            covered += int(required_prefixes.issubset(available_prefixes))
            unsafe += int(contains_unsafe_execution_claim(report))
        except Exception:
            pass
        if diagnosis.started_at and diagnosis.completed_at:
            latencies.append((diagnosis.completed_at - diagnosis.started_at).total_seconds())
    completed = len(latest_by_incident)
    denominator = completed or 1
    return EvaluationSummary(
        total_cases=len(cases),
        completed_diagnoses=completed,
        root_cause_accuracy=round(correct / denominator, 4),
        evidence_coverage=round(covered / denominator, 4),
        structured_output_validity=round(valid / denominator, 4),
        unsafe_action_count=unsafe,
        average_latency_seconds=round(sum(latencies) / (len(latencies) or 1), 3),
    )


@app.post("/admin/seed-data")
def seed_data(_user: User = Depends(require_roles("commander"))) -> dict:
    return seed_database(index_rag=True)


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.scalar(select(func.count()).select_from(Incident))
    return {
        "status": "healthy",
        "service": settings.app_name,
        "environment": settings.app_env,
        "automatic_actions": False,
    }


@app.get("/metrics")
def metrics(db: Session = Depends(get_db)) -> Response:
    incidents = db.scalar(select(func.count()).select_from(Incident)) or 0
    diagnoses = db.scalar(select(func.count()).select_from(Diagnosis)) or 0
    body = (
        "# HELP ai_sre_incidents_total Seeded incidents\n"
        "# TYPE ai_sre_incidents_total gauge\n"
        f"ai_sre_incidents_total {incidents}\n"
        "# HELP ai_sre_diagnoses_total Requested diagnoses\n"
        "# TYPE ai_sre_diagnoses_total counter\n"
        f"ai_sre_diagnoses_total {diagnoses}\n"
    )
    return Response(content=body, media_type="text/plain; version=0.0.4")
