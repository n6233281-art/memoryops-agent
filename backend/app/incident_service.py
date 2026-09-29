"""Incident orchestration for MemoryOps.

Responsibilities
----------------
* Persist incident *metadata* in ``data/incidents.json`` (demo bookkeeping only).
* Search Hindsight for relevant prior experiences.
* Ask Groq to analyse the incident *using those memories*.
* Store the resolved experience back into Hindsight so the agent learns.

The JSON file is deliberately dumb: it is a demo ledger. The learning happens in
Hindsight.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .agent import IncidentResponseAgent
from .config import Settings, get_settings
from .hindsight_client import (
    HindsightClient,
    build_incident_experience,
    build_incident_metadata,
    incident_document_id,
    incident_tags,
)
from .llm import GroqLLM
from .models import (
    AnalyzeRequest,
    AnalyzeResponse,
    IncidentRecord,
    ResolveRequest,
    ResolveResponse,
)

logger = logging.getLogger(__name__)

_ID_PATTERN = re.compile(r"^INC-(\d+)$", re.IGNORECASE)


class IncidentStore:
    """Tiny JSON-file store for incident metadata (demo ledger)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = asyncio.Lock()

    # -- raw IO -----------------------------------------------------------
    def _read(self) -> dict:
        if not self.path.exists():
            return {"_meta": {}, "incidents": []}
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read %s (%s); starting empty", self.path, exc)
            return {"_meta": {}, "incidents": []}

        if isinstance(data, list):  # tolerate a bare list
            data = {"_meta": {}, "incidents": data}
        data.setdefault("_meta", {})
        data.setdefault("incidents", [])
        return data

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic replace so a crash mid-write cannot corrupt the ledger.
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", delete=False, dir=str(self.path.parent), suffix=".tmp"
        ) as handle:
            json.dump(data, handle, indent=2, default=str)
            temp_name = handle.name
        Path(temp_name).replace(self.path)

    # -- public API -------------------------------------------------------
    def list(self) -> list[IncidentRecord]:
        records: list[IncidentRecord] = []
        for raw in self._read()["incidents"]:
            try:
                records.append(IncidentRecord.model_validate(raw))
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Skipping invalid incident record: %s", exc)
        records.sort(key=lambda record: record.created_at, reverse=True)
        return records

    def get(self, incident_id: str) -> IncidentRecord | None:
        target = incident_id.strip().upper()
        for record in self.list():
            if record.incident_id.upper() == target:
                return record
        return None

    def count(self) -> int:
        return len(self._read()["incidents"])

    def next_incident_id(self) -> str:
        highest = 0
        for record in self.list():
            match = _ID_PATTERN.match(record.incident_id)
            if match:
                highest = max(highest, int(match.group(1)))
        return f"INC-{highest + 1:03d}"

    async def upsert(self, record: IncidentRecord) -> IncidentRecord:
        async with self._lock:
            data = self._read()
            payload = record.model_dump(mode="json")
            incidents = data["incidents"]
            for index, existing in enumerate(incidents):
                if str(existing.get("incident_id", "")).upper() == record.incident_id.upper():
                    incidents[index] = payload
                    break
            else:
                incidents.append(payload)
            self._write(data)
        return record

    async def reset(self) -> None:
        async with self._lock:
            data = self._read()
            data["incidents"] = []
            self._write(data)


