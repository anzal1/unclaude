"""Smart LLM routing engine.

Inspired by ClawRouter's architecture but adapted for UnClaude:
- Multi-dimension request analysis (complexity, code, reasoning, etc.)
- Cost-optimized model selection
- Provider fallback chains
- Session model pinning
- 100% local routing (no external API calls for routing decisions)

The key insight from ClawRouter: most requests don't need the most
expensive model. By classifying requests and routing them to the
cheapest model that can handle them, we save 70-90% on LLM costs.
"""

from unclaude.routing.router import SmartRouter, RoutingDecision, RoutingProfile
from unclaude.routing.scorer import RequestScorer, RequestTier

__all__ = [
    "SmartRouter",
    "RoutingDecision",
    "RoutingProfile",
    "RequestScorer",
    "RequestTier",
]
