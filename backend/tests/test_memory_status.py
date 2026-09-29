"""Tests for GET /api/memory/status (the Hindsight readiness probe)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_memory_status_reports_unavailable_without_key(client: TestClient) -> None:
    response = client.get("/api/memory/status")

    assert response.status_code == 200
    body = response.json()
    status = body["memory_status"]
    assert status["provider"] == "Hindsight by Vectorize"
    assert status["configured"] is False
    assert status["available"] is False
    assert status["message"] == "Hindsight memory unavailable"
    assert status["bank_id"] == "memoryops-test-bank"
    assert body["checked_at"]


def test_memory_status_reports_available_with_stub(memory_client: TestClient) -> None:
    status = memory_client.get("/api/memory/status").json()["memory_status"]

    assert status["available"] is True
    assert status["configured"] is True
    assert status["memories_found"] == 1


def test_memory_status_reports_error_from_stub(failing_memory_client: TestClient) -> None:
    status = failing_memory_client.get("/api/memory/status").json()["memory_status"]

    assert status["available"] is False
    assert status["message"] == "Hindsight memory unavailable"
    assert "stub error" in status["error"]
