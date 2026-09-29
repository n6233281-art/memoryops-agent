"""Test doubles for the Hindsight and Groq layers.

These stubs mimic the public surface of :class:`app.hindsight_client.HindsightClient`
and :class:`app.llm.GroqLLM`, so the API tests exercise the real service,
prompt-building and JSON-parsing code without making network calls.
"""

from __future__ import annotations

import json
import re

from app.llm import GroqLLM
from app.models import MemoryHit, MemoryStatus, MemoryStoreResult

INCIDENT_MEMORY = MemoryHit(
    id="mem-abc-123",
    text=(
        "The Payment API returned HTTP 503 errors in production and the root cause was "
        "database connection pool exhaustion. Increasing the database connection pool "
        "from 50 to 100 resolved it and the error rate returned to normal."
    ),
    fact_type="experience",
    context="production incident postmortem",
    score=0.91,
    scores={"final": 0.91, "reranker": 0.88, "semantic": 0.83, "keyword": 7.2},
    entities=["Payment API", "database connection pool"],
    mentioned_at="2026-04-01T10:05:00Z",
    document_id="incident-INC-001",
    relevance_reason=(
        "Hindsight matched this memory because of same affected service (Payment API); "
        "matching symptom (HTTP 503 errors)."
    ),
    related_incident_id="INC-001",
    demo_metadata={
        "incident_id": "INC-001",
        "service": "Payment API",
        "symptom": "HTTP 503 errors",
        "root_cause": "Database connection pool exhaustion",
        "resolution": "Increased database connection pool from 50 to 100",
        "outcome": "Payment API recovered and error rate returned to normal",
    },
)


class StubMemory:
    """In-memory stand-in for :class:`HindsightClient`."""

    def __init__(self, fail: bool = False, hits: list[MemoryHit] | None = None) -> None:
        self.fail = fail
        self.hits = hits if hits is not None else [INCIDENT_MEMORY]
        self.stored: list[dict] = []

    # -- status helpers ---------------------------------------------------
    def _status(self, available: bool, message: str, found: int = 0) -> MemoryStatus:
        return MemoryStatus(
            provider="Hindsight by Vectorize",
            configured=True,
            available=available,
            bank_id="memoryops-test-bank",
            endpoint="https://api.hindsight.vectorize.io",
            memories_found=found,
            message=message,
        )

    def unavailable_status(self, reason: str) -> MemoryStatus:
        status = self._status(False, "Hindsight memory unavailable")
        status.error = reason
        return status

    # -- operations -------------------------------------------------------
    async def search_relevant_memories(
        self, query: str, limit: int | None = None
    ) -> tuple[list[MemoryHit], MemoryStatus]:
        if self.fail:
            return [], self.unavailable_status("Hindsight recall failed: stub error")
        hits = list(self.hits[: (limit or len(self.hits))])
        status = self._status(
            True,
            f"Hindsight recalled {len(hits)} relevant memory item(s) from bank "
            "'memoryops-test-bank'.",
            found=len(hits),
        )
        return hits, status

    async def store_incident_experience(self, **kwargs: object) -> MemoryStoreResult:
        if self.fail:
            return MemoryStoreResult(
                stored=False,
                document_id=str(kwargs.get("document_id") or ""),
                status=self.unavailable_status("Hindsight retain failed: stub error"),
                message="Hindsight memory unavailable — the experience was NOT stored.",
            )
        self.stored.append(kwargs)
        return MemoryStoreResult(
            stored=True,
            document_id=str(kwargs.get("document_id") or ""),
            memory_ids=["mem-new-1", "mem-new-2"],
            status=self._status(
                True, "Experience stored in Hindsight bank 'memoryops-test-bank' (2 items)."
            ),
            message="Experience stored in Hindsight bank 'memoryops-test-bank' (2 items).",
        )

    async def probe(self) -> MemoryStatus:
        if self.fail:
            return self.unavailable_status("Hindsight recall failed: stub error")
        return self._status(True, "Hindsight reachable.", found=len(self.hits))

    @staticmethod
    def format_memories_for_prompt(hits: list[MemoryHit]) -> str:
        if not hits:
            return "NO_MEMORY_AVAILABLE"
        return "\n\n".join(
            f"[MEMORY {index}]\nid: {hit.id}\nmemory_text: {hit.text}"
            for index, hit in enumerate(hits, start=1)
        )


class StubAsyncGroq(GroqLLM):
    """Groq stub that behaves like a real model: it reads the prompt.

    Specifically it parses the memory ids out of the MEMORY CONTEXT block, so it
    can only ever cite memories that Hindsight actually returned — exactly like a
    well-behaved model, and exactly what the production guard enforces.
    """

    def __init__(self, fail: bool = False) -> None:
        super().__init__(settings=None)  # type: ignore[arg-type]
        self.fail = fail

    @property
    def configured(self) -> bool:  # force the "Groq is available" path in tests
        return True

    @staticmethod
    def _memory_ids(messages: list[dict[str, str]]) -> list[str]:
        user = next((m.get("content", "") for m in messages if m.get("role") == "user"), "")
        return re.findall(r"^id:\s*(\S+)\s*$", user, flags=re.MULTILINE)

    async def _chat(self, messages: list[dict[str, str]], json_mode: bool) -> str:
        if self.fail:
            raise RuntimeError("stub Groq failure")
        if not json_mode:
            return (
                "Pin the database connection pool size in configuration so 503 spikes on the "
                "Payment API can be fixed with a single safe change."
            )

        remembered = self._memory_ids(messages)

        return json.dumps(
            {
                "summary": "Payment API is failing at the edge with 5xx responses.",
                "severity_assessment": "Customer-facing payments impact; treat as high urgency.",
                "likely_causes": [
                    "Database connection pool exhaustion",
                    "Upstream dependency saturation",
                ],
                "memory_used": bool(remembered),
                "memory_influence": (
                    "Hindsight recalled INC-001, where the same symptom was fixed by raising "
                    "the database connection pool from 50 to 100."
                    if remembered
                    else "No prior Hindsight experience matched this incident."
                ),
                "similar_incident_ids": ["INC-001"] if remembered else [],
                "recommended_actions": [
                    {
                        "action": "Raise the database connection pool from 50 to 100",
                        "rationale": "This exact fix resolved INC-001 on the same service.",
                        "confidence": "high",
                        "priority": 1,
                        "based_on_memory_ids": [remembered[0]] if remembered else [],
                    },
                    {
                        "action": "Check pool saturation metrics on the payment database",
                        "rationale": "Confirms whether the pool is the bottleneck right now.",
                        "confidence": "medium",
                        "priority": 2,
                        "based_on_memory_ids": [],
                    },
                ],
            }
        )
