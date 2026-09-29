"""Groq LLM integration for MemoryOps.

Groq turns the live incident plus the *recalled Hindsight memories* into a
structured analysis and a ranked action plan.

Failure policy: if ``GROQ_API_KEY`` is missing or the call fails, the agent falls
back to a deterministic runbook. Memory-grounded fallbacks keep their
``source="hindsight_memory"`` label, generic ones are labelled
``source="general_knowledge"`` — the UI never claims a memory-influenced answer
that Groq did not produce.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from .config import Settings, get_settings
from .models import (
    ActionSource,
    AnalyzeRequest,
    Confidence,
    IncidentAnalysis,
    IncidentRecord,
    LLMStatus,
    MemoryHit,
    MemoryStatus,
    RecommendedAction,
)
from .prompts import (
    build_analysis_prompt,
    build_generic_recommendations,
    build_lesson_prompt,
    fallback_recommendations_from_memory,
)

logger = logging.getLogger(__name__)

_VALID_CONFIDENCE = {item.value for item in Confidence}


@dataclass
class AnalysisResult:
    """Outcome of one analysis pass."""

    analysis: IncidentAnalysis
    actions: list[RecommendedAction] = field(default_factory=list)
    llm_status: LLMStatus = field(default_factory=LLMStatus)


def _extract_json(raw: str) -> dict:
    """Parse a JSON object out of a model response, tolerating code fences."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("Groq response did not contain a valid JSON object")


