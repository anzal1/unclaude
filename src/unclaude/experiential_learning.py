"""Experiential Learning — Extract patterns from completed tasks.

The missing piece: UnClaude executes tasks but never learns from them.
This module runs post-task analysis to extract:

1. WHAT WORKED    — Approaches/tools that led to success
2. WHAT FAILED    — Errors, dead ends, wrong assumptions
3. PATTERNS       — Recurring techniques across similar tasks
4. CONTEXT CUES   — What signals indicate which approach to use

Insights are stored as high-importance Items in hierarchical memory,
creating a growing knowledge base that makes the agent better over time.

On new tasks, the pattern matcher searches episodic memory for similar
past experiences and injects relevant context into the system prompt.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from unclaude.memory_v2 import (
    HierarchicalMemory,
    MemoryLayer,
    MemoryImportance,
    MemoryNode,
)

logger = logging.getLogger(__name__)


# Tags for experiential memory nodes
TAG_EXPERIENCE = "experience"
TAG_SUCCESS = "success_pattern"
TAG_FAILURE = "failure_pattern"
TAG_TECHNIQUE = "technique"
TAG_CONTEXT_CUE = "context_cue"


@dataclass
class TaskOutcome:
    """The outcome of a completed task for analysis."""
    task_description: str
    result: str
    success: bool
    duration_seconds: float
    iterations: int
    tools_used: list[str] = field(default_factory=list)
    errors_encountered: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    project_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExperientialInsight:
    """An insight extracted from task experience."""
    insight_type: str  # success_pattern, failure_pattern, technique, context_cue
    content: str
    confidence: float  # 0.0 - 1.0
    tags: list[str] = field(default_factory=list)
    source_task: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.insight_type,
            "content": self.content,
            "confidence": self.confidence,
            "tags": self.tags,
            "source_task": self.source_task,
        }


class ExperientialLearner:
    """Extracts learning from task outcomes and stores as memory.

    Usage:
        learner = ExperientialLearner(memory)

        # After a task completes
        outcome = TaskOutcome(
            task_description="Fix the auth bug",
            result="Fixed by adding null check in session.py",
            success=True,
            duration_seconds=120,
            iterations=5,
            tools_used=["file_read", "file_write", "bash"],
        )
        insights = learner.extract_insights(outcome)
        learner.store_insights(insights)

        # Before a new task, find relevant experience
        context = learner.find_relevant_experience(
            "There's a bug in the login flow"
        )
    """

    def __init__(self, memory: HierarchicalMemory):
        self.memory = memory

    def extract_insights(self, outcome: TaskOutcome) -> list[ExperientialInsight]:
        """Extract learning insights from a task outcome.

        This is the core learning function — it analyzes what happened
        and produces structured insights.
        """
        insights: list[ExperientialInsight] = []

        if outcome.success:
            insights.extend(self._extract_success_patterns(outcome))
        else:
            insights.extend(self._extract_failure_patterns(outcome))

        insights.extend(self._extract_technique_patterns(outcome))
        insights.extend(self._extract_context_cues(outcome))

        return insights

    def store_insights(self, insights: list[ExperientialInsight]) -> list[str]:
        """Store extracted insights into hierarchical memory.

        Returns list of stored node IDs.
        """
        stored_ids = []

        for insight in insights:
            # Map confidence to importance
            if insight.confidence >= 0.8:
                importance = MemoryImportance.CRITICAL
            elif insight.confidence >= 0.6:
                importance = MemoryImportance.HIGH
            elif insight.confidence >= 0.3:
                importance = MemoryImportance.MEDIUM
            else:
                importance = MemoryImportance.LOW

            tags = [TAG_EXPERIENCE, insight.insight_type] + insight.tags

            try:
                node_id = self.memory.store(
                    content=insight.content,
                    layer=MemoryLayer.ITEM,  # Insights go directly to Item layer
                    importance=importance,
                    tags=tags,
                    metadata={
                        "source": "experiential_learning",
                        "insight_type": insight.insight_type,
                        "confidence": insight.confidence,
                        "source_task": insight.source_task,
                        "timestamp": time.time(),
                    },
                )
                stored_ids.append(node_id)
            except Exception as e:
                logger.error(f"Failed to store insight: {e}")

        logger.info(f"Stored {len(stored_ids)} experiential insights")
        return stored_ids

    def learn_from_task(self, outcome: TaskOutcome) -> list[str]:
        """Convenience: extract and store in one call."""
        insights = self.extract_insights(outcome)
        return self.store_insights(insights)

    def find_relevant_experience(
        self,
        task_description: str,
        limit: int = 5,
    ) -> list[MemoryNode]:
        """Find past experiences relevant to a new task.

        Searches memory for experiential insights that match the
        new task's keywords/domain.
        """
        # Search for experience-tagged items
        results = self.memory.search(
            query=task_description,
            layer=MemoryLayer.ITEM,
            limit=limit * 2,  # Over-fetch for filtering
        )

        # Filter to only experiential insights
        experiences = [
            node for node in results
            if TAG_EXPERIENCE in node.tags
        ]

        return experiences[:limit]

    def format_experience_context(
        self,
        experiences: list[MemoryNode],
        max_chars: int = 2000,
    ) -> str:
        """Format relevant experiences into a context string for the system prompt."""
        if not experiences:
            return ""

        lines = ["## Past Experience (Relevant to This Task)\n"]
        char_count = len(lines[0])

        for exp in experiences:
            insight_type = exp.metadata.get("insight_type", "unknown")
            confidence = exp.metadata.get("confidence", 0.0)
            prefix = {
                TAG_SUCCESS: "SUCCESS",
                TAG_FAILURE: "CAUTION",
                TAG_TECHNIQUE: "TECHNIQUE",
                TAG_CONTEXT_CUE: "CONTEXT",
            }.get(insight_type, "NOTE")

            line = f"- **[{prefix}]** (confidence: {confidence:.0%}) {exp.content}\n"
            if char_count + len(line) > max_chars:
                break
            lines.append(line)
            char_count += len(line)

        return "".join(lines)

    # ── Pattern extraction methods ─────────────────────────────

    def _extract_success_patterns(self, outcome: TaskOutcome) -> list[ExperientialInsight]:
        """Extract what made a successful task work."""
        insights = []
        task_short = outcome.task_description[:100]

        # Efficiency insight
        if outcome.iterations <= 3 and outcome.duration_seconds < 60:
            insights.append(ExperientialInsight(
                insight_type=TAG_SUCCESS,
                content=(
                    f"Quick-solve pattern: Task '{task_short}' completed in "
                    f"{outcome.iterations} iterations ({outcome.duration_seconds:.0f}s). "
                    f"Tools: {', '.join(outcome.tools_used[:5])}."
                ),
                confidence=0.7,
                tags=self._extract_domain_tags(outcome),
                source_task=task_short,
            ))

        # Tool combination insight
        if len(outcome.tools_used) >= 2:
            tool_combo = ", ".join(sorted(set(outcome.tools_used[:5])))
            insights.append(ExperientialInsight(
                insight_type=TAG_SUCCESS,
                content=(
                    f"Effective tool combination for '{task_short}': {tool_combo}. "
                    f"Result: {outcome.result[:150]}."
                ),
                confidence=0.6,
                tags=self._extract_domain_tags(outcome) + ["tool_pattern"],
                source_task=task_short,
            ))

        # File-change pattern
        if outcome.files_modified:
            files = ", ".join(outcome.files_modified[:5])
            insights.append(ExperientialInsight(
                insight_type=TAG_SUCCESS,
                content=(
                    f"For '{task_short}', modified: {files}. "
                    f"The approach that worked: {outcome.result[:150]}."
                ),
                confidence=0.65,
                tags=self._extract_domain_tags(outcome) + ["file_pattern"],
                source_task=task_short,
            ))

        return insights

    def _extract_failure_patterns(self, outcome: TaskOutcome) -> list[ExperientialInsight]:
        """Extract patterns from failed tasks to avoid repeating mistakes."""
        insights = []
        task_short = outcome.task_description[:100]

        # What errors occurred
        if outcome.errors_encountered:
            for error in outcome.errors_encountered[:3]:
                insights.append(ExperientialInsight(
                    insight_type=TAG_FAILURE,
                    content=(
                        f"Error on '{task_short}': {error[:200]}. "
                        f"Tools used: {', '.join(outcome.tools_used[:3])}."
                    ),
                    confidence=0.75,  # Failures are high-confidence learning
                    tags=self._extract_domain_tags(outcome) + ["error"],
                    source_task=task_short,
                ))

        # High iteration count = likely stuck
        if outcome.iterations >= 15:
            insights.append(ExperientialInsight(
                insight_type=TAG_FAILURE,
                content=(
                    f"Got stuck on '{task_short}' ({outcome.iterations} iterations). "
                    f"Consider a different approach next time. "
                    f"Tools tried: {', '.join(set(outcome.tools_used[:5]))}."
                ),
                confidence=0.8,
                tags=self._extract_domain_tags(outcome) + ["stuck"],
                source_task=task_short,
            ))

        # Expensive failure
        if outcome.cost_usd > 0.5:
            insights.append(ExperientialInsight(
                insight_type=TAG_FAILURE,
                content=(
                    f"Expensive failure on '{task_short}': ${outcome.cost_usd:.2f}. "
                    f"Consider using cheaper model tier or breaking into subtasks."
                ),
                confidence=0.7,
                tags=["cost", "optimization"],
                source_task=task_short,
            ))

        return insights

    def _extract_technique_patterns(self, outcome: TaskOutcome) -> list[ExperientialInsight]:
        """Extract reusable technique patterns regardless of outcome."""
        insights = []
        task_short = outcome.task_description[:100]
        desc_lower = outcome.task_description.lower()

        # Detect task categories and link to approaches
        if any(w in desc_lower for w in ["bug", "fix", "error", "debug", "broken"]):
            insights.append(ExperientialInsight(
                insight_type=TAG_TECHNIQUE,
                content=(
                    f"Debugging approach for '{task_short}': "
                    f"Used {', '.join(set(outcome.tools_used[:5]))} "
                    f"over {outcome.iterations} iterations. "
                    f"{'Succeeded' if outcome.success else 'Failed'}."
                ),
                confidence=0.5 + (0.2 if outcome.success else 0.0),
                tags=["debugging"] + self._extract_domain_tags(outcome),
                source_task=task_short,
            ))

        if any(w in desc_lower for w in ["test", "testing", "spec", "coverage"]):
            insights.append(ExperientialInsight(
                insight_type=TAG_TECHNIQUE,
                content=(
                    f"Testing approach for '{task_short}': "
                    f"Files: {', '.join(outcome.files_modified[:3])}. "
                    f"{'Succeeded' if outcome.success else 'Failed'}."
                ),
                confidence=0.5 + (0.2 if outcome.success else 0.0),
                tags=["testing"] + self._extract_domain_tags(outcome),
                source_task=task_short,
            ))

        if any(w in desc_lower for w in ["refactor", "restructure", "cleanup", "reorganize"]):
            insights.append(ExperientialInsight(
                insight_type=TAG_TECHNIQUE,
                content=(
                    f"Refactoring approach for '{task_short}': "
                    f"Modified {len(outcome.files_modified)} files. "
                    f"{'Succeeded' if outcome.success else 'Failed'}."
                ),
                confidence=0.5 + (0.2 if outcome.success else 0.0),
                tags=["refactoring"] + self._extract_domain_tags(outcome),
                source_task=task_short,
            ))

        return insights

    def _extract_context_cues(self, outcome: TaskOutcome) -> list[ExperientialInsight]:
        """Extract signals that indicate which approach to use."""
        insights = []
        task_short = outcome.task_description[:100]

        # If task mentions specific file types, link to successful tools
        if outcome.success:
            file_types = set()
            for f in outcome.files_modified:
                if "." in f:
                    ext = f.rsplit(".", 1)[-1]
                    file_types.add(ext)

            if file_types:
                types_str = ", ".join(sorted(file_types))
                insights.append(ExperientialInsight(
                    insight_type=TAG_CONTEXT_CUE,
                    content=(
                        f"For .{types_str} files: "
                        f"{', '.join(set(outcome.tools_used[:5]))} worked well. "
                        f"Task: '{task_short}'."
                    ),
                    confidence=0.55,
                    tags=["file_type_cue"] + list(file_types),
                    source_task=task_short,
                ))

        return insights

    def _extract_domain_tags(self, outcome: TaskOutcome) -> list[str]:
        """Extract domain tags from task description and files."""
        tags = []
        desc_lower = outcome.task_description.lower()

        domain_keywords = {
            "auth": ["auth", "login", "session", "token", "password"],
            "api": ["api", "endpoint", "route", "rest", "graphql"],
            "database": ["database", "db", "sql", "migration", "schema"],
            "frontend": ["ui", "frontend", "component", "react", "css", "html"],
            "backend": ["server", "backend", "handler", "middleware"],
            "testing": ["test", "spec", "coverage", "mock"],
            "devops": ["deploy", "docker", "ci", "cd", "pipeline", "k8s"],
            "config": ["config", "env", "settings", "yaml", "toml"],
        }

        for domain, keywords in domain_keywords.items():
            if any(kw in desc_lower for kw in keywords):
                tags.append(domain)

        # Add file extension tags
        for f in outcome.files_modified[:5]:
            if "." in f:
                ext = f.rsplit(".", 1)[-1]
                if ext in ("py", "ts", "js", "go", "rs", "java", "rb"):
                    tags.append(ext)

        return tags[:5]  # Cap at 5 tags
