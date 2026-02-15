"""Advanced context management for agents.

Inspired by OpenClaw's context architecture:
1. Bootstrap files: SOUL.md, TOOLS.md, AGENTS.md, IDENTITY.md
2. Context pruning: Trim tool results to manage context window
3. Context compaction: Summarize old messages when context grows too large
4. On-demand loading: Only load what's needed per session
"""

from unclaude.context_engine.bootstrap import BootstrapLoader
from unclaude.context_engine.pruning import ContextPruner
from unclaude.context_engine.compaction import ContextCompactor

__all__ = [
    "BootstrapLoader",
    "ContextPruner",
    "ContextCompactor",
]
