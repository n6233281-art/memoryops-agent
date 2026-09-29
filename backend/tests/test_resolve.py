"""API tests for the MemoryOps resolve endpoint (writing experience into Hindsight)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

RESOLVE_PAYLOAD = {
    "root_cause": "Database connection pool exhaustion",
    "resolution": "Increased database connection pool from 50 to 100",
    "outcome": "Payment API recovered and error rate returned to normal",
    "outcome_status": "resolved",
    "resolved_by": "oncall@example.com",
    "time_to_resolve_minutes": 18,
}


def _create_incident(client: TestClient) -> str:
    response = client.post(
        "/api/incidents/analyze",
        json={
            "service": "Payment API",
            "symptom": "HTTP 503 errors",
            "severity": "SEV2",
            "environment": "production",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["incident_id"]


def _resolve(client: TestClient, incident_id: str, **overrides: object):
    payload = {**RESOLVE_PAYLOAD, **overrides}
    return client.post(f"/api/incidents/{incident_id}/resolve", json=payload)


def test_resolve_stores_experience_in_hindsight(memory_client: TestClient) -> None:
    incident_id = _create_incident(memory_client)

    response = _resolve(memory_client, incident_id)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["incident_id"] == incident_id
    assert body["status"] == "resolved"
    assert body["stored_to_memory"] is True
    assert body["memory_document_id"] == f"incident-{incident_id}"
    assert body["memory_ids"] == ["mem-new-1", "mem-new-2"]
    assert body["memory_status"]["available"] is True
    assert "stored in Hindsight" in body["message"]

    incident = body["incident"]
    assert incident["status"] == "resolved"
    assert incident["root_cause"] == RESOLVE_PAYLOAD["root_cause"]
    assert incident["resolution"] == RESOLVE_PAYLOAD["resolution"]
    assert incident["outcome"] == RESOLVE_PAYLOAD["outcome"]
    assert incident["resolved_at"]
    assert incident["time_to_resolve_minutes"] == 18
    assert body["lesson"]


def test_resolve_reports_unavailable_memory_instead_of_pretending(
    client: TestClient,
) -> None:
    """No Hindsight key -> nothing is stored and the status says so."""
    incident_id = _create_incident(client)

    response = _resolve(client, incident_id)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["stored_to_memory"] is False
    assert body["memory_document_id"] is None
    assert body["memory_status"]["available"] is False
    assert body["memory_status"]["message"] == "Hindsight memory unavailable"
    assert "NOT stored" in body["message"]

    # The incident itself is still resolved locally.
    assert body["incident"]["status"] == "resolved"
    assert client.get(f"/api/incidents/{incident_id}").json()["resolution"] == (
        RESOLVE_PAYLOAD["resolution"]
    )


def test_resolve_reports_error_when_hindsight_store_fails(
    failing_memory_client: TestClient,
) -> None:
    incident_id = _create_incident(failing_memory_client)

    body = _resolve(failing_memory_client, incident_id).json()

    assert body["stored_to_memory"] is False
    assert body["memory_status"]["available"] is False
    assert body["memory_status"]["message"] == "Hindsight memory unavailable"
    assert body["memory_ids"] == []


def test_resolve_unknown_incident_returns_404(memory_client: TestClient) -> None:
    response = _resolve(memory_client, "INC-999")
    assert response.status_code == 404
    assert "INC-999" in response.json()["detail"]


def test_resolve_can_skip_memory_storage(memory_client: TestClient) -> None:
    incident_id = _create_incident(memory_client)

    body = _resolve(memory_client, incident_id, store_in_hindsight=False).json()

    assert body["stored_to_memory"] is False
    assert "skipped" in body["message"].lower()


def test_resolve_validates_required_fields(client: TestClient) -> None:
    incident_id = _create_incident(client)
    response = client.post(
        f"/api/incidents/{incident_id}/resolve", json={"root_cause": "only a root cause"}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("field", ["root_cause", "resolution", "outcome"])
def test_resolve_rejects_blank_fields(client: TestClient, field: str) -> None:
    incident_id = _create_incident(client)
    response = _resolve(client, incident_id, **{field: "   "})
    assert response.status_code == 422


def test_incident_history_and_lookup(memory_client: TestClient) -> None:
    first = _create_incident(memory_client)
    second = _create_incident(memory_client)
    _resolve(memory_client, first)

    history = memory_client.get("/api/incidents").json()
    assert history["total"] == 2
    assert {item["incident_id"] for item in history["incidents"]} == {first, second}

    detail = memory_client.get(f"/api/incidents/{first}").json()
    assert detail["status"] == "resolved"
    assert memory_client.get("/api/incidents/INC-404").status_code == 404
