"""Capability-based security for agents.

Instead of asking "is this user authorized?", we ask
"does this agent have the capability to do X?"

Capabilities are:
- Fine-grained (read file vs write file vs execute command)
- Scopeable (only in /src/**, only *.py files)
- Composable (combine into capability sets)
- Revocable (remove at runtime)
- Auditable (every capability use is logged)

This is the key innovation: agents don't get blanket access.
They get a specific set of capabilities, and every action
is checked against those capabilities.
"""

import hashlib
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any


class Capability(str, Enum):
    """Individual capabilities an agent can have."""

    # File system
    FILE_READ = "file:read"
    FILE_WRITE = "file:write"
    FILE_DELETE = "file:delete"
    FILE_GLOB = "file:glob"
    FILE_GREP = "file:grep"
    DIR_LIST = "dir:list"
    DIR_CREATE = "dir:create"

    # Execution
    EXEC_SAFE = "exec:safe"  # Commands from whitelist only
    EXEC_SHELL = "exec:shell"  # Any shell command (dangerous)
    EXEC_BACKGROUND = "exec:background"  # Background processes

    # Network
    NET_FETCH = "net:fetch"  # HTTP GET
    NET_POST = "net:post"  # HTTP POST/PUT
    NET_SEARCH = "net:search"  # Web search
    NET_WEBSOCKET = "net:websocket"  # WebSocket connections

    # Git
    GIT_READ = "git:read"  # status, diff, log
    GIT_WRITE = "git:write"  # add, commit
    GIT_PUSH = "git:push"  # push (most dangerous git op)
    GIT_BRANCH = "git:branch"  # branch, checkout

    # Memory
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    MEMORY_DELETE = "memory:delete"

    # Agent
    AGENT_SPAWN = "agent:spawn"  # Spawn sub-agents
    AGENT_BACKGROUND = "agent:background"  # Background jobs

    # MCP
    MCP_CONNECT = "mcp:connect"
    MCP_EXECUTE = "mcp:execute"

    # Browser
    BROWSER_NAVIGATE = "browser:navigate"
    BROWSER_INTERACT = "browser:interact"
    BROWSER_SCREENSHOT = "browser:screenshot"

    # System
    SYSTEM_CONFIG = "system:config"  # Read/modify config


@dataclass
class CapabilityScope:
    """Scoping rules for a capability.

    Examples:
        - FILE_READ scoped to paths=["/src/**"] means only read files under /src/
        - EXEC_SHELL scoped to commands=["npm *", "python *"] means only npm/python
        - NET_FETCH scoped to domains=["api.github.com"] means only GitHub API
    """

    # File path patterns (glob-style)
    paths: list[str] = field(default_factory=list)

    # Command patterns (glob-style)
    commands: list[str] = field(default_factory=list)

    # Domain patterns
    domains: list[str] = field(default_factory=list)

    # Time-based: capability expires after this many seconds
    ttl_seconds: int | None = None
    created_at: float = field(default_factory=time.time)

    # Max invocations allowed (-1 = unlimited)
    max_invocations: int = -1
    invocation_count: int = 0

    # Rate limit: max N calls per M seconds
    rate_limit_count: int = -1  # -1 = no limit
    rate_limit_window: int = 60  # seconds
    _rate_limit_calls: list[float] = field(default_factory=list)

    def is_expired(self) -> bool:
        """Check if this scope has expired."""
        if self.ttl_seconds is None:
            return False
        return (time.time() - self.created_at) > self.ttl_seconds

    def is_exhausted(self) -> bool:
        """Check if max invocations have been used."""
        if self.max_invocations == -1:
            return False
        return self.invocation_count >= self.max_invocations

    def is_rate_limited(self) -> bool:
        """Check if rate limit is exceeded."""
        if self.rate_limit_count == -1:
            return False  # No limit
        now = time.time()
        # Clean old entries
        self._rate_limit_calls = [
            t for t in self._rate_limit_calls
            if now - t < self.rate_limit_window
        ]
        return len(self._rate_limit_calls) >= self.rate_limit_count

    def record_invocation(self) -> None:
        """Record that this capability was invoked."""
        self.invocation_count += 1
        self._rate_limit_calls.append(time.time())

    def matches_path(self, path: str) -> bool:
        """Check if a path matches the scope's path patterns."""
        if not self.paths:
            return True  # No path restriction

        from fnmatch import fnmatch
        return any(fnmatch(path, pattern) for pattern in self.paths)

    def matches_command(self, command: str) -> bool:
        """Check if a command matches the scope's command patterns."""
        if not self.commands:
            return True  # No command restriction

        from fnmatch import fnmatch
        return any(fnmatch(command, pattern) for pattern in self.commands)

    def matches_domain(self, url: str) -> bool:
        """Check if a URL's domain matches the scope's domain patterns."""
        if not self.domains:
            return True  # No domain restriction

        from urllib.parse import urlparse
        from fnmatch import fnmatch
        hostname = urlparse(url).hostname or ""
        return any(fnmatch(hostname, pattern) for pattern in self.domains)


