"""API tests for the MemoryOps analyze endpoint (Hindsight recall + Groq reasoning)."""

from __future__ import annotations

from fastapi.testclient import TestClient

ANALYZE_PAYLOAD = {
    "service": "Payment API",
    "symptom": "HTTP 503 errors",
    "description": "Checkout requests are failing intermittently under peak load.",
    "severity": "SEV2",
    "environment": "production",
    "error_signature": "upstream connect error / connection pool timeout",
}


def _analyze(client: TestClient, **overrides: object) -> dict:
    payload = {**ANALYZE_PAYLOAD, **overrides}
    response = client.post("/api/incidents/analyze", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_analyze_without_hindsight_key_reports_unavailable_memory(client: TestClient) -> None:
    """No API key -> the response must say memory is unavailable, not fake a hit."""
    body = _analyze(client)

    assert body["status"] == "analyzed"
    assert body["incident_id"] == "INC-001"
    assert body["retrieved_memories"] == []

    memory_status = body["memory_status"]
    assert memory_status["available"] is False
    assert memory_status["configured"] is False
    assert memory_status["memories_found"] == 0
    assert memory_status["message"] == "Hindsight memory unavailable"
    assert "HINDSIGHT_API_KEY" in memory_status["error"]

    # No memory -> general guidance only, clearly labelled.
    assert body["analysis"]["memory_used"] is False
    assert body["analysis"]["similar_incident_ids"] == []
    assert body["recommended_actions"]
    assert all(action["source"] == "general_knowledge" for action in body["recommended_actions"])
    assert body["llm_status"]["used"] is False
    assert "not configured" in body["llm_status"]["message"]


def test_analyze_returns_recalled_hindsight_memory(memory_client: TestClient) -> None:
    body = _analyze(memory_client)

    memory_status = body["memory_status"]
    assert memory_status["available"] is True
    assert memory_status["memories_found"] == 1

    assert len(body["retrieved_memories"]) == 1
    memory = body["retrieved_memories"][0]
    assert memory["id"] == "mem-abc-123"
    assert memory["related_incident_id"] == "INC-001"
    assert "database connection pool exhaustion" in memory["text"].lower()
    assert memory["relevance_reason"]
    assert memory["score"] == 0.91
    # The structured previous-incident fields the UI renders in the memory card.
    assert memory["demo_metadata"]["root_cause"] == "Database connection pool exhaustion"
    assert (
        memory["demo_metadata"]["resolution"]
        == "Increased database connection pool from 50 to 100"
    )

    assert body["analysis"]["memory_used"] is True
    assert "INC-001" in body["analysis"]["similar_incident_ids"]
    assert body["llm_status"]["used"] is True

    actions = body["recommended_actions"]
    assert actions[0]["source"] == "hindsight_memory"
    assert actions[0]["based_on_memory_ids"] == ["mem-abc-123"]
    assert actions[0]["confidence"] == "high"
    assert actions[1]["source"] == "general_knowledge"


def test_analyze_records_memory_status_on_incident(memory_client: TestClient) -> None:
    body = _analyze(memory_client)

    incident = body["incident"]
    assert incident["memory_status"]["memories_found"] == 1
    assert len(incident["retrieved_memories"]) == 1
    assert incident["status"] == "open"


def test_analyze_when_hindsight_errors_does_not_claim_memory(
    failing_memory_client: TestClient,
) -> None:
    body = _analyze(failing_memory_client)

    assert body["retrieved_memories"] == []
    memory_status = body["memory_status"]
    assert memory_status["available"] is False
    assert memory_status["message"] == "Hindsight memory unavailable"
    assert "stub error" in memory_status["error"]
    assert body["analysis"]["memory_used"] is False


def test_analyze_falls_back_when_groq_fails(failing_groq_memory_client: TestClient) -> None:
    """Hindsight works but Groq fails -> memory-driven deterministic fallback."""
    body = _analyze(failing_groq_memory_client)

    assert body["memory_status"]["memories_found"] == 1
    assert body["llm_status"]["used"] is False
    assert "Groq" in body["llm_status"]["message"]

    actions = body["recommended_actions"]
    assert actions[0]["source"] == "hindsight_memory"
    assert "Increased database connection pool from 50 to 100" in actions[0]["action"]
    assert actions[0]["based_on_memory_ids"] == ["mem-abc-123"]

    assert body["analysis"]["memory_used"] is True
    assert "INC-001" in body["analysis"]["similar_incident_ids"]


def test_analyze_rejects_missing_required_fields(client: TestClient) -> None:
    response = client.post("/api/incidents/analyze", json={"symptom": "HTTP 503 errors"})
    assert response.status_code == 422


def test_analyze_rejects_blank_service(client: TestClient) -> None:
    response = client.post(
        "/api/incidents/analyze", json={"service": "   ", "symptom": "HTTP 503 errors"}
    )
    assert response.status_code == 422


def test_incident_ids_increment(client: TestClient) -> None:
    first = _analyze(client)
    second = _analyze(client)
    third = _analyze(client, service="Search API", symptom="High latency")

    assert first["incident_id"] == "INC-001"
    assert second["incident_id"] == "INC-002"
    assert third["incident_id"] == "INC-003"
