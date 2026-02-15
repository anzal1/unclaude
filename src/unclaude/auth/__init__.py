"""Agent Auth & Security Layer for UnClaude.

Solves the core problem: autonomous agents need security guarantees.
People fear that:
1. Agents might execute harmful commands
2. Agents might exfiltrate sensitive data
3. Agents might make unauthorized changes
4. There's no audit trail of what agents did
5. There's no way to scope agent capabilities

This module provides:
- Capability-based security (agents get scoped tokens)
- Sandbox policies (file/network/exec boundaries)
- Audit logging (every action is recorded)
- Session auth for web dashboard
- Rate limiting
"""

from unclaude.auth.capabilities import (
    Capability,
    CapabilityScope,
    CapabilitySet,
)
from unclaude.auth.policy import (
    SandboxPolicy,
    PolicyEngine,
    PolicyViolation,
)
from unclaude.auth.audit import (
    AuditLog,
    AuditEvent,
    AuditEventType,
)
from unclaude.auth.session import (
    SessionManager,
    Session,
)

__all__ = [
    "Capability",
    "CapabilityScope",
    "CapabilitySet",
    "SandboxPolicy",
    "PolicyEngine",
    "PolicyViolation",
    "AuditLog",
    "AuditEvent",
    "AuditEventType",
    "SessionManager",
    "Session",
]
