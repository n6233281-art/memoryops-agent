"""Verifies the raw-HTTP fallback speaks the documented Hindsight REST protocol.

A fake ``httpx.AsyncClient`` captures the outgoing request so we can assert the
exact URL, auth header and JSON body without touching the network.
"""

from __future__ import annotations

import asyncio

import pytest

from app import hindsight_client as hc
from app.hindsight_client import HindsightClient

from .conftest import make_settings


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class FakeAsyncClient:
    """Records every request and returns canned responses."""

    calls: list[dict] = []
    responses: dict[str, dict] = {}

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False

    async def _record(self, method: str, url: str, json: dict, headers: dict) -> FakeResponse:
        FakeAsyncClient.calls.append(
            {"method": method, "url": url, "json": json, "headers": headers}
        )
        for suffix, payload in FakeAsyncClient.responses.items():
            if url.endswith(suffix):
                return FakeResponse(payload)
        return FakeResponse({})

    async def post(self, url: str, json: dict | None = None, headers: dict | None = None):
        return await self._record("POST", url, json or {}, headers or {})

    async def put(self, url: str, json: dict | None = None, headers: dict | None = None):
        return await self._record("PUT", url, json or {}, headers or {})

    async def delete(self, url: str, headers: dict | None = None):
        return await self._record("DELETE", url, {}, headers or {})


def _recall_result() -> dict:
    return {
        "results": [
            {
                "id": "mem-1",
                "text": (
                    "The Payment API 503 incident was caused by database connection pool "
                    "exhaustion; raising the pool from 50 to 100 fixed it."
                ),
                "type": "experience",
                "context": "production incident postmortem",
                "document_id": "incident-INC-001",
                "entities": ["Payment API"],
                "metadata": {
                    "incident_id": "INC-001",
                    "service": "Payment API",
                    "symptom": "HTTP 503 errors",
                    "root_cause": "Database connection pool exhaustion",
                    "resolution": "Increased database connection pool from 50 to 100",
                },
                "mentioned_at": "2026-04-01T10:05:00Z",
                "scores": {
                    "final": 0.87,
                    "reranker": 0.8,
                    "semantic": 0.75,
                    "keyword": 6.1,
                },
            }
        ]
    }


@pytest.fixture()
def rest_client(tmp_path, monkeypatch):
    """HindsightClient forced onto the REST transport with a stubbed transport."""
    FakeAsyncClient.calls = []
    FakeAsyncClient.responses = {
        "/memories/recall": _recall_result(),
        "/memories": {"success": True, "items_count": 3, "bank_id": "memoryops-test-bank"},
    }
    monkeypatch.setattr(hc.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(HindsightClient, "_get_sdk", lambda self: None)

    settings = make_settings(
        tmp_path,
        hindsight_api_key="hsk_test_key",
        hindsight_url="https://api.hindsight.vectorize.io",
    )
    return HindsightClient(settings)


def test_retain_posts_to_documented_path_with_bearer_token(rest_client: HindsightClient) -> None:
    result = asyncio.run(
        rest_client.store_incident_experience(
            document_id="incident-INC-001",
            content="POST-INCIDENT EXPERIENCE REPORT ...",
            metadata={"incident_id": "INC-001"},
        )
    )

    assert result.stored is True

    retain_call = next(call for call in FakeAsyncClient.calls if call["url"].endswith("/memories"))
    assert retain_call["method"] == "POST"
    assert retain_call["url"] == (
        "https://api.hindsight.vectorize.io/v1/default/banks/memoryops-test-bank/memories"
    )
    assert retain_call["headers"]["Authorization"] == "Bearer hsk_test_key"
    assert retain_call["json"]["async"] is False
    assert retain_call["json"]["items"][0]["document_id"] == "incident-INC-001"
    assert retain_call["json"]["items"][0]["metadata"] == {"incident_id": "INC-001"}

    # The bank is created/updated first via the idempotent PUT.
    bank_call = next(call for call in FakeAsyncClient.calls if call["method"] == "PUT")
    assert bank_call["url"] == (
        "https://api.hindsight.vectorize.io/v1/default/banks/memoryops-test-bank"
    )


def test_recall_posts_to_memories_recall_with_query(rest_client: HindsightClient) -> None:
    hits, status = asyncio.run(rest_client.search_relevant_memories("Payment API 503 errors"))

    recall_call = next(
        call for call in FakeAsyncClient.calls if call["url"].endswith("/memories/recall")
    )
    assert recall_call["method"] == "POST"
    assert recall_call["url"] == (
        "https://api.hindsight.vectorize.io/v1/default/banks/memoryops-test-bank"
        "/memories/recall"
    )
    assert recall_call["json"]["query"] == "Payment API 503 errors"
    assert recall_call["json"]["types"] == ["world", "experience", "observation"]
    assert recall_call["headers"]["Authorization"] == "Bearer hsk_test_key"

    assert status.available is True
    assert status.memories_found == 1
    assert len(hits) == 1


def test_recalled_memory_is_mapped_for_the_ui(rest_client: HindsightClient) -> None:
    hits, _ = asyncio.run(rest_client.search_relevant_memories("Payment API 503 errors"))
    memory = hits[0]

    assert memory.id == "mem-1"
    assert memory.fact_type == "experience"
    assert memory.score == 0.87
    assert memory.related_incident_id == "INC-001"
    assert memory.demo_metadata["root_cause"] == "Database connection pool exhaustion"
    assert memory.demo_metadata["resolution"] == (
        "Increased database connection pool from 50 to 100"
    )
    assert "same affected service (Payment API)" in memory.relevance_reason
    assert "final=0.870" in memory.relevance_reason


def test_format_memories_for_prompt_is_explicit_when_empty() -> None:
    assert HindsightClient.format_memories_for_prompt([]) == "NO_MEMORY_AVAILABLE"
