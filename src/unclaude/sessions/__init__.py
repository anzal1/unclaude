"""Session management for conversation persistence and recovery.

Inspired by OpenClaw's session architecture:
- Session keys: agent:id:session format for namespacing
- JSONL persistence: append-only, crash-resistant
- Session recovery on restart
- Conversation continuity across agent restarts

This replaces the naive "new AgentLoop per message" pattern
with proper session lifecycle management.
"""

from unclaude.sessions.manager import (
    SessionStore,
    ConversationSession,
    SessionKey,
)

__all__ = [
    "SessionStore",
    "ConversationSession",
    "SessionKey",
]
