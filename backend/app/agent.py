"""The MemoryOps agent: recall from Hindsight, reason with Groq, explain the memory.

This module is the cognitive layer. It has exactly one job — turn a raw incident
report into a *memory-aware* analysis — and it is deliberately small so the
memory-first design is obvious:

1. **Recall** — ask Hindsight for experiences matching this service and symptom.
2. **Reason** — hand the incident *and* the recalled memories to Groq.
3. **Explain** — surface why each memory was relevant and whether it changed the
   recommendation.

If step 1 returns nothing, the agent must say "no prior experience" rather than
behave as if it remembered something.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .hindsight_client import HindsightClient, build_recall_query
from .llm import GroqLLM
from .models import (
    ActionSource,
    AnalyzeRequest,
    IncidentAnalysis,
    LLMStatus,
    MemoryHit,
    MemoryStatus,
    RecommendedAction,
)

logger = logging.getLogger(__name__)


@dataclass
class AgentOutcome:
    """Everything the agent produced for one incident."""

    analysis: IncidentAnalysis
    actions: list[RecommendedAction] = field(default_factory=list)
    memories: list[MemoryHit] = field(default_factory=list)
    memory_status: MemoryStatus = field(default_factory=MemoryStatus)
    llm_status: LLMStatus = field(default_factory=LLMStatus)
    recall_query: str = ""
    memory_prompt: str = ""

    @property
    def memory_used(self) -> bool:
        return self.memory_status.available and len(self.memories) > 0


class IncidentResponseAgent:
    """Memory-first incident response agent."""

    def __init__(
        self,
        memory: HindsightClient,
        llm: GroqLLM,
        recall_limit: int | None = None,
    ) -> None:
        self.memory = memory
        self.llm = llm
        self.recall_limit = recall_limit

    def build_query(self, request: AnalyzeRequest) -> str:
        """The recall query used to search Hindsight for similar incidents."""
        return build_recall_query(
            service=request.service,
            symptom=request.symptom,
            description=request.description,
            error_signature=request.error_signature,
        )

    async def recall(self, request: AnalyzeRequest) -> tuple[str, list[MemoryHit], MemoryStatus]:
        """Step 1 — retrieve relevant experiences from Hindsight."""
        query = self.build_query(request)
        memories, status = await self.memory.search_relevant_memories(
            query, limit=self.recall_limit
        )
        logger.info(
            "Agent recall for %s / %s -> %s (%s)",
            request.service,
            request.symptom,
            status.memories_found,
            status.message,
        )
        return query, memories, status

    async def investigate(self, request: AnalyzeRequest) -> AgentOutcome:
        """Run the full recall → reason → explain loop for one incident."""
        query, memories, memory_status = await self.recall(request)
        memory_prompt = self.memory.format_memories_for_prompt(memories)

        result = await self.llm.analyze(request, memories, memory_status, memory_prompt)

        outcome = AgentOutcome(
            analysis=result.analysis,
            actions=result.actions,
            memories=memories,
            memory_status=memory_status,
            llm_status=result.llm_status,
            recall_query=query,
            memory_prompt=memory_prompt,
        )

        # Defensive consistency: never let the LLM claim a memory that was not recalled.
        if not outcome.memory_used:
            outcome.analysis.memory_used = False
            for action in outcome.actions:
                if (
                    action.source is ActionSource.HINDSIGHT_MEMORY
                    and not action.based_on_memory_ids
                ):
                    action.source = ActionSource.GENERAL_KNOWLEDGE
        return outcome
