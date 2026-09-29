"""End-to-end test of the core claim: the agent *learns* from a resolved incident.

This wires the real :class:`HindsightClient` (onto a stateful fake Hindsight REST
transport), the real :class:`IncidentResponseAgent`, the real FastAPI routes and a
stubbed Groq, then walks the exact demo flow:

    incident 1 → no memory → resolve (retain) → incident 2 → memory recalled

If this test fails, the product's central promise is broken.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import hindsight_client as hc
from app.hindsight_client import HindsightClient
from app.incident_service import IncidentService, IncidentStore
from app.main import create_app, get_incident_service

from .conftest import make_settings
from .fakes import StubAsyncGroq

ANALYZE_PAYLOAD = {
    "service": "Payment API",
    "symptom": "HTTP 503 errors",
    "severity": "SEV2",
    "environment": "production",
    "description": "4% of checkout requests failing at the evening traffic peak.",
}

RESOLVE_PAYLOAD = {
    "root_cause": "Database connection pool exhaustion",
    "resolution": "Increased database connection pool from 50 to 100",
    "outcome": "Payment API recovered and error rate returned to normal",
    "outcome_status": "resolved",
}


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class StatefulHindsight:
    """A tiny in-memory Hindsight REST server.

    Retains what it is given and recalls a memory only when the query mentions the
    service that memory belongs to. A fresh instance holds nothing, so the first
    recall legitimately finds no memory.
    """

    def __init__(self) -> None:
        self.retained: list[dict] = []
        self.bank_id = "memoryops-incident-loop"
        self.calls: list[tuple[str, str]] = []

    def handle(self, method: str, url: str, payload: dict, headers: dict) -> dict:
        self.calls.append((method, url))

        if url.endswith("/memories/recall"):
            query = str(payload.get("query") or "").lower()
            results = []
            for index, row in enumerate(self.retained):
                service = str(row["metadata"].get("service") or "")
                if service and service.lower() in query:
                    results.append(self._to_result(row, index))
            return {"results": results}

        if url.endswith("/memories"):
            for item in payload.get("items") or []:
                self.retained.append(
                    {
                        "content": item.get("content", ""),
                        "metadata": item.get("metadata") or {},
                        "document_id": item.get("document_id"),
                        "context": item.get("context"),
                    }
                )
            return {"success": True, "bank_id": self.bank_id, "items_count": 3, "async": False}

        if method == "PUT":
            return {"bank_id": self.bank_id, "name": "MemoryOps — Incident Response"}

        return {}

    @staticmethod
    def _to_result(row: dict, index: int) -> dict:
        meta = row["metadata"]
        return {
            "id": f"mem-{index + 1}",
            "text": (
                f"The {meta.get('service')} returned {meta.get('symptom')} and the root cause "
                f"was {meta.get('root_cause')}. {meta.get('resolution')} resolved it: "
                f"{meta.get('outcome')}."
            ),
            "type": "experience",
            "context": row.get("context"),
            "document_id": row.get("document_id"),
            "metadata": meta,
            "entities": [meta.get("service", "")],
            "mentioned_at": "2026-04-01T10:05:00Z",
            "scores": {"final": 0.93, "reranker": 0.9, "semantic": 0.88, "keyword": 7.4},
        }

    def client_factory(self, **kwargs: object) -> "FakeAsyncClient":
        return FakeAsyncClient(self)


class FakeAsyncClient:
    def __init__(self, server: StatefulHindsight) -> None:
        self.server = server

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False

    async def post(self, url: str, json: dict | None = None, headers: dict | None = None):
        return FakeResponse(self.server.handle("POST", url, json or {}, headers or {}))

    async def put(self, url: str, json: dict | None = None, headers: dict | None = None):
        return FakeResponse(self.server.handle("PUT", url, json or {}, headers or {}))

    async def delete(self, url: str, headers: dict | None = None):
        return FakeResponse(self.server.handle("DELETE", url, {}, headers or {}))


@pytest.fixture()
def loop_client(tmp_path, monkeypatch):
    """TestClient with the real HindsightClient over a stateful fake transport."""
    server = StatefulHindsight()
    monkeypatch.setattr(hc.httpx, "AsyncClient", server.client_factory)
    monkeypatch.setattr(HindsightClient, "_get_sdk", lambda self: None)

    settings = make_settings(
        tmp_path,
        hindsight_api_key="hsk_test_key",
        hindsight_url="https://api.hindsight.vectorize.io",
        hindsight_bank_id=server.bank_id,
    )
    service = IncidentService(
        settings=settings,
        memory=HindsightClient(settings),
        llm=StubAsyncGroq(),
        store=IncidentStore(settings.data_file),
    )
    app = create_app()
    app.dependency_overrides[get_incident_service] = lambda: service
    return TestClient(app), server


def _analyze(client: TestClient) -> dict:
    response = client.post("/api/incidents/analyze", json=ANALYZE_PAYLOAD)
    assert response.status_code == 200, response.text
    return response.json()


def test_memory_loop_learns_from_a_resolved_incident(loop_client) -> None:
    client, server = loop_client

    # --- incident 1: the bank is empty, so there is nothing to remember -----
    first = _analyze(client)
    assert first["incident_id"] == "INC-001"
    assert first["retrieved_memories"] == []
    assert first["memory_status"]["available"] is True, "Hindsight itself is reachable"
    assert first["memory_status"]["memories_found"] == 0
    assert "no relevant memory" in first["memory_status"]["message"]
    assert first["analysis"]["memory_used"] is False
    assert all(a["source"] == "general_knowledge" for a in first["recommended_actions"])

    # --- resolve: write the experience into Hindsight ----------------------
    resolved = client.post("/api/incidents/INC-001/resolve", json=RESOLVE_PAYLOAD).json()
    assert resolved["stored_to_memory"] is True
    assert resolved["memory_document_id"] == "incident-INC-001"
    assert resolved["memory_status"]["available"] is True

    # Hindsight received the root cause and the fix as structured metadata.
    assert len(server.retained) == 1
    metadata = server.retained[0]["metadata"]
    assert metadata["incident_id"] == "INC-001"
    assert metadata["root_cause"] == "Database connection pool exhaustion"
    assert metadata["resolution"] == "Increased database connection pool from 50 to 100"
    assert "Symptom: HTTP 503 errors" in server.retained[0]["content"]

    # --- incident 2: the same symptom now recalls the learned experience ---
    second = _analyze(client)
    assert second["incident_id"] == "INC-002"
    assert second["memory_status"]["memories_found"] == 1
    assert len(second["retrieved_memories"]) == 1

    memory = second["retrieved_memories"][0]
    assert memory["related_incident_id"] == "INC-001"
    assert memory["fact_type"] == "experience"
    assert memory["score"] == 0.93
    assert memory["demo_metadata"]["root_cause"] == "Database connection pool exhaustion"
    assert memory["demo_metadata"]["resolution"] == (
        "Increased database connection pool from 50 to 100"
    )
    assert "same affected service (Payment API)" in memory["relevance_reason"]
    assert "final=0.930" in memory["relevance_reason"]

    # The recommendation is now memory-grounded, and says so.
    assert second["analysis"]["memory_used"] is True
    assert "INC-001" in second["analysis"]["similar_incident_ids"]
    memory_actions = [
        action for action in second["recommended_actions"] if action["source"] == "hindsight_memory"
    ]
    assert memory_actions, "at least one action must be attributed to Hindsight memory"
    assert memory_actions[0]["based_on_memory_ids"] == [memory["id"]]
    assert memory_actions[0]["confidence"] == "high"

    # --- the ledger shows the learning happened ----------------------------
    history = client.get("/api/incidents").json()
    assert history["total"] == 2
    states = {item["incident_id"]: item["status"] for item in history["incidents"]}
    assert states == {"INC-001": "resolved", "INC-002": "open"}


def test_memory_loop_uses_the_documented_recall_endpoint(loop_client) -> None:
    client, server = loop_client
    _analyze(client)

    recall_calls = [url for method, url in server.calls if url.endswith("/memories/recall")]
    assert recall_calls, "the agent must recall through the documented endpoint"
    assert recall_calls[0] == (
        "https://api.hindsight.vectorize.io/v1/default/banks/memoryops-incident-loop"
        "/memories/recall"
    )