def _as_text(value: object, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        return "; ".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


class GroqLLM:
    """Small async wrapper around the Groq chat-completions API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: object | None = None

    @property
    def configured(self) -> bool:
        return self.settings.groq_configured

    def _get_client(self) -> object | None:
        if not self.configured:
            return None
        if self._client is None:
            from groq import AsyncGroq

            self._client = AsyncGroq(
                api_key=self.settings.groq_api_key,
                timeout=self.settings.groq_timeout_seconds,
            )
        return self._client

    def _status(
        self,
        *,
        used: bool,
        message: str,
        error: str | None = None,
    ) -> LLMStatus:
        return LLMStatus(
            provider="Groq",
            configured=self.configured,
            used=used,
            model=self.settings.groq_model,
            message=message,
            error=error,
        )

    async def _chat(self, messages: list[dict[str, str]], json_mode: bool) -> str:
        client = self._get_client()
        if client is None:
            raise RuntimeError("GROQ_API_KEY is not configured")
        kwargs: dict[str, object] = {
            "model": self.settings.groq_model,
            "messages": messages,
            "temperature": self.settings.groq_temperature,
            "max_tokens": self.settings.groq_max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        completion = await client.chat.completions.create(**kwargs)  # type: ignore[attr-defined]
        return completion.choices[0].message.content or ""

    # -- analysis ---------------------------------------------------------
    async def analyze(
        self,
        request: AnalyzeRequest,
        memories: list[MemoryHit],
        memory_status: MemoryStatus,
        memories_text: str,
    ) -> AnalysisResult:
        """Produce the incident analysis and ranked action plan."""
        memory_used = memory_status.available and memory_status.memories_found > 0

        if not self.configured:
            return self._fallback(
                request,
                memories,
                memory_used,
                "Groq is not configured (GROQ_API_KEY missing) — deterministic runbook used.",
            )

        messages = build_analysis_prompt(request, memories_text, memory_status)
        try:
            raw = await self._chat(messages, json_mode=True)
            payload = _extract_json(raw)
        except Exception as exc:
            logger.warning("Groq analysis failed: %s", exc)
            return self._fallback(request, memories, memory_used, f"Groq call failed: {exc}")

        analysis = IncidentAnalysis(
            summary=_as_text(payload.get("summary"), "Analysis unavailable."),
            severity_assessment=_as_text(payload.get("severity_assessment")),
            likely_causes=[_as_text(item) for item in (payload.get("likely_causes") or []) if item],
            memory_used=bool(payload.get("memory_used")) and memory_used,
            memory_influence=_as_text(payload.get("memory_influence")),
            similar_incident_ids=[
                _as_text(item) for item in (payload.get("similar_incident_ids") or []) if item
            ][:5],
            generated_by=f"groq:{self.settings.groq_model}",
        )

        actions = self._parse_actions(payload.get("recommended_actions"), memories)
        if not actions:
            actions = self._fallback_actions(memories, memory_used)

        status_message = (
            f"Groq model '{self.settings.groq_model}' produced the analysis."
            if memory_used
            else f"Groq model '{self.settings.groq_model}' produced general guidance (no memory)."
        )
        return AnalysisResult(
            analysis=analysis,
            actions=actions,
            llm_status=self._status(used=True, message=status_message),
        )

    def _parse_actions(
        self, raw_actions: object, memories: list[MemoryHit]
    ) -> list[RecommendedAction]:
        known_ids = {hit.id for hit in memories}
        actions: list[RecommendedAction] = []
        if not isinstance(raw_actions, list):
            return actions

        for index, item in enumerate(raw_actions, start=1):
            if not isinstance(item, dict):
                continue
            action_text = _as_text(item.get("action"))
            if not action_text:
                continue
            confidence = _as_text(item.get("confidence"), "medium").lower()
            if confidence not in _VALID_CONFIDENCE:
                confidence = "medium"

            based_on = [
                str(memory_id)
                for memory_id in (item.get("based_on_memory_ids") or [])
                if str(memory_id) in known_ids
            ]
            raw_priority = item.get("priority")
            priority = raw_priority if isinstance(raw_priority, int) and raw_priority > 0 else index

            actions.append(
                RecommendedAction(
                    action=action_text,
                    rationale=_as_text(item.get("rationale")),
                    confidence=Confidence(confidence),
                    source=(
                        ActionSource.HINDSIGHT_MEMORY if based_on else ActionSource.GENERAL_KNOWLEDGE
                    ),
                    priority=priority,
                    based_on_memory_ids=based_on,
                )
            )
        return sorted(actions, key=lambda action: action.priority)

    def _fallback_actions(
        self, memories: list[MemoryHit], memory_used: bool
    ) -> list[RecommendedAction]:
        if memory_used and memories:
            return [
                RecommendedAction(
                    action=action,
                    rationale=rationale,
                    confidence=Confidence.MEDIUM,
                    source=ActionSource.HINDSIGHT_MEMORY,
                    priority=index,
                    based_on_memory_ids=[memory_id] if memory_id else [],
                )
                for index, (action, rationale, memory_id) in enumerate(
                    fallback_recommendations_from_memory(memories), start=1
                )
            ]
        return [
            RecommendedAction(
                action=action,
                rationale=rationale,
                confidence=Confidence.LOW,
                source=ActionSource.GENERAL_KNOWLEDGE,
                priority=index,
            )
            for index, (action, rationale, _) in enumerate(
                build_generic_recommendations(), start=1
            )
        ]

    def _fallback(
        self,
        request: AnalyzeRequest,
        memories: list[MemoryHit],
        memory_used: bool,
        reason: str,
    ) -> AnalysisResult:
        scope = f"{request.service} — {request.symptom}"

        if memory_used and memories:
            memory_recs = fallback_recommendations_from_memory(memories)
            summary = (
                f"{scope} in {request.environment}. No LLM reasoning was available, but Hindsight "
                f"recalled {len(memories)} relevant prior experience(s), so the plan below is "
                "grounded in what worked before."
            )
            influence = (
                "Hindsight returned relevant prior incident experience; the recommended actions "
                "are derived from the remembered resolutions."
            )
            causes = [rationale for _, rationale, _ in memory_recs]
        else:
            generic_recs = build_generic_recommendations()
            summary = (
                f"{scope} in {request.environment}. No relevant prior experience was available in "
                "Hindsight, so this is general troubleshooting guidance."
            )
            influence = (
                "No prior Hindsight memory matched this incident, so no experience-based "
                "recommendation could be made. This is general guidance only."
            )
            causes = [rationale for _, rationale, _ in generic_recs]

        return AnalysisResult(
            analysis=IncidentAnalysis(
                summary=summary,
                severity_assessment=(
                    f"Reported as {request.severity.value}; confirm blast radius before "
                    "declaring impact."
                ),
                likely_causes=causes[:4],
                memory_used=memory_used,
                memory_influence=influence,
                similar_incident_ids=sorted(
                    {
                        hit.related_incident_id
                        for hit in memories
                        if hit.related_incident_id
                    }
                ),
                generated_by="template",
            ),
            actions=self._fallback_actions(memories, memory_used),
            llm_status=self._status(used=False, message=reason, error=reason),
        )

    # -- lessons ----------------------------------------------------------
    async def summarize_lesson(self, record: IncidentRecord) -> str:
        """One-line lesson learned for a resolved incident."""
        if not self.configured:
            return ""
        try:
            text = await self._chat(build_lesson_prompt(record), json_mode=False)
        except Exception as exc:
            logger.warning("Groq lesson summarisation failed: %s", exc)
            return ""
        return re.sub(r"\s+", " ", text).strip().strip('"')[:280]
