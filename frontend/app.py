from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
API_URL = os.getenv("API_URL", "http://localhost:8000")
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"


def _load_demo() -> dict:
    return json.loads((ROOT / "demo" / "data.json").read_text(encoding="utf-8"))


def _headers() -> dict:
    return {"Authorization": f"Bearer {st.session_state.token}"}


def _login() -> bool:
    if DEMO_MODE:
        return True
    if st.session_state.get("token"):
        return True
    st.title("AI SRE Copilot")
    st.caption("Local, evidence-grounded incident diagnosis")
    with st.form("login"):
        email = st.text_input("Email", value="analyst@local.dev")
        password = st.text_input("Password", value="analyst123", type="password")
        submitted = st.form_submit_button("Sign in", use_container_width=True)
    if submitted:
        response = requests.post(
            f"{API_URL}/auth/login",
            json={"email": email, "password": password},
            timeout=15,
        )
        if response.ok:
            payload = response.json()
            st.session_state.token = payload["access_token"]
            st.session_state.role = payload["role"]
            st.rerun()
        st.error("Login failed. Make sure the local stack is running.")
    return False


def _report_panel(report: dict, evidence: list[dict]) -> None:
    st.subheader("Root-cause analysis")
    left, middle, right = st.columns(3)
    left.metric("Confidence", f"{report['confidence_score']:.0%}")
    middle.metric("Evidence cited", len(report["evidence_ids"]))
    right.metric("Automatic actions", "0")
    st.markdown(f"**Probable cause**  \n{report['probable_root_cause']}")
    st.markdown(f"**Suggested remediation**  \n{report['suggested_fix']}")
    st.markdown(f"**Rollback recommendation**  \n{report['rollback_recommendation']}")
    st.markdown(f"**Prevention**  \n{report['prevention_action']}")
    st.warning("Human review required. This application never executes remediation.")
    cited = [item for item in evidence if item["evidence_id"] in report["evidence_ids"]]
    with st.expander("Cited evidence", expanded=True):
        for item in cited:
            st.markdown(f"**{item['evidence_id']}** — {item['summary']}")


def _demo_incidents(data: dict) -> None:
    incidents = data["incidents"]
    selected_id = st.selectbox(
        "Incident",
        options=[item["id"] for item in incidents],
        format_func=lambda incident_id: next(
            f"{item['id']} · {item['service']} · {item['title']}"
            for item in incidents
            if item["id"] == incident_id
        ),
    )
    incident = next(item for item in incidents if item["id"] == selected_id)
    severity_color = "red" if incident["severity"] == "SEV-1" else "orange"
    st.markdown(f":{severity_color}[**{incident['severity']}**] · {incident['service']}")
    st.write(incident["alert_summary"])
    cols = st.columns(3)
    cols[0].metric("Error rate", incident["metrics"]["error_rate"])
    cols[1].metric("p95 latency", incident["metrics"]["p95_latency"])
    cols[2].metric("Availability", incident["metrics"]["availability"])
    if st.button("Diagnose incident", type="primary", use_container_width=True):
        with st.status("Running recorded local investigation…", expanded=True) as status:
            for step in incident["trace"]:
                st.write(f"✓ {step['label']}")
                time.sleep(0.18)
            status.update(label="Recorded investigation complete", state="complete")
        st.session_state.demo_result = selected_id
    if st.session_state.get("demo_result") == selected_id:
        _report_panel(incident["report"], incident["evidence"])


def _local_incidents() -> None:
    response = requests.get(f"{API_URL}/incidents", headers=_headers(), timeout=20)
    response.raise_for_status()
    incidents = response.json()
    selected_id = st.selectbox(
        "Incident",
        [item["id"] for item in incidents],
        format_func=lambda incident_id: next(
            f"{item['id']} · {item['service_name']} · {item['title']}"
            for item in incidents
            if item["id"] == incident_id
        ),
    )
    incident = next(item for item in incidents if item["id"] == selected_id)
    st.write(incident["alert_summary"])
    if st.button("Diagnose incident", type="primary", use_container_width=True):
        request = requests.post(
            f"{API_URL}/incidents/{selected_id}/diagnose",
            headers=_headers(),
            timeout=20,
        )
        request.raise_for_status()
        st.session_state.local_diagnosis_id = request.json()["id"]
    if st.session_state.get("local_diagnosis_id"):
        if st.button("Refresh investigation status"):
            st.rerun()
        diagnosis = requests.get(
            f"{API_URL}/incidents/{selected_id}/diagnosis",
            headers=_headers(),
            timeout=20,
        )
        if diagnosis.ok:
            payload = diagnosis.json()
            st.info(f"Status: {payload['status']}")
            for event in payload["trace"]:
                st.write(f"{event['status'].upper()} · {event['step']} · {event['detail']}")
            if payload.get("report"):
                _report_panel(payload["report"], [])


def _evaluation(data: dict | None) -> None:
    st.header("Evaluation contract")
    st.caption("Targets are shown until the complete local golden-set run has been executed.")
    rows = data["evaluation_targets"] if data else []
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.info(
        "The project does not publish accuracy or latency claims until Ollama has run the full "
        "evaluation set. CI always verifies schema validity, evidence isolation, and the no-action policy."
    )


def main() -> None:
    st.set_page_config(page_title="AI SRE Copilot", page_icon="🛡️", layout="wide")
    st.markdown(
        """
        <style>
        .stApp {background: #08111f; color: #e7eef8;}
        [data-testid="stSidebar"] {background: #0d1929;}
        div[data-testid="stMetric"] {background: #102035; padding: 1rem; border-radius: .75rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    if not _login():
        return
    demo_data = _load_demo() if DEMO_MODE else None
    with st.sidebar:
        st.title("AI SRE Copilot")
        st.caption("Evidence before conclusions")
        page = st.radio("Navigate", ["Incidents", "Evaluation", "Architecture"])
        st.divider()
        if DEMO_MODE:
            st.success("Hosted demo mode")
            st.caption("Replays recorded local Ollama investigations. No paid API is used.")
        else:
            st.success("Live local mode")
            st.caption(f"Role: {st.session_state.get('role', 'unknown')}")
    if page == "Incidents":
        st.header("Incident investigation")
        if DEMO_MODE:
            _demo_incidents(demo_data)
        else:
            _local_incidents()
    elif page == "Evaluation":
        _evaluation(demo_data)
    else:
        st.header("System architecture")
        st.graphviz_chart(
            """
            digraph G {
              rankdir=LR; bgcolor="transparent"; node [shape=box style=rounded];
              UI [label="Streamlit UI"]; API [label="FastAPI"];
              DB [label="PostgreSQL"]; K [label="Kafka"];
              W [label="LangGraph worker"]; MCP [label="Read-only MCP tools"];
              C [label="ChromaDB + MiniLM"]; O [label="Ollama qwen3:4b"];
              UI -> API; API -> DB; API -> W; K -> DB; W -> MCP;
              MCP -> DB; MCP -> C; W -> O;
            }
            """
        )


if __name__ == "__main__":
    main()
