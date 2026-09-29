"""Pydantic models shared between the MemoryOps API and its services.

These models are deliberately small and JSON-friendly so the React dashboard can
render every field without transformation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    """Timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class Severity(str, Enum):
    SEV1 = "SEV1"
    SEV2 = "SEV2"
    SEV3 = "SEV3"
    SEV4 = "SEV4"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ActionSource(str, Enum):
    """Where a recommended action came from."""

    HINDSIGHT_MEMORY = "hindsight_memory"
    GENERAL_KNOWLEDGE = "general_knowledge"


class OutcomeStatus(str, Enum):
    RESOLVED = "resolved"
    MITIGATED = "mitigated"
    MONITORING = "monitoring"


# ---------------------------------------------------------------------------
# Hindsight memory models
# ---------------------------------------------------------------------------
class MemoryStatus(BaseModel):
    """Honest, explicit status of the Hindsight memory layer.

    The UI renders ``message`` verbatim, so it must never claim that a memory was
    retrieved when Hindsight is unreachable or unconfigured.
    """

    provider: str = "Hindsight by Vectorize"
    configured: bool = False
    available: bool = False
    bank_id: str | None = None
    endpoint: str | None = None
    memories_found: int = 0
    message: str = "Hindsight memory unavailable"
    error: str | None = None


class MemoryHit(BaseModel):
    """A single memory returned by ``POST /recall``."""

    id: str
    text: str
    fact_type: str | None = None
    context: str | None = None
    score: float | None = None
    scores: dict[str, Any] | None = None
    entities: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    mentioned_at: str | None = None
    occurred_start: str | None = None
    occurred_end: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    relevance_reason: str = ""
    related_incident_id: str | None = None
    demo_metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryStoreResult(BaseModel):
    """Result of retaining an incident experience in Hindsight."""

    stored: bool = False
    document_id: str | None = None
    memory_ids: list[str] = Field(default_factory=list)
    operation_id: str | None = None
    status: MemoryStatus = Field(default_factory=MemoryStatus)
    message: str = "Hindsight memory unavailable"


# ---------------------------------------------------------------------------
# Incident models
# ---------------------------------------------------------------------------
class AnalyzeRequest(BaseModel):
    """Body of ``POST /api/incidents/analyze``."""

    model_config = ConfigDict(extra="ignore")

    service: str = Field(..., min_length=1, description="Affected service, e.g. 'Payment API'")
    symptom: str = Field(..., min_length=1, description="Observed symptom, e.g. 'HTTP 503 errors'")
    title: str | None = None
    description: str = ""
    severity: Severity = Severity.SEV2
    environment: str = "production"
    error_signature: str | None = None
    reported_by: str | None = None
    started_at: str | None = None

    @field_validator("service", "symptom", mode="before")
    @classmethod
    def _strip_required(cls, value: object) -> object:
        """Trim and reject blank required fields (validated *before* min_length)."""
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("must not be blank")
        return value


class RecommendedAction(BaseModel):
    action: str
    rationale: str = ""
    confidence: Confidence = Confidence.MEDIUM
    source: ActionSource = ActionSource.GENERAL_KNOWLEDGE
    priority: int = 1
    based_on_memory_ids: list[str] = Field(default_factory=list)


class IncidentAnalysis(BaseModel):
    summary: str
    severity_assessment: str = ""
    likely_causes: list[str] = Field(default_factory=list)
    memory_used: bool = False
    memory_influence: str = ""
    similar_incident_ids: list[str] = Field(default_factory=list)
    generated_by: str = "template"


class LLMStatus(BaseModel):
    provider: str = "Groq"
    configured: bool = False
    used: bool = False
    model: str | None = None
    message: str = ""
    error: str | None = None


class ResolveRequest(BaseModel):
    """Body of ``POST /api/incidents/{id}/resolve``."""

    model_config = ConfigDict(extra="ignore")

    root_cause: str = Field(..., min_length=1)
    resolution: str = Field(..., min_length=1)
    outcome: str = Field(..., min_length=1)
    outcome_status: OutcomeStatus = OutcomeStatus.RESOLVED
    resolved_by: str | None = None
    time_to_resolve_minutes: int | None = None
    notes: str = ""
    store_in_hindsight: bool = True

    @field_validator("root_cause", "resolution", "outcome", mode="before")
    @classmethod
    def _strip_required(cls, value: object) -> object:
        """Trim and reject blank required fields (validated *before* min_length)."""
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("must not be blank")
        return value


class IncidentRecord(BaseModel):
    """A stored incident, persisted to ``data/incidents.json``.

    ``data/incidents.json`` is demo metadata only. The *memory* the agent learns
    from lives in Hindsight.
    """

    incident_id: str
    title: str = ""
    service: str
    symptom: str
    description: str = ""
    severity: Severity = Severity.SEV2
    environment: str = "production"
    error_signature: str | None = None
    reported_by: str | None = None
    started_at: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    status: Literal["open", "resolved"] = "open"

    analysis: IncidentAnalysis | None = None
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    retrieved_memories: list[MemoryHit] = Field(default_factory=list)
    memory_status: MemoryStatus | None = None

    root_cause: str | None = None
    resolution: str | None = None
    outcome: str | None = None
    outcome_status: OutcomeStatus | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    time_to_resolve_minutes: int | None = None
    notes: str = ""
    memory_document_id: str | None = None
    memory_ids: list[str] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    incident_id: str
    status: Literal["analyzed"] = "analyzed"
    created_at: datetime = Field(default_factory=utc_now)
    incident: IncidentRecord
    analysis: IncidentAnalysis
    recommended_actions: list[RecommendedAction]
    retrieved_memories: list[MemoryHit]
    memory_status: MemoryStatus
    llm_status: LLMStatus


class ResolveResponse(BaseModel):
    incident_id: str
    status: Literal["resolved"] = "resolved"
    incident: IncidentRecord
    stored_to_memory: bool
    memory_status: MemoryStatus
    memory_document_id: str | None = None
    memory_ids: list[str] = Field(default_factory=list)
    message: str
    lesson: str = ""


class IncidentHistoryResponse(BaseModel):
    incidents: list[IncidentRecord]
    total: int


class MemoryProbeResponse(BaseModel):
    memory_status: MemoryStatus
    checked_at: datetime = Field(default_factory=utc_now)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    app: str
    version: str
    synthetic_demo_data: bool
    groq_configured: bool
    groq_model: str
    hindsight_configured: bool
    hindsight_bank_id: str
    hindsight_url: str
    data_file: str
    incidents_stored: int
