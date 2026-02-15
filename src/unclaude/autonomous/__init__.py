"""Autonomous agent module for UnClaude.

Provides the infrastructure for running 24/7 autonomous agents:
- Daemon: Long-running agent process with task queue
- Swarm: Multi-agent coordination for complex tasks
- Discovery: Auto-detect project capabilities and skills
- Intake: Accept tasks from files, webhooks, git hooks
"""

from unclaude.autonomous.daemon import AgentDaemon, DaemonStatus
from unclaude.autonomous.swarm import SwarmOrchestrator, SwarmTask, SwarmResult
from unclaude.autonomous.discovery import SkillDiscovery, ProjectProfile
from unclaude.autonomous.intake import TaskIntake, IntakeSource

__all__ = [
    "AgentDaemon",
    "DaemonStatus",
    "SwarmOrchestrator",
    "SwarmTask",
    "SwarmResult",
    "SkillDiscovery",
    "ProjectProfile",
    "TaskIntake",
    "IntakeSource",
]