@dataclass
class CapabilityGrant:
    """A specific grant of a capability with its scope."""

    capability: Capability
    scope: CapabilityScope = field(default_factory=CapabilityScope)
    granted_by: str = "system"  # Who/what granted this
    reason: str = ""  # Why it was granted


class CapabilitySet:
    """A set of capabilities assigned to an agent session.

    This is the primary security boundary. An agent can only
    do what its CapabilitySet allows.
    """

    # Pre-defined capability profiles
    PROFILES: dict[str, list[Capability]] = {
        "readonly": [
            Capability.FILE_READ,
            Capability.FILE_GLOB,
            Capability.FILE_GREP,
            Capability.DIR_LIST,
            Capability.GIT_READ,
            Capability.MEMORY_READ,
        ],
        "developer": [
            Capability.FILE_READ,
            Capability.FILE_WRITE,
            Capability.FILE_GLOB,
            Capability.FILE_GREP,
            Capability.DIR_LIST,
            Capability.DIR_CREATE,
            Capability.EXEC_SAFE,
            Capability.GIT_READ,
            Capability.GIT_WRITE,
            Capability.GIT_BRANCH,
            Capability.NET_FETCH,
            Capability.NET_SEARCH,
            Capability.MEMORY_READ,
            Capability.MEMORY_WRITE,
        ],
        "full": [cap for cap in Capability],  # Everything
        "autonomous": [
            # For Ralph Wiggum / autonomous mode
            Capability.FILE_READ,
            Capability.FILE_WRITE,
            Capability.FILE_DELETE,
            Capability.FILE_GLOB,
            Capability.FILE_GREP,
            Capability.DIR_LIST,
            Capability.DIR_CREATE,
            Capability.EXEC_SHELL,
            Capability.EXEC_BACKGROUND,
            Capability.GIT_READ,
            Capability.GIT_WRITE,
            Capability.GIT_BRANCH,
            Capability.NET_FETCH,
            Capability.NET_SEARCH,
            Capability.MEMORY_READ,
            Capability.MEMORY_WRITE,
            Capability.AGENT_SPAWN,
        ],
        "subagent": [
            # Limited set for sub-agents
            Capability.FILE_READ,
            Capability.FILE_GLOB,
            Capability.FILE_GREP,
            Capability.DIR_LIST,
            Capability.EXEC_SAFE,
            Capability.MEMORY_READ,
        ],
    }

    def __init__(self, profile: str = "developer"):
        """Initialize with a capability profile.

        Args:
            profile: One of 'readonly', 'developer', 'full', 'autonomous', 'subagent'
        """
        self.token = secrets.token_urlsafe(32)
        self.token_hash = hashlib.sha256(self.token.encode()).hexdigest()
        self.created_at = time.time()
        self._grants: dict[Capability, CapabilityGrant] = {}

        # Load profile
        if profile in self.PROFILES:
            for cap in self.PROFILES[profile]:
                self.grant(cap, reason=f"Profile: {profile}")

    def grant(
        self,
        capability: Capability,
        scope: CapabilityScope | None = None,
        granted_by: str = "system",
        reason: str = "",
    ) -> None:
        """Grant a capability to this set.

        Args:
            capability: The capability to grant.
            scope: Optional scoping rules.
            granted_by: Who/what is granting this capability.
            reason: Why it's being granted.
        """
        self._grants[capability] = CapabilityGrant(
            capability=capability,
            scope=scope or CapabilityScope(),
            granted_by=granted_by,
            reason=reason,
        )

    def revoke(self, capability: Capability) -> None:
        """Revoke a capability from this set."""
        self._grants.pop(capability, None)

    def has(self, capability: Capability) -> bool:
        """Check if this set has a capability (ignoring scope)."""
        return capability in self._grants

    def check(
        self,
        capability: Capability,
        *,
        path: str | None = None,
        command: str | None = None,
        url: str | None = None,
    ) -> tuple[bool, str]:
        """Check if an action is allowed.

        Args:
            capability: The capability needed.
            path: File path for file operations.
            command: Shell command for exec operations.
            url: URL for network operations.

        Returns:
            (allowed, reason) tuple.
        """
        grant = self._grants.get(capability)
        if not grant:
            return False, f"Capability {capability.value} not granted"

        scope = grant.scope

        # Time expiry
        if scope.is_expired():
            self.revoke(capability)
            return False, f"Capability {capability.value} has expired"

        # Invocation count
        if scope.is_exhausted():
            return False, f"Capability {capability.value} max invocations reached"

        # Rate limit
        if scope.is_rate_limited():
            return False, f"Capability {capability.value} rate limit exceeded"

        # Path scope
        if path and not scope.matches_path(path):
            return False, f"Path {path} not allowed for {capability.value}"

        # Command scope
        if command and not scope.matches_command(command):
            return False, f"Command not allowed for {capability.value}"

        # Domain scope
        if url and not scope.matches_domain(url):
            return False, f"Domain not allowed for {capability.value}"

        return True, "Allowed"

    def use(
        self,
        capability: Capability,
        *,
        path: str | None = None,
        command: str | None = None,
        url: str | None = None,
    ) -> tuple[bool, str]:
        """Check and record a capability use.

        Like check(), but also records the invocation if allowed.

        Returns:
            (allowed, reason) tuple.
        """
        allowed, reason = self.check(
            capability, path=path, command=command, url=url
        )
        if allowed:
            self._grants[capability].scope.record_invocation()
        return allowed, reason

    def get_grants(self) -> dict[str, dict[str, Any]]:
        """Get a summary of all grants for introspection."""
        return {
            cap.value: {
                "granted_by": grant.granted_by,
                "reason": grant.reason,
                "paths": grant.scope.paths,
                "commands": grant.scope.commands,
                "domains": grant.scope.domains,
                "ttl": grant.scope.ttl_seconds,
                "invocations": f"{grant.scope.invocation_count}/{grant.scope.max_invocations}",
            }
            for cap, grant in self._grants.items()
        }

    @classmethod
    def for_tool(cls, tool_name: str) -> list[Capability]:
        """Map a tool name to the capabilities it requires.

        This is the bridge between the tool system and the auth system.
        """
        TOOL_CAPABILITY_MAP: dict[str, list[Capability]] = {
            "file_read": [Capability.FILE_READ],
            "file_write": [Capability.FILE_WRITE],
            "file_edit": [Capability.FILE_WRITE],
            "file_glob": [Capability.FILE_GLOB],
            "file_grep": [Capability.FILE_GREP],
            "directory_list": [Capability.DIR_LIST],
            "bash_execute": [Capability.EXEC_SHELL],
            "web_fetch": [Capability.NET_FETCH],
            "web_search": [Capability.NET_SEARCH],
            "git": [Capability.GIT_READ],  # Base; specific ops may need more
            "memory_search": [Capability.MEMORY_READ],
            "memory_save": [Capability.MEMORY_WRITE],
            "browser_tool": [Capability.BROWSER_NAVIGATE],
            "spawn_subagent": [Capability.AGENT_SPAWN],
        }
        return TOOL_CAPABILITY_MAP.get(tool_name, [])