class IncidentService:
    """Coordinates Hindsight (memory), Groq (reasoning) and the JSON ledger."""

    def __init__(
        self,
        settings: Settings | None = None,
        memory: HindsightClient | None = None,
        llm: GroqLLM | None = None,
        store: IncidentStore | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.memory = memory or HindsightClient(self.settings)
        self.llm = llm or GroqLLM(self.settings)
        self.store = store or IncidentStore(self.settings.data_file)
        self.agent = IncidentResponseAgent(
            memory=self.memory,  # type: ignore[arg-type]
            llm=self.llm,
            recall_limit=self.settings.hindsight_recall_limit,
        )

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    # -- analyze ----------------------------------------------------------
    async def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        """Search memory, reason with Groq, and persist the incident."""
        incident_id = self.store.next_incident_id()
        now = self._now()
        record = IncidentRecord(
            incident_id=incident_id,
            title=request.title or f"{request.service}: {request.symptom}",
            service=request.service,
            symptom=request.symptom,
            description=request.description,
            severity=request.severity,
            environment=request.environment,
            error_signature=request.error_signature,
            reported_by=request.reported_by,
            started_at=request.started_at,
            created_at=now,
            updated_at=now,
            status="open",
        )

        # 1 & 2. The agent recalls from Hindsight, then reasons with Groq over the
        #        incident plus the recalled experiences.
        outcome = await self.agent.investigate(request)

        record.analysis = outcome.analysis
        record.recommended_actions = outcome.actions
        record.retrieved_memories = outcome.memories
        record.memory_status = outcome.memory_status
        record.updated_at = self._now()
        await self.store.upsert(record)

        return AnalyzeResponse(
            incident_id=incident_id,
            created_at=now,
            incident=record,
            analysis=outcome.analysis,
            recommended_actions=outcome.actions,
            retrieved_memories=outcome.memories,
            memory_status=outcome.memory_status,
            llm_status=outcome.llm_status,
        )

    # -- resolve ----------------------------------------------------------
    async def resolve(self, incident_id: str, request: ResolveRequest) -> ResolveResponse:
        """Store the resolved experience in Hindsight so the agent learns."""
        record = self.store.get(incident_id)
        if record is None:
            raise KeyError(incident_id)

        record.root_cause = request.root_cause
        record.resolution = request.resolution
        record.outcome = request.outcome
        record.outcome_status = request.outcome_status
        record.resolved_by = request.resolved_by
        record.time_to_resolve_minutes = request.time_to_resolve_minutes
        record.notes = request.notes
        record.status = "resolved"
        record.resolved_at = self._now()
        record.updated_at = record.resolved_at

        lesson = await self.llm.summarize_lesson(record)
        if lesson:
            record.notes = f"{record.notes}\nLesson: {lesson}".strip()

        if not request.store_in_hindsight:
            await self.store.upsert(record)
            return ResolveResponse(
                incident_id=record.incident_id,
                incident=record,
                stored_to_memory=False,
                memory_status=self.memory.unavailable_status(
                    "Memory storage was skipped for this request (store_in_hindsight=false)."
                ),
                message="Incident resolved locally; Hindsight storage was skipped by request.",
                lesson=lesson,
            )

        experience = build_incident_experience(
            incident_id=record.incident_id,
            title=record.title,
            service=record.service,
            symptom=record.symptom,
            severity=record.severity.value,
            environment=record.environment,
            description=record.description,
            root_cause=record.root_cause,
            resolution=record.resolution,
            outcome=record.outcome,
            outcome_status=record.outcome_status.value,
            error_signature=record.error_signature,
            time_to_resolve_minutes=record.time_to_resolve_minutes,
            resolved_by=record.resolved_by,
            notes=record.notes,
        )
        document_id = incident_document_id(record.incident_id)
        metadata = build_incident_metadata(
            incident_id=record.incident_id,
            service=record.service,
            symptom=record.symptom,
            severity=record.severity.value,
            environment=record.environment,
            root_cause=record.root_cause,
            resolution=record.resolution,
            outcome=record.outcome,
            outcome_status=record.outcome_status.value,
            resolved_at=record.resolved_at.isoformat(),
        )

        result = await self.memory.store_incident_experience(
            document_id=document_id,
            content=experience,
            metadata=metadata,
            tags=incident_tags(record.service, record.environment),
        )

        if result.stored:
            record.memory_document_id = document_id
            record.memory_ids = result.memory_ids

        await self.store.upsert(record)
        return ResolveResponse(
            incident_id=record.incident_id,
            incident=record,
            stored_to_memory=result.stored,
            memory_status=result.status,
            memory_document_id=document_id if result.stored else None,
            memory_ids=result.memory_ids,
            message=result.message,
            lesson=lesson,
        )
