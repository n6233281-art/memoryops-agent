"""Hindsight by Vectorize memory client for MemoryOps.

This module is the memory brain of the agent. It talks to a real Hindsight
deployment (Hindsight Cloud or a self-hosted server) and **never fabricates a
memory**. If Hindsight is not configured, unreachable, or returns an error, the
returned :class:`~app.models.MemoryStatus` says so explicitly with
``message="Hindsight memory unavailable"``.

Two transports are supported, tried in order:

1. The official SDK (``pip install hindsight-client``) using its native async
   methods (``acreate_bank`` / ``aretain`` / ``arecall``).
2. Raw HTTP via ``httpx`` against the documented REST API, so the integration
   still works if the SDK is missing. Verified against Hindsight HTTP API 0.10.2:

   * ``PUT  /v1/default/banks/{bank_id}``                 — create/update the bank
   * ``POST /v1/default/banks/{bank_id}/memories``        — retain (store)
   * ``POST /v1/default/banks/{bank_id}/memories/recall`` — recall (search)
   * ``Authorization: Bearer <HINDSIGHT_API_KEY>``

Environment variables (never hard-coded):
``HINDSIGHT_API_KEY``, ``HINDSIGHT_URL``, ``HINDSIGHT_BANK_ID``.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from .config import Settings, get_settings
from .models import MemoryHit, MemoryStatus, MemoryStoreResult

logger = logging.getLogger(__name__)

BANK_NAME = "MemoryOps — Incident Response"

BANK_BACKGROUND = (
    "MemoryOps is the long-term memory of an AI incident-response agent for a "
    "production platform engineering team. It stores post-incident experiences: "
    "the affected service, the observed symptom, the confirmed root cause, the "
    "resolution that actually worked, and the measured outcome. When a new "
    "incident arrives the agent recalls these experiences and recommends the fix "
    "that worked before."
)

BANK_RETAIN_MISSION = (
    "Extract durable incident-response facts from postmortems: which service and "
    "symptom were involved, the confirmed root cause, the exact remediation that "
    "was applied (including configuration values such as pool sizes, timeouts and "
    "replica counts), the measured outcome, and any prevention or follow-up step. "
    "Preserve numeric before/after values exactly as written."
)

#: Hindsight REST paths (HTTP API 0.10.x).
RETAIN_PATH = "/v1/default/banks/{bank_id}/memories"
RECALL_PATH = "/v1/default/banks/{bank_id}/memories/recall"
BANK_PATH = "/v1/default/banks/{bank_id}"

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "was",
    "were", "is", "are", "be", "been", "by", "from", "at", "as", "it", "its",
    "this", "that", "these", "those", "we", "our", "after", "before", "into",
    "returned", "returning", "return", "error", "errors", "issue", "issues",
    "incident", "incidents", "production", "prod", "api", "http", "service",
}


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "unknown"


def _significant_terms(text: str) -> set[str]:
    """Lower-cased terms worth comparing between a query and a memory."""
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_.:-]{2,}", (text or "").lower())
    return {token for token in tokens if token not in _STOPWORDS}


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item) for item in value)
    return str(value)


def build_recall_query(
    service: str,
    symptom: str,
    description: str = "",
    error_signature: str | None = None,
) -> str:
    """Build the natural-language recall query for a new incident.

    Hindsight fuses semantic, keyword, graph and temporal retrieval, so the query
    is written as a full sentence rather than a bag of keywords.
    """
    parts = [
        f"Production incident on the {service} with the symptom: {symptom}.",
        "What was the root cause, the resolution that fixed it, and the outcome "
        "of previous similar incidents on this service?",
    ]
    if description:
        parts.append(f"Context: {description.strip()}")
    if error_signature:
        parts.append(f"Error signature: {error_signature.strip()}")
    return " ".join(parts)


def build_incident_experience(
    *,
    incident_id: str,
    title: str,
    service: str,
    symptom: str,
    severity: str,
    environment: str,
    description: str,
    root_cause: str,
    resolution: str,
    outcome: str,
    outcome_status: str,
    error_signature: str | None = None,
    time_to_resolve_minutes: int | None = None,
    resolved_by: str | None = None,
    notes: str = "",
) -> str:
    """Render an incident experience as a document for Hindsight to learn from.

    Shaped as a labelled postmortem so Hindsight's fact extractor can separate the
    symptom from the root cause and the resolution.
    """
    lines = [
        "POST-INCIDENT EXPERIENCE REPORT",
        f"Incident ID: {incident_id}",
        f"Title: {title}",
        f"Service: {service}",
        f"Environment: {environment}",
        f"Severity: {severity}",
        f"Symptom: {symptom}",
    ]
    if error_signature:
        lines.append(f"Error signature: {error_signature}")
    if description:
        lines.append(f"Observed behaviour: {description.strip()}")
    lines += [
        f"Root cause: {root_cause.strip()}",
        f"Resolution applied: {resolution.strip()}",
        f"Outcome: {outcome.strip()}",
        f"Outcome status: {outcome_status}",
    ]
    if time_to_resolve_minutes is not None:
        lines.append(f"Time to resolve: {time_to_resolve_minutes} minutes")
    if resolved_by:
        lines.append(f"Resolved by: {resolved_by}")
    if notes:
        lines.append(f"Follow-up notes: {notes.strip()}")
    return "\n".join(lines)


def build_incident_metadata(
    *,
    incident_id: str,
    service: str,
    symptom: str,
    severity: str,
    environment: str,
    root_cause: str,
    resolution: str,
    outcome: str,
    outcome_status: str,
    resolved_at: str,
) -> dict[str, str]:
    """Structured metadata stored alongside the memory.

    Hindsight metadata values must be strings. Keeping the incident id here is
    what lets the UI map a recalled fact back to the exact previous incident.
    """
    return {
        "incident_id": incident_id,
        "service": service,
        "symptom": symptom,
        "severity": severity,
        "environment": environment,
        "root_cause": root_cause,
        "resolution": resolution,
        "outcome": outcome,
        "outcome_status": outcome_status,
        "resolved_at": resolved_at,
        "record_type": "incident_postmortem",
    }


def incident_document_id(incident_id: str) -> str:
    """Deterministic Hindsight document id for an incident."""
    return f"incident-{incident_id}"


def incident_tags(service: str, environment: str) -> list[str]:
    """Tags attached to a retained incident experience."""
    return ["incident-experience", f"service:{_slug(service)}", f"env:{_slug(environment)}"]


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------
class HindsightClient:
    """Thin, failure-tolerant wrapper around the Hindsight memory API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.hindsight_url.rstrip("/")
        self.api_key = self.settings.hindsight_api_key
        self.bank_id = self.settings.hindsight_bank_id
        self.timeout = self.settings.hindsight_timeout_seconds
        self.recall_limit = self.settings.hindsight_recall_limit
        self._bank_ready = False
        self._sdk: Any | None = None
        self._sdk_checked = False

    # -- status helpers ---------------------------------------------------
    def _status(
        self,
        *,
        available: bool,
        message: str,
        memories_found: int = 0,
        error: str | None = None,
    ) -> MemoryStatus:
        return MemoryStatus(
            provider="Hindsight by Vectorize",
            configured=self.settings.hindsight_configured,
            available=available,
            bank_id=self.bank_id,
            endpoint=self.base_url,
            memories_found=memories_found,
            message=message,
            error=error,
        )

    def unavailable_status(self, reason: str) -> MemoryStatus:
        """Status object used whenever Hindsight cannot be used."""
        return self._status(available=False, message="Hindsight memory unavailable", error=reason)

    # -- transports -------------------------------------------------------
    def _get_sdk(self) -> Any | None:
        """Return the official SDK client if it is installed, else ``None``."""
        if self._sdk_checked:
            return self._sdk
        self._sdk_checked = True
        if not self.settings.hindsight_configured:
            return None
        try:
            from hindsight_client import Hindsight  # type: ignore[import-not-found]

            self._sdk = Hindsight(base_url=self.base_url, api_key=self.api_key)
            logger.info("Hindsight: using official hindsight-client SDK against %s", self.base_url)
        except Exception as exc:  # pragma: no cover - depends on environment
            logger.info("Hindsight: SDK unavailable (%s); falling back to REST", exc)
            self._sdk = None
        return self._sdk

    @property
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def _rest_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload, headers=self._headers)
        response.raise_for_status()
        return response.json()

    async def _rest_put(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.put(url, json=payload, headers=self._headers)
        response.raise_for_status()
        return response.json()

    async def ensure_bank(self) -> MemoryStatus | None:
        """Create or update the incident bank (idempotent PUT).

        Returns ``None`` on success, or a status describing the failure.
        """
        if not self.settings.hindsight_configured:
            return self.unavailable_status(
                "HINDSIGHT_API_KEY is not set, so no memories can be read or written."
            )
        if self._bank_ready:
            return None

        sdk = self._get_sdk()
        try:
            if sdk is not None:
                await sdk.acreate_bank(
                    self.bank_id,
                    name=BANK_NAME,
                    background=BANK_BACKGROUND,
                    retain_mission=BANK_RETAIN_MISSION,
                    enable_observations=True,
                )
            else:
                await self._rest_put(
                    BANK_PATH.format(bank_id=self.bank_id),
                    {
                        "name": BANK_NAME,
                        "background": BANK_BACKGROUND,
                        "retain_mission": BANK_RETAIN_MISSION,
                        "enable_observations": True,
                    },
                )
            self._bank_ready = True
            return None
        except Exception as exc:
            logger.warning("Hindsight: could not create/update bank %s: %s", self.bank_id, exc)
            return self.unavailable_status(
                f"Could not reach Hindsight bank '{self.bank_id}': {exc}"
            )

    # -- store ------------------------------------------------------------
    async def store_incident_experience(
        self,
        *,
        document_id: str,
        content: str,
        metadata: dict[str, str],
        context: str = "production incident postmortem",
        tags: list[str] | None = None,
    ) -> MemoryStoreResult:
        """Retain a resolved incident experience as a Hindsight memory.

        ``retain_async=False`` (the default) blocks until fact extraction has
        finished, so the very next recall in the demo already finds it.
        """
        missing = await self.ensure_bank()
        if missing is not None:
            return MemoryStoreResult(
                stored=False,
                document_id=document_id,
                status=missing,
                message="Hindsight memory unavailable — the experience was NOT stored.",
            )

        sdk = self._get_sdk()
        try:
            if sdk is not None:
                response = await sdk.aretain(
                    self.bank_id,
                    content,
                    context=context,
                    document_id=document_id,
                    metadata=metadata,
                    tags=tags or [],
                )
                payload = (
                    response.model_dump() if hasattr(response, "model_dump") else dict(response)
                )
            else:
                payload = await self._rest_post(
                    RETAIN_PATH.format(bank_id=self.bank_id),
                    {
                        "items": [
                            {
                                "content": content,
                                "context": context,
                                "document_id": document_id,
                                "metadata": metadata,
                                "tags": tags or [],
                            }
                        ],
                        "async": False,
                    },
                )
        except Exception as exc:
            logger.warning("Hindsight retain failed: %s", exc)
            return MemoryStoreResult(
                stored=False,
                document_id=document_id,
                status=self.unavailable_status(f"Hindsight retain failed: {exc}"),
                message="Hindsight memory unavailable — the experience was NOT stored.",
            )

        success = bool(payload.get("success", True))
        items_count = int(payload.get("items_count") or 0)
        status = self._status(
            available=True,
            message=(
                f"Experience stored in Hindsight bank '{self.bank_id}' "
                f"({items_count} memory item(s) extracted)."
            ),
        )
        return MemoryStoreResult(
            stored=success,
            document_id=document_id,
            memory_ids=[],
            operation_id=payload.get("operation_id"),
            status=status,
            message=status.message,
        )

    # -- search -----------------------------------------------------------
    def _to_hit(self, result: Any, query: str) -> MemoryHit:
        data = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        scores = data.get("scores") or {}
        if hasattr(scores, "model_dump"):
            scores = scores.model_dump()
        final_score = None
        if isinstance(scores, dict) and isinstance(scores.get("final"), (int, float)):
            final_score = float(scores["final"])

        metadata = {key: _format_value(value) for key, value in (data.get("metadata") or {}).items()}
        relation = self._relation_to_incident(metadata, data.get("document_id"))

        return MemoryHit(
            id=str(data.get("id") or ""),
            text=str(data.get("text") or ""),
            fact_type=data.get("type"),
            context=data.get("context"),
            score=final_score,
            scores=scores if isinstance(scores, dict) else None,
            entities=[str(item) for item in (data.get("entities") or [])],
            tags=[str(item) for item in (data.get("tags") or [])],
            mentioned_at=data.get("mentioned_at"),
            occurred_start=data.get("occurred_start"),
            occurred_end=data.get("occurred_end"),
            document_id=data.get("document_id"),
            chunk_id=data.get("chunk_id"),
            relevance_reason=self._relevance_reason(query, data, metadata),
            related_incident_id=relation.get("incident_id"),
            demo_metadata=relation,
        )

    def _relation_to_incident(self, metadata: dict[str, str], document_id: Any) -> dict[str, Any]:
        """Map a recalled memory back to the incident it was learned from.

        Only values Hindsight actually returned are used — nothing is invented
        when metadata is absent.
        """
        incident_id = metadata.get("incident_id")
        if not incident_id and isinstance(document_id, str) and document_id.startswith("incident-"):
            incident_id = document_id.replace("incident-", "", 1)
        relation: dict[str, Any] = {"incident_id": incident_id}
        for key in ("service", "symptom", "root_cause", "resolution", "outcome", "severity"):
            if metadata.get(key):
                relation[key] = metadata[key]
        return relation

    def _relevance_reason(self, query: str, data: dict[str, Any], metadata: dict[str, str]) -> str:
        """Explain — from real data only — why Hindsight returned this memory."""
        query_terms = _significant_terms(query)
        memory_terms = _significant_terms(
            " ".join(
                [
                    str(data.get("text") or ""),
                    str(data.get("context") or ""),
                    " ".join(str(value) for value in metadata.values()),
                ]
            )
        )

        reasons: list[str] = []
        service = (metadata.get("service") or "").strip()
        if service and service.lower() in query.lower():
            reasons.append(f"same affected service ({service})")
        symptom = (metadata.get("symptom") or "").strip()
        if symptom and any(term in query.lower() for term in _significant_terms(symptom)):
            reasons.append(f"matching symptom ({symptom})")
        overlap = sorted(query_terms & memory_terms)
        if overlap:
            reasons.append("shared incident signals: " + ", ".join(overlap[:8]))

        reason_text = (
            "Hindsight matched this memory because of " + "; ".join(reasons) + "."
            if reasons
            else "Hindsight ranked this memory as the closest match to the current incident."
        )

        scores = data.get("scores")
        if hasattr(scores, "model_dump"):
            scores = scores.model_dump()
        if isinstance(scores, dict):
            parts = [
                f"{name}={scores[name]:.3f}"
                for name in ("final", "reranker", "semantic", "keyword")
                if isinstance(scores.get(name), (int, float))
            ]
            if parts:
                reason_text += f" Retrieval scores: {', '.join(parts)}."
        return reason_text

    async def search_relevant_memories(
        self, query: str, limit: int | None = None
    ) -> tuple[list[MemoryHit], MemoryStatus]:
        """Recall memories relevant to ``query``.

        Returns ``([], status)`` with ``available=False`` whenever Hindsight could
        not answer — callers must then report "no memory available" instead of
        pretending a memory was retrieved.
        """
        if not self.settings.hindsight_configured:
            reason = (
                "HINDSIGHT_API_KEY is not set. Add it to backend/.env to enable real "
                "memory retrieval."
            )
            logger.info("Hindsight: %s", reason)
            return [], self.unavailable_status(reason)

        missing = await self.ensure_bank()
        if missing is not None:
            return [], missing

        sdk = self._get_sdk()
        try:
            if sdk is not None:
                response = await sdk.arecall(
                    self.bank_id,
                    query,
                    types=["world", "experience", "observation"],
                    budget="mid",
                    max_tokens=4096,
                    include_entities=True,
                )
                raw_results = list(getattr(response, "results", []) or [])
            else:
                payload = await self._rest_post(
                    RECALL_PATH.format(bank_id=self.bank_id),
                    {
                        "query": query,
                        "types": ["world", "experience", "observation"],
                        "budget": "mid",
                        "max_tokens": 4096,
                        "include": {"entities": True},
                    },
                )
                raw_results = list(payload.get("results") or [])
        except Exception as exc:
            logger.warning("Hindsight recall failed: %s", exc)
            return [], self.unavailable_status(f"Hindsight recall failed: {exc}")

        cap = limit or self.recall_limit
        hits = [self._to_hit(result, query) for result in raw_results[:cap]]
        hits = [hit for hit in hits if hit.text.strip()]

        if hits:
            status = self._status(
                available=True,
                message=(
                    f"Hindsight recalled {len(hits)} relevant memory item(s) from bank "
                    f"'{self.bank_id}'."
                ),
                memories_found=len(hits),
            )
        else:
            status = self._status(
                available=True,
                message=(
                    f"Hindsight is reachable but bank '{self.bank_id}' holds no relevant "
                    "memory for this incident yet."
                ),
                memories_found=0,
            )
        return hits, status

    # -- health -----------------------------------------------------------
    async def probe(self) -> MemoryStatus:
        """Readiness probe used by ``GET /api/memory/status``."""
        if not self.settings.hindsight_configured:
            return self.unavailable_status(
                "HINDSIGHT_API_KEY is not set. Add it to backend/.env to enable Hindsight memory."
            )
        missing = await self.ensure_bank()
        if missing is not None:
            return missing
        _, status = await self.search_relevant_memories("incident root cause resolution")
        return status

    # -- prompt helpers ---------------------------------------------------
    @staticmethod
    def format_memories_for_prompt(hits: list[MemoryHit]) -> str:
        """Render recalled memories as compact, numbered prompt context."""
        if not hits:
            return "NO_MEMORY_AVAILABLE"
        blocks: list[str] = []
        for index, hit in enumerate(hits, start=1):
            lines = [
                f"[MEMORY {index}]",
                f"id: {hit.id}",
                f"type: {hit.fact_type or 'unknown'}",
            ]
            if hit.related_incident_id:
                lines.append(f"incident_id: {hit.related_incident_id}")
            for key in ("service", "symptom", "root_cause", "resolution", "outcome"):
                value = hit.demo_metadata.get(key)
                if value:
                    lines.append(f"{key}: {value}")
            lines.append(f"memory_text: {hit.text}")
            if hit.relevance_reason:
                lines.append(f"why_recalled: {hit.relevance_reason}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)
