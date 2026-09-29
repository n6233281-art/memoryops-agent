"""Prompt construction for the MemoryOps incident-response agent.

The prompts are the contract between the agent and two systems:

* **Hindsight** — receives a labelled postmortem document and recalls facts.
* **Groq** — receives the live incident plus the *recalled* memories and must
  return strict JSON.

The memory block is either real recalled memories or the literal string
``NO_MEMORY_AVAILABLE``. The model is told explicitly never to invent a memory,
which is what keeps the demo honest.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .models import AnalyzeRequest, IncidentRecord, MemoryStatus

if TYPE_CHECKING:  # pragma: no cover
    from .models import MemoryHit

ANALYSIS_SYSTEM_PROMPT = """You are MemoryOps, a senior site-reliability engineer \
acting as a production incident-response assistant.

You receive:
1. A NEW incident reported by an engineer.
2. A MEMORY CONTEXT block containing experiences recalled from Hindsight by
   Vectorize (a long-term memory service), or the literal token
   NO_MEMORY_AVAILABLE when nothing relevant was recalled.

Rules you must always follow:
- Only treat something as a remembered experience if it appears in MEMORY CONTEXT.
  Never invent, guess, or embellish a memory. If MEMORY CONTEXT is
  NO_MEMORY_AVAILABLE, you have no prior experience: give sound general
  troubleshooting guidance and set "memory_used" to false.
- When memories exist, prefer them over generic advice. Anchor recommendations to
  the remembered root cause, resolution and outcome, and reference the memory ids
  you used in "based_on_memory_ids".
- Be concrete and operational. Mention exact configuration values, commands,
  dashboards or queries an on-call engineer would use.
- Rank actions by how quickly they restore service.

Reply with a single JSON object and nothing else, using exactly this schema:
{
  "summary": "2-4 sentence assessment of the current incident",
  "severity_assessment": "one sentence on urgency and blast radius",
  "likely_causes": ["most likely cause first", "..."],
  "memory_used": true,
  "memory_influence": "Explain in 1-3 sentences how the recalled Hindsight memory changed your recommendation. If no memory was available, say so explicitly and state that this is general guidance.",
  "similar_incident_ids": ["INC-001"],
  "recommended_actions": [
    {
      "action": "specific remediation step",
      "rationale": "why this step, in one or two sentences",
      "confidence": "high|medium|low",
      "priority": 1,
      "based_on_memory_ids": ["memory id from MEMORY CONTEXT, or empty list"]
    }
  ]
}
Provide between 3 and 6 recommended_actions, ordered by priority ascending."""


def _incident_block(request: AnalyzeRequest) -> str:
    lines = [
        f"service: {request.service}",
        f"symptom: {request.symptom}",
        f"severity: {request.severity.value}",
        f"environment: {request.environment}",
    ]
    if request.title:
        lines.append(f"title: {request.title}")
    if request.started_at:
        lines.append(f"started_at: {request.started_at}")
    if request.error_signature:
        lines.append(f"error_signature: {request.error_signature}")
    if request.description:
        lines.append(f"description: {request.description.strip()}")
    if request.reported_by:
        lines.append(f"reported_by: {request.reported_by}")
    return "\n".join(lines)


def build_analysis_prompt(
    request: AnalyzeRequest,
    memories_text: str,
    memory_status: MemoryStatus,
) -> list[dict[str, str]]:
    """Build the Groq chat messages for incident analysis."""
    memory_available = memory_status.available and memory_status.memories_found > 0
    memory_header = (
        f"MEMORY CONTEXT (source: Hindsight by Vectorize, bank '{memory_status.bank_id}')"
        if memory_available
        else "MEMORY CONTEXT (no usable Hindsight memory for this incident)"
    )
    user_content = (
        "=== NEW INCIDENT ===\n"
        f"{_incident_block(request)}\n\n"
        f"=== {memory_header} ===\n"
        f"{memories_text}\n\n"
        f"memory_layer_status: {memory_status.message}\n\n"
        "Analyse the new incident and return the JSON object described in your "
        "instructions."
    )
    return [
        {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


LESSON_SYSTEM_PROMPT = """You write a single-sentence operational lesson learned from a \
resolved production incident. It must be specific, actionable and under 240 \
characters. Reply with plain text only, no JSON, no markdown, no quotes."""


def build_lesson_prompt(record: IncidentRecord) -> list[dict[str, str]]:
    """Prompt that turns a resolved incident into a reusable lesson."""
    detail = {
        "incident_id": record.incident_id,
        "service": record.service,
        "symptom": record.symptom,
        "root_cause": record.root_cause,
        "resolution": record.resolution,
        "outcome": record.outcome,
    }
    return [
        {"role": "system", "content": LESSON_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Write the lesson learned from this resolved incident:\n"
                f"{json.dumps(detail, indent=2)}"
            ),
        },
    ]


#: Deterministic fallback actions used when Groq is not configured. The API
#: response labels these as general guidance.
GENERIC_RUNBOOK: tuple[tuple[str, str], ...] = (
    (
        "Confirm the blast radius and capture evidence before changing anything.",
        "Establish which endpoints, tenants and regions are affected so later steps are "
        "targeted rather than speculative.",
    ),
    (
        "Check recent changes and deployments for the affected service.",
        "A large share of 5xx spikes correlate with a deploy, config push or feature flag "
        "flip in the preceding window.",
    ),
    (
        "Inspect upstream dependencies for saturation or errors.",
        "HTTP 503 means the service cannot serve requests; an exhausted resource in a "
        "dependency is a common cause.",
    ),
    (
        "Check connection pool, thread pool and worker saturation metrics.",
        "Resource-pool exhaustion is a leading cause of intermittent 503 responses under "
        "load.",
    ),
)


def fallback_recommendations_from_memory(
    memories: list["MemoryHit"],
) -> list[tuple[str, str, str]]:
    """Turn recalled memories into a deterministic memory-driven recommendation set.

    Returns tuples of ``(action, rationale, memory_id)``. Used only when Groq is
    unavailable, so the demo still shows a memory-grounded recommendation.
    """
    recommendations: list[tuple[str, str, str]] = []
    for hit in memories[:3]:
        meta = hit.demo_metadata or {}
        root_cause = meta.get("root_cause") or "the previously confirmed root cause"
        resolution = meta.get("resolution") or hit.text
        incident_ref = f" ({meta['incident_id']})" if meta.get("incident_id") else ""
        recommendations.append(
            (
                f"Apply the previously successful fix: {resolution}",
                f"Hindsight recalled a prior incident{incident_ref} whose root cause was: "
                f"{root_cause}.",
                hit.id,
            )
        )
    return recommendations


def build_generic_recommendations() -> list[tuple[str, str, str]]:
    """Deterministic generic recommendations used when no memory is available."""
    return [(action, rationale, "") for action, rationale in GENERIC_RUNBOOK]
