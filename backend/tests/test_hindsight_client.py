"""Unit tests for the Hindsight integration (paths, mapping, failure handling).

The REST-path assertions pin the integration to the documented Hindsight HTTP API
(0.10.x), so an accidental path drift fails the build instead of silently
returning "no memory found".
"""

from __future__ import annotations

import asyncio

import httpx

from app.hindsight_client import (
    BANK_PATH,
    RECALL_PATH,
    RETAIN_PATH,
    HindsightClient,
    build_incident_experience,
    build_incident_metadata,
    build_recall_query,
    incident_document_id,
    incident_tags,
)

from .conftest import make_settings


def run(coro):
    """Run a coroutine without needing an async pytest plugin."""
    return asyncio.run(coro)


def configured_client(tmp_path, **overrides) -> HindsightClient:
    settings = make_settings(
        tmp_path,
        hindsight_api_key="hsk_test_key",
        hindsight_url="https://api.hindsight.vectorize.io",
        **overrides,
    )
    return HindsightClient(settings)


# ---------------------------------------------------------------------------
# Documented API surface
# ---------------------------------------------------------------------------
def test_rest_paths_match_documented_hindsight_api() -> None:
    assert BANK_PATH == "/v1/default/banks/{bank_id}"
    assert RETAIN_PATH == "/v1/default/banks/{bank_id}/memories"
    assert RECALL_PATH == "/v1/default/banks/{bank_id}/memories/recall"


def test_recall_path_is_not_the_bare_recall_endpoint() -> None:
    """Recall lives under /memories/recall, not /recall."""
    assert RECALL_PATH.endswith("/memories/recall")
    assert not RECALL_PATH.endswith("/banks/{bank_id}/recall")


# ---------------------------------------------------------------------------
# Document and query builders
# ---------------------------------------------------------------------------
def test_build_recall_query_includes_service_and_symptom() -> None:
    query = build_recall_query(
        service="Payment API",
        symptom="HTTP 503 errors",
        description="Started after the traffic peak.",
        error_signature="upstream connect error",
    )

    assert "Payment API" in query
    assert "HTTP 503 errors" in query
    assert "root cause" in query
    assert "upstream connect error" in query


def test_build_incident_experience_contains_all_sections() -> None:
    document = build_incident_experience(
        incident_id="INC-001",
        title="Payment API: HTTP 503 errors",
        service="Payment API",
        symptom="HTTP 503 errors",
        severity="SEV2",
        environment="production",
        description="4% of checkouts failing.",
        root_cause="Database connection pool exhaustion",
        resolution="Increased database connection pool from 50 to 100",
        outcome="Payment API recovered and error rate returned to normal",
        outcome_status="resolved",
        error_signature="upstream connect error",
        time_to_resolve_minutes=18,
        resolved_by="oncall@example.com",
        notes="Add a pool saturation alert.",
    )

    assert "POST-INCIDENT EXPERIENCE REPORT" in document
    assert "Incident ID: INC-001" in document
    assert "Root cause: Database connection pool exhaustion" in document
    assert "Resolution applied: Increased database connection pool from 50 to 100" in document
    assert "Outcome status: resolved" in document
    assert "Time to resolve: 18 minutes" in document


def test_build_incident_metadata_values_are_strings() -> None:
    metadata = build_incident_metadata(
        incident_id="INC-001",
        service="Payment API",
        symptom="HTTP 503 errors",
        severity="SEV2",
        environment="production",
        root_cause="Database connection pool exhaustion",
        resolution="Increased database connection pool from 50 to 100",
        outcome="Recovered",
        outcome_status="resolved",
        resolved_at="2026-04-01T10:05:00Z",
    )

    assert all(isinstance(key, str) and isinstance(value, str) for key, value in metadata.items())
    assert metadata["incident_id"] == "INC-001"
    assert incident_document_id("INC-001") == "incident-INC-001"
    assert "service:payment-api" in incident_tags("Payment API", "production")


# ---------------------------------------------------------------------------
# Unavailable / error behaviour
# ---------------------------------------------------------------------------
def test_search_without_api_key_reports_unavailable(tmp_path) -> None:
    client = HindsightClient(make_settings(tmp_path))

    hits, status = run(client.search_relevant_memories("Payment API 503"))

    assert hits == []
    assert status.available is False
    assert status.configured is False
    assert status.memories_found == 0
    assert status.message == "Hindsight memory unavailable"
    assert "HINDSIGHT_API_KEY" in (status.error or "")


def test_store_without_api_key_does_not_report_success(tmp_path) -> None:
    client = HindsightClient(make_settings(tmp_path))

    result = run(
        client.store_incident_experience(
            document_id="incident-INC-001", content="text", metadata={"incident_id": "INC-001"}
        )
    )

    assert result.stored is False
    assert result.status.message == "Hindsight memory unavailable"


def test_recall_transport_error_is_reported_not_hidden(tmp_path, monkeypatch) -> None:
    client = configured_client(tmp_path)
    monkeypatch.setattr(HindsightClient, "_get_sdk", lambda self: None)
    monkeypatch.setattr(HindsightClient, "_rest_put", lambda self, path, payload: _ok_bank())

    async def boom(self, path, payload):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(HindsightClient, "_rest_post", boom)

    hits, status = run(client.search_relevant_memories("Payment API 503"))

    assert hits == []
    assert status.available is False
    assert status.message == "Hindsight memory unavailable"
    assert "connection refused" in (status.error or "")


def test_recall_with_no_results_reports_reachable_but_empty(tmp_path, monkeypatch) -> None:
    client = configured_client(tmp_path)
    monkeypatch.setattr(HindsightClient, "_get_sdk", lambda self: None)
    monkeypatch.setattr(HindsightClient, "_rest_put", lambda self, path, payload: _ok_bank())
    monkeypatch.setattr(HindsightClient, "_rest_post", lambda self, path, payload: _empty_recall())

    hits, status = run(client.search_relevant_memories("Payment API 503"))

    assert hits == []
    assert status.available is True
    assert status.memories_found == 0
    assert "no relevant memory" in status.message


async def _ok_bank() -> dict:
    return {"bank_id": "memoryops-test-bank"}


async def _empty_recall() -> dict:
    return {"results": []}
