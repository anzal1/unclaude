"""Agent module for UnClaude.

Provides both the original AgentLoop and the enhanced EnhancedAgentLoop
with capability-based security, smart routing, and hierarchical memory.
"""

from unclaude.agent.loop import AgentLoop
from unclaude.agent.enhanced_loop import EnhancedAgentLoop
from unclaude.agent.ralph_wiggum import RalphWiggumMode, RalphWiggumResult

__all__ = ["AgentLoop", "EnhancedAgentLoop", "RalphWiggumMode", "RalphWiggumResult"]
