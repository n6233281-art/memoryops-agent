"""API tests for the MemoryOps health endpoint and demo helpers."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_endpoint_returns_configuration(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "MemoryOps"
    assert body["hindsight_configured"] is False
    assert body["groq_configured"] is False
    assert body["hindsight_bank_id"] == "memoryops-test-bank"
    assert body["hindsight_url"].startswith("https://")
    assert body["incidents_stored"] == 0
    assert body["data_file"]


def test_health_counts_stored_incidents(client: TestClient) -> None:
    client.post(
        "/api/incidents/analyze",
        json={"service": "Payment API", "symptom": "HTTP 503 errors"},
    )

    body = client.get("/api/health").json()
    assert body["incidents_stored"] == 1


def test_synthetic_example_is_clearly_labelled(client: TestClient) -> None:
    response = client.get("/api/demo/synthetic-example")

    assert response.status_code == 200
    body = response.json()
    assert body["synthetic"] is True
    assert "SYNTHETIC" in body["label"]
    assert body["incident_id"] == "INC-001"
    assert body["root_cause"] == "Database connection pool exhaustion"
    assert body["resolution"] == "Increased database connection pool from 50 to 100"


def test_demo_reset_clears_local_ledger(client: TestClient) -> None:
    client.post(
        "/api/incidents/analyze",
        json={"service": "Payment API", "symptom": "HTTP 503 errors"},
    )
    assert client.get("/api/incidents").json()["total"] == 1

    reset = client.post("/api/demo/reset")
    assert reset.status_code == 200
    assert reset.json()["incidents_cleared"] is True
    assert client.get("/api/incidents").json()["total"] == 0
    assert client.get("/api/health").json()["incidents_stored"] == 0
