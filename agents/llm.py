from __future__ import annotations

import json
from typing import Protocol

import httpx

from backend.config import get_settings
from backend.schemas import RCAReport


class RCAClient(Protocol):
    async def generate(self, incident: dict, evidence: list[dict]) -> RCAReport: ...


class OllamaRCAClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    async def generate(self, incident: dict, evidence: list[dict]) -> RCAReport:
        system_prompt = (
            "You are an SRE incident analyst. Use only the supplied evidence. Never claim that you "
            "executed a command, rollback, deployment, or remediation. Recommendations are proposals "
            "that require human review. Cite only exact evidence_id values supplied below. If evidence "
            "is insufficient, lower confidence and state that limitation."
        )
        payload = {
            "incident": {
                "id": incident["id"],
                "title": incident["title"],
                "service_name": incident["service_name"],
                "alert_summary": incident["alert_summary"],
                "metrics": incident["metrics"],
            },
            "evidence": evidence,
        }
        request = {
            "model": self.settings.ollama_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": "Produce the RCA JSON for this investigation:\n" + json.dumps(payload),
                },
            ],
            "stream": False,
            "think": False,
            "format": RCAReport.model_json_schema(),
            "options": {
                "temperature": 0,
                "num_ctx": self.settings.ollama_context_length,
            },
        }
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(f"{self.settings.ollama_base_url}/api/chat", json=request)
            response.raise_for_status()
        content = response.json()["message"]["content"]
        return RCAReport.model_validate_json(content)

