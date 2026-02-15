"""Sandbox policy engine for agent execution.

Defines what an agent CAN and CANNOT do at the system level.
This is the enforcement layer - capabilities define WHAT is allowed,
policies define HOW it's enforced.

Key concepts:
- File system boundaries (agent can only touch certain paths)
- Network boundaries (allowlist/denylist of domains)
- Execution boundaries (command filtering, timeout enforcement)
- Resource limits (max file size, max files created, etc.)
"""

from dataclasses import dataclass, field
from enum import Enum
from fnmatch import fnmatch
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from unclaude.auth.capabilities import Capability, CapabilitySet


class PolicyAction(str, Enum):
    """What to do when a policy check fails."""
    DENY = "deny"  # Block the action
    WARN = "warn"  # Allow but log a warning
    ASK = "ask"  # Ask the user
    ALLOW = "allow"  # Allow silently


class PolicyViolation(Exception):
    """Raised when an action violates a sandbox policy."""

    def __init__(self, message: str, capability: Capability | None = None, context: dict[str, Any] | None = None):
        super().__init__(message)
        self.capability = capability
        self.context = context or {}


@dataclass
class SandboxPolicy:
    """Defines the sandbox boundaries for an agent.

    This is the security perimeter. Everything the agent does
    must pass through this policy.
    """

    # File system boundaries
    allowed_paths: list[str] = field(default_factory=list)  # Glob patterns
    denied_paths: list[str] = field(default_factory=lambda: [
        "~/.ssh/*",
        "~/.gnupg/*",
        "~/.aws/*",
        "~/.config/gcloud/*",
        "**/credentials*",
        "**/.env",
        "**/.env.*",
        "**/secret*",
        "**/*.pem",
        "**/*.key",
        "**/id_rsa*",
        "**/id_ed25519*",
    ])

    # Network boundaries
    allowed_domains: list[str] = field(
        default_factory=list)  # Empty = all allowed
    denied_domains: list[str] = field(default_factory=lambda: [
        "*.internal",
        "localhost",
        "127.0.0.1",
        "metadata.google.internal",
        "169.254.169.254",  # AWS metadata service
    ])

    # Execution boundaries
    allowed_commands: list[str] = field(
        default_factory=list)  # Empty = all allowed
    denied_commands: list[str] = field(default_factory=lambda: [
        "rm -rf /*",
        "rm -rf /",
        "mkfs*",
        "dd if=/dev/*",
        ":(){:|:&};:",  # Fork bomb
        "chmod 777 /*",
        "curl * | bash",
        "wget * | bash",
        "sudo *",
        "su *",
    ])

    # Resource limits
    max_file_size_bytes: int = 10 * 1024 * 1024  # 10MB
    max_files_created: int = 100
    max_output_size_bytes: int = 1024 * 1024  # 1MB
    exec_timeout_seconds: int = 120
    max_concurrent_processes: int = 5
    max_memory_entries: int = 10000

    # Behavioral limits
    max_iterations: int = 100
    max_tool_calls_per_turn: int = 20
    max_cost_usd: float = 50.0

    files_created_count: int = 0
    current_concurrent_processes: int = 0

    @classmethod
    def for_profile(cls, profile: str) -> "SandboxPolicy":
        """Create a policy from a named profile.

        Profiles:
        - strict: Very limited. Good for untrusted tasks.
        - standard: Reasonable defaults. Good for development.
        - permissive: Few restrictions. For trusted operators.
        """
        if profile == "strict":
            return cls(
                allowed_commands=["ls*", "cat*", "grep*",
                                  "find*", "echo*", "python*", "node*", "npm*"],
                max_file_size_bytes=1024 * 1024,  # 1MB
                max_files_created=10,
                exec_timeout_seconds=30,
                max_iterations=20,
                max_cost_usd=5.0,
            )
        elif profile == "permissive":
            return cls(
                denied_paths=["~/.ssh/*", "~/.gnupg/*"],  # Minimal denials
                denied_commands=["rm -rf /*", "rm -rf /",
                                 "mkfs*"],  # Minimal denials
                max_file_size_bytes=100 * 1024 * 1024,  # 100MB
                max_files_created=1000,
                exec_timeout_seconds=600,
                max_iterations=200,
                max_cost_usd=200.0,
            )
        else:  # "standard"
            return cls()  # Defaults are standard profile


