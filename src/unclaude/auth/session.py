"""Session management for agent authentication.

Handles:
- Web dashboard authentication (token-based)
- Agent session lifecycle
- Session-scoped capabilities
- CORS and origin validation
"""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from unclaude.auth.capabilities import CapabilitySet
from unclaude.auth.policy import SandboxPolicy
from unclaude.auth.audit import AuditLog, AuditEvent, AuditEventType


@dataclass
class Session:
    """An authenticated session.

    Each session has:
    - A unique token (used for API auth)
    - A capability set (what it can do)
    - A sandbox policy (boundaries)
    - Audit logging enabled by default
    """

    session_id: str = field(default_factory=lambda: secrets.token_urlsafe(16))
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    token_hash: str = ""  # SHA-256 of token, stored instead of plaintext

    # Identity
    name: str = "default"
    session_type: str = "interactive"  # interactive, autonomous, subagent, api

    # Security
    capabilities: CapabilitySet = field(
        default_factory=lambda: CapabilitySet("developer"))
    policy: SandboxPolicy = field(default_factory=SandboxPolicy)

    # Lifecycle
    created_at: float = field(default_factory=time.time)
    expires_at: float | None = None  # None = no expiry
    last_active: float = field(default_factory=time.time)

    # Metadata
    project_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.token_hash:
            self.token_hash = hashlib.sha256(self.token.encode()).hexdigest()

    def is_expired(self) -> bool:
        """Check if session has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def is_active(self, idle_timeout: int = 3600) -> bool:
        """Check if session is still active (not idle too long)."""
        return (time.time() - self.last_active) < idle_timeout

    def touch(self) -> None:
        """Update last active timestamp."""
        self.last_active = time.time()

    def to_dict(self) -> dict[str, Any]:
        """Serialize session metadata (no secrets)."""
        return {
            "session_id": self.session_id,
            "name": self.name,
            "session_type": self.session_type,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "project_path": self.project_path,
            "capabilities": list(self.capabilities.get_grants().keys()),
        }


class SessionManager:
    """Manages authenticated sessions.

    Provides:
    - Session creation with capability profiles
    - Token-based authentication
    - Session lifecycle management
    - API key management for web dashboard
    """

    def __init__(self, config_dir: Path | None = None):
        self.config_dir = config_dir or (Path.home() / ".unclaude")
        self._sessions: dict[str, Session] = {}  # token_hash -> session
        self._api_keys: dict[str, dict[str, Any]] = {}  # key_hash -> metadata
        self.audit = AuditLog()
        self._load_api_keys()

    def _load_api_keys(self) -> None:
        """Load API keys from config."""
        key_file = self.config_dir / "api_keys.yaml"
        if key_file.exists():
            with open(key_file) as f:
                data = yaml.safe_load(f) or {}
                self._api_keys = data.get("keys", {})

    def _save_api_keys(self) -> None:
        """Save API keys to config."""
        key_file = self.config_dir / "api_keys.yaml"
        key_file.parent.mkdir(parents=True, exist_ok=True)

        with open(key_file, "w") as f:
            yaml.dump({"keys": self._api_keys}, f)

        # Restrict permissions (secrets file)
        key_file.chmod(0o600)

    def create_session(
        self,
        name: str = "default",
        session_type: str = "interactive",
        profile: str = "developer",
        policy_profile: str = "standard",
        project_path: str = "",
        ttl_seconds: int | None = None,
    ) -> Session:
        """Create a new authenticated session.

        Args:
            name: Human-readable session name.
            session_type: Type of session (interactive, autonomous, subagent, api).
            profile: Capability profile (readonly, developer, full, autonomous, subagent).
            policy_profile: Sandbox policy profile (strict, standard, permissive).
            project_path: Project directory for this session.
            ttl_seconds: Session time-to-live in seconds.

        Returns:
            New Session object with token.
        """
        session = Session(
            name=name,
            session_type=session_type,
            capabilities=CapabilitySet(profile),
            policy=SandboxPolicy.for_profile(policy_profile),
            project_path=project_path,
            expires_at=time.time() + ttl_seconds if ttl_seconds else None,
        )

        self._sessions[session.token_hash] = session

        # Audit
        self.audit.log(AuditEvent(
            event_type=AuditEventType.SESSION_START,
            session_id=session.session_id,
            data={
                "name": name,
                "session_type": session_type,
                "profile": profile,
                "policy_profile": policy_profile,
            },
        ))

        return session

    def authenticate(self, token: str) -> Session | None:
        """Authenticate by token.

        Args:
            token: The session token.

        Returns:
            Session if valid, None if not.
        """
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        session = self._sessions.get(token_hash)

        if not session:
            return None

        if session.is_expired():
            self.end_session(session.session_id)
            return None

        session.touch()
        return session

    def authenticate_api_key(self, api_key: str) -> Session | None:
        """Authenticate with an API key (for web dashboard / external access).

        API keys are longer-lived than session tokens and can create sessions.

        Args:
            api_key: The API key.

        Returns:
            A new Session bound to this API key, or None.
        """
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_meta = self._api_keys.get(key_hash)

        if not key_meta:
            return None

        # Create a session for this API key
        return self.create_session(
            name=key_meta.get("name", "api"),
            session_type="api",
            profile=key_meta.get("profile", "developer"),
            policy_profile=key_meta.get("policy", "standard"),
        )

    def create_api_key(
        self,
        name: str,
        profile: str = "developer",
        policy: str = "standard",
    ) -> str:
        """Create a new API key for external access.

        Args:
            name: Human-readable name for the key.
            profile: Capability profile for sessions created with this key.
            policy: Sandbox policy for sessions created with this key.

        Returns:
            The API key (show once, then store hash only).
        """
        api_key = f"uc_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()

        self._api_keys[key_hash] = {
            "name": name,
            "profile": profile,
            "policy": policy,
            "created_at": time.time(),
        }

        self._save_api_keys()
        return api_key

    def revoke_api_key(self, key_hash: str) -> bool:
        """Revoke an API key by its hash."""
        if key_hash in self._api_keys:
            del self._api_keys[key_hash]
            self._save_api_keys()
            return True
        return False

    def get_session(self, session_id: str) -> Session | None:
        """Get a session by ID."""
        for session in self._sessions.values():
            if session.session_id == session_id:
                return session
        return None

    def end_session(self, session_id: str) -> None:
        """End a session."""
        to_remove = None
        for token_hash, session in self._sessions.items():
            if session.session_id == session_id:
                to_remove = token_hash
                self.audit.log(AuditEvent(
                    event_type=AuditEventType.SESSION_END,
                    session_id=session_id,
                ))
                break

        if to_remove:
            del self._sessions[to_remove]

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all active sessions."""
        # Clean expired sessions first
        expired = [
            h for h, s in self._sessions.items()
            if s.is_expired()
        ]
        for h in expired:
            self.end_session(self._sessions[h].session_id)

        return [s.to_dict() for s in self._sessions.values()]

    def cleanup(self, idle_timeout: int = 3600) -> int:
        """Clean up expired and idle sessions.

        Args:
            idle_timeout: Seconds of inactivity before a session is cleaned up.

        Returns:
            Number of sessions cleaned up.
        """
        to_remove = []
        for token_hash, session in self._sessions.items():
            if session.is_expired() or not session.is_active(idle_timeout):
                to_remove.append(token_hash)

        for h in to_remove:
            session = self._sessions[h]
            self.audit.log(AuditEvent(
                event_type=AuditEventType.SESSION_END,
                session_id=session.session_id,
                data={"reason": "cleanup"},
            ))
            del self._sessions[h]

        # Flush audit log
        self.audit.flush()

        return len(to_remove)
