from fastapi.testclient import TestClient

from backend.app import app
from backend.db import Base, engine
from backend.seed import seed_database


def setup_module():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed_database(index_rag=False)


def test_login_incidents_and_no_ground_truth_leakage():
    with TestClient(app) as client:
        login = client.post(
            "/auth/login",
            json={"email": "analyst@local.dev", "password": "analyst123"},
        )
        assert login.status_code == 200
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        incidents = client.get("/incidents", headers=headers)
        assert incidents.status_code == 200
        assert len(incidents.json()) == 50
        assert "expected_root_cause" not in incidents.text


def test_viewer_cannot_request_diagnosis():
    with TestClient(app) as client:
        login = client.post(
            "/auth/login",
            json={"email": "viewer@local.dev", "password": "viewer123"},
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        response = client.post("/incidents/INC-001/diagnose", headers=headers)
        assert response.status_code == 403