class PolicyEngine:
    """Evaluates actions against sandbox policies.

    This is the central enforcement point. Every tool execution
    goes through here before being allowed.
    """

    def __init__(
        self,
        capabilities: CapabilitySet,
        policy: SandboxPolicy | None = None,
    ):
        self.capabilities = capabilities
        self.policy = policy or SandboxPolicy()

    def check_file_access(self, path: str, write: bool = False) -> tuple[bool, str]:
        """Check if file access is allowed.

        Args:
            path: The file path to check.
            write: Whether this is a write operation.

        Returns:
            (allowed, reason) tuple.
        """
        # Expand home directory
        expanded = str(Path(path).expanduser().resolve())

        # Check denied paths first (deny takes precedence)
        for pattern in self.policy.denied_paths:
            pattern_expanded = str(Path(pattern).expanduser())
            if fnmatch(expanded, pattern_expanded) or fnmatch(path, pattern):
                return False, f"Path matches denied pattern: {pattern}"

        # Check allowed paths (if specified)
        if self.policy.allowed_paths:
            allowed = False
            for pattern in self.policy.allowed_paths:
                pattern_expanded = str(Path(pattern).expanduser())
                if fnmatch(expanded, pattern_expanded) or fnmatch(path, pattern):
                    allowed = True
                    break
            if not allowed:
                return False, f"Path not in allowed paths"

        # Check capability
        cap = Capability.FILE_WRITE if write else Capability.FILE_READ
        return self.capabilities.check(cap, path=path)

    def check_command(self, command: str) -> tuple[bool, str]:
        """Check if a command execution is allowed.

        Args:
            command: The shell command to check.

        Returns:
            (allowed, reason) tuple.
        """
        # Normalize command
        cmd_lower = command.strip().lower()

        # Check denied commands
        for pattern in self.policy.denied_commands:
            if fnmatch(cmd_lower, pattern.lower()):
                return False, f"Command matches denied pattern: {pattern}"

        # Check allowed commands (if specified)
        if self.policy.allowed_commands:
            allowed = False
            for pattern in self.policy.allowed_commands:
                if fnmatch(cmd_lower, pattern.lower()):
                    allowed = True
                    break
            if not allowed:
                return False, "Command not in allowed commands"

        # Check capability
        return self.capabilities.check(Capability.EXEC_SHELL, command=command)

    def check_network(self, url: str) -> tuple[bool, str]:
        """Check if network access is allowed.

        Args:
            url: The URL to check.

        Returns:
            (allowed, reason) tuple.
        """
        hostname = urlparse(url).hostname or ""

        # Check denied domains
        for pattern in self.policy.denied_domains:
            if fnmatch(hostname, pattern):
                return False, f"Domain matches denied pattern: {pattern}"

        # Check allowed domains (if specified)
        if self.policy.allowed_domains:
            allowed = False
            for pattern in self.policy.allowed_domains:
                if fnmatch(hostname, pattern):
                    allowed = True
                    break
            if not allowed:
                return False, "Domain not in allowed domains"

        # Check capability
        return self.capabilities.check(Capability.NET_FETCH, url=url)

    def check_resource_limits(self, action: str) -> tuple[bool, str]:
        """Check resource limits.

        Args:
            action: The type of resource action ('create_file', 'spawn_process').

        Returns:
            (allowed, reason) tuple.
        """
        if action == "create_file":
            if self.policy.files_created_count >= self.policy.max_files_created:
                return False, f"Max files created ({self.policy.max_files_created}) reached"
            self.policy.files_created_count += 1

        elif action == "spawn_process":
            if self.policy.current_concurrent_processes >= self.policy.max_concurrent_processes:
                return False, f"Max concurrent processes ({self.policy.max_concurrent_processes}) reached"

        return True, "Within limits"

    def enforce(
        self,
        capability: Capability,
        *,
        path: str | None = None,
        command: str | None = None,
        url: str | None = None,
        action: str | None = None,
    ) -> None:
        """Enforce a policy check, raising PolicyViolation on failure.

        This is the main method tools should call.

        Args:
            capability: The capability needed.
            path: File path (for file operations).
            command: Shell command (for exec operations).
            url: URL (for network operations).
            action: Resource action type.

        Raises:
            PolicyViolation: If the action is not allowed.
        """
        # Check capability
        allowed, reason = self.capabilities.use(
            capability, path=path, command=command, url=url
        )
        if not allowed:
            raise PolicyViolation(
                f"Capability denied: {reason}",
                capability=capability,
                context={"path": path, "command": command, "url": url},
            )

        # Check policy-level restrictions
        if path:
            write = capability in (Capability.FILE_WRITE,
                                   Capability.FILE_DELETE)
            allowed, reason = self.check_file_access(path, write=write)
            if not allowed:
                raise PolicyViolation(
                    f"File access denied: {reason}",
                    capability=capability,
                    context={"path": path},
                )

        if command:
            allowed, reason = self.check_command(command)
            if not allowed:
                raise PolicyViolation(
                    f"Command denied: {reason}",
                    capability=capability,
                    context={"command": command},
                )

        if url:
            allowed, reason = self.check_network(url)
            if not allowed:
                raise PolicyViolation(
                    f"Network access denied: {reason}",
                    capability=capability,
                    context={"url": url},
                )

        if action:
            allowed, reason = self.check_resource_limits(action)
            if not allowed:
                raise PolicyViolation(
                    f"Resource limit: {reason}",
                    capability=capability,
                    context={"action": action},
                )
