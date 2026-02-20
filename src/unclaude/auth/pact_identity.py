"""Pact Identity Layer — Persistent Cryptographic Identity for UnClaude.

Gives UnClaude a persistent, self-sovereign Ed25519 identity backed by
the Pact protocol. The root keypair lives at ~/.unclaude/identity/ and
survives restarts. Sessions are cryptographic delegations from the root,
not random tokens.

Hierarchy:
    Owner (human, optional — for multi-user setups)
      └── Agent Root (persistent Ed25519, stored on disk)
            └── Session Delegation (ephemeral, scoped capabilities, TTL)
                  └── Subagent Delegation (narrowed from parent session)

This replaces the old SessionManager's in-memory token dict with
cryptographically-backed sessions that:
1. Survive restarts (root key persists)
2. Have verifiable capability chains
3. Support sub-delegation to subagents
4. Can be revoked instantly
5. Leave an unforgeable audit trail
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    BestAvailableEncryption,
)

import pact
from pact import (
    Identity,
    EntityType,
    new_identity,
    new_delegation,
    sub_delegate,
    Delegation,
    DelegationChain,
    verify_chain,
    VerifyOptions,
    MemoryRevocationStore,
    new_revocation,
    Session as PactSession,
    SessionConfig,
    new_session as pact_new_session,
)


# Default capabilities for each profile, as Pact capability URIs
PROFILE_CAPABILITIES: dict[str, list[str]] = {
    "readonly": [
        "file:read",
        "memory:read",
        "context:read",
    ],
    "developer": [
        "file:read",
        "file:write",
        "file:create",
        "shell:execute",
        "memory:read",
        "memory:write",
        "context:read",
        "context:write",
        "network:fetch",
    ],
    "full": [
        "file:*",
        "shell:*",
        "memory:*",
        "context:*",
        "network:*",
        "process:*",
    ],
    "autonomous": [
        "file:*",
        "shell:*",
        "memory:*",
        "context:*",
        "network:*",
        "process:*",
        "daemon:*",
        "task:*",
    ],
    "subagent": [
        "file:read",
        "file:write",
        "shell:execute",
        "memory:read",
    ],
}

# TTLs per session type
SESSION_TTLS: dict[str, timedelta] = {
    "interactive": timedelta(hours=8),
    "autonomous": timedelta(hours=24),
    "subagent": timedelta(hours=1),
    "api": timedelta(days=30),
    "daemon": timedelta(days=7),
}


@dataclass
class PactSessionInfo:
    """Metadata about an active Pact-backed session."""
    session_id: str
    pact_session: PactSession
    name: str = "default"
    session_type: str = "interactive"
    profile: str = "developer"
    project_path: str = ""
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.last_active = time.time()

    @property
    def identity(self) -> Identity:
        return self.pact_session.identity

    @property
    def chain(self) -> DelegationChain:
        return self.pact_session.chain

    @property
    def is_closed(self) -> bool:
        return self.pact_session.is_closed

    def to_dict(self) -> dict[str, Any]:
        chain = self.pact_session.chain
        caps = chain[-1].capabilities if chain else []
        return {
            "session_id": self.session_id,
            "name": self.name,
            "session_type": self.session_type,
            "profile": self.profile,
            "identity_id": self.identity.id,
            "root_id": self.pact_session.root.id,
            "capabilities": caps,
            "created_at": self.created_at,
            "last_active": self.last_active,
            "project_path": self.project_path,
            "chain_depth": len(chain),
        }


class PactIdentityManager:
    """Manages UnClaude's persistent cryptographic identity.

    On first run, generates a root Ed25519 keypair and stores it
    at ~/.unclaude/identity/. All sessions are Pact delegations
    from this root.

    Usage:
        mgr = PactIdentityManager()
        session = mgr.create_session(profile="developer")
        # session.pact_session can sign requests, sub-delegate, etc.

        # Sub-delegate to a subagent (narrowed capabilities)
        sub = mgr.create_subagent_delegation(
            parent_session=session,
            capabilities=["file:read", "shell:execute"],
        )
    """

    def __init__(self, identity_dir: Path | None = None):
        self.identity_dir = identity_dir or (
            Path.home() / ".unclaude" / "identity")
        self.identity_dir.mkdir(parents=True, exist_ok=True)

        # Core state
        self._root: Identity | None = None
        self._owner: Identity | None = None
        self._owner_to_root_delegation: Delegation | None = None
        self._root_chain: DelegationChain = []

        # Active sessions: session_id -> PactSessionInfo
        self._sessions: dict[str, PactSessionInfo] = {}

        # Revocation store
        self._revocations = MemoryRevocationStore()

        # Load or generate root identity
        self._init_root()

    def _init_root(self) -> None:
        """Load or generate the persistent root identity."""
        key_file = self.identity_dir / "root_key.json"
        meta_file = self.identity_dir / "root_meta.json"

        if key_file.exists():
            self._root = self._load_identity(key_file, meta_file)
        else:
            self._root = new_identity(EntityType.AGENT, "unclaude-root")
            self._save_identity(self._root, key_file, meta_file)

        # Create a self-delegation for the root (bootstrap chain)
        # The root delegates all capabilities to itself with max depth
        # so sessions can be sub-delegated from it
        self._owner = new_identity(EntityType.HUMAN, "unclaude-owner")
        self._save_owner_if_needed()

        self._owner_to_root_delegation = new_delegation(
            from_identity=self._owner,
            to_identity=self._root,
            capabilities=["*"],
            ttl=timedelta(days=365),
            max_chain_depth=5,
        )
        self._root_chain = [self._owner_to_root_delegation]

    def _save_owner_if_needed(self) -> None:
        """Save owner identity if it doesn't exist yet."""
        owner_key = self.identity_dir / "owner_key.json"
        owner_meta = self.identity_dir / "owner_meta.json"
        if not owner_key.exists():
            self._save_identity(self._owner, owner_key, owner_meta)
        else:
            self._owner = self._load_identity(owner_key, owner_meta)
            # Re-sign owner->root delegation with loaded owner
            self._owner_to_root_delegation = new_delegation(
                from_identity=self._owner,
                to_identity=self._root,
                capabilities=["*"],
                ttl=timedelta(days=365),
                max_chain_depth=5,
            )
            self._root_chain = [self._owner_to_root_delegation]

    def _save_identity(self, identity: Identity, key_file: Path, meta_file: Path) -> None:
        """Save identity keypair to disk with restricted permissions."""
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        if identity.private_key is None:
            raise ValueError("Cannot save identity without private key")

        # Save private key bytes (raw 32-byte seed)
        raw_private = identity.private_key.private_bytes(
            Encoding.Raw, PrivateFormat.Raw, NoEncryption()
        )
        key_data = {
            "private_key_seed": pact.encode_base64url(raw_private),
            "public_key": identity.public_key,
        }
        key_file.write_text(json.dumps(key_data, indent=2))
        key_file.chmod(0o600)  # Owner-only read/write

        # Save metadata (non-secret)
        meta = {
            "type": identity.type,
            "id": identity.id,
            "name": identity.name,
            "public_key": identity.public_key,
            "created_at": identity.created_at,
        }
        meta_file.write_text(json.dumps(meta, indent=2))

    def _load_identity(self, key_file: Path, meta_file: Path) -> Identity:
        """Load identity from disk."""
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        key_data = json.loads(key_file.read_text())
        meta = json.loads(meta_file.read_text())

        seed = pact.decode_base64url(key_data["private_key_seed"])
        private_key = Ed25519PrivateKey.from_private_bytes(seed)

        return Identity(
            type=meta["type"],
            id=meta["id"],
            public_key=meta["public_key"],
            private_key=private_key,
            name=meta.get("name", ""),
            created_at=meta.get("created_at", ""),
        )

    @property
    def root_identity(self) -> Identity:
        """The persistent root identity."""
        return self._root

    @property
    def root_id(self) -> str:
        """The root identity's ID (sha256:hex)."""
        return self._root.id

    @property
    def owner_identity(self) -> Identity:
        """The owner (human) identity."""
        return self._owner

    def create_session(
        self,
        name: str = "default",
        session_type: str = "interactive",
        profile: str = "developer",
        project_path: str = "",
        ttl: timedelta | None = None,
    ) -> PactSessionInfo:
        """Create a new Pact-backed session.

        The session gets a fresh ephemeral keypair with capabilities
        delegated from the root identity.

        Args:
            name: Human-readable session name
            session_type: interactive/autonomous/subagent/api/daemon
            profile: Capability profile (readonly/developer/full/autonomous/subagent)
            project_path: Project directory for this session
            ttl: Session time-to-live (defaults based on session_type)

        Returns:
            PactSessionInfo with embedded PactSession for signing/delegation
        """
        if ttl is None:
            ttl = SESSION_TTLS.get(session_type, timedelta(hours=8))

        capabilities = PROFILE_CAPABILITIES.get(
            profile, PROFILE_CAPABILITIES["developer"])

        config = SessionConfig(
            ttl=ttl,
            capabilities=capabilities,
            max_chain_depth=3,  # root -> session -> subagent
        )

        pact_session = pact_new_session(
            root=self._root,
            parent_chain=self._root_chain,
            config=config,
        )

        # Short ID from public key hash
        session_id = pact_session.identity.id[:16]

        info = PactSessionInfo(
            session_id=session_id,
            pact_session=pact_session,
            name=name,
            session_type=session_type,
            profile=profile,
            project_path=project_path,
        )

        self._sessions[session_id] = info
        return info

    def create_subagent_delegation(
        self,
        parent_session: PactSessionInfo,
        capabilities: list[str] | None = None,
        ttl: timedelta | None = None,
    ) -> PactSessionInfo:
        """Create a narrowed delegation for a subagent.

        The subagent gets capabilities that are a strict subset of
        the parent session's capabilities.

        Args:
            parent_session: The parent session to delegate from
            capabilities: Capabilities to grant (must be subset of parent)
            ttl: Time-to-live (capped at parent's remaining TTL)

        Returns:
            PactSessionInfo for the subagent
        """
        if capabilities is None:
            capabilities = PROFILE_CAPABILITIES["subagent"]

        if ttl is None:
            ttl = SESSION_TTLS["subagent"]

        # Create a new identity for the subagent
        subagent_identity = new_identity(EntityType.AGENT, "unclaude-subagent")

        # Sub-delegate from the parent session
        delegation, new_chain = parent_session.pact_session.sub_delegate(
            to=subagent_identity,
            capabilities=capabilities,
            ttl=ttl,
        )

        # Build a PactSession-like wrapper for the subagent
        sub_pact_session = PactSession(
            root=subagent_identity,
            parent_chain=new_chain[:-1],
            session_identity=subagent_identity,
            root_to_session=delegation,
        )

        session_id = subagent_identity.id[:16]

        info = PactSessionInfo(
            session_id=session_id,
            pact_session=sub_pact_session,
            name=f"subagent-{session_id[:8]}",
            session_type="subagent",
            profile="subagent",
            project_path=parent_session.project_path,
            metadata={"parent_session": parent_session.session_id},
        )

        self._sessions[session_id] = info
        return info

    def get_session(self, session_id: str) -> PactSessionInfo | None:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    def end_session(self, session_id: str | "PactSessionInfo") -> None:
        """End a session, zeroizing its keys."""
        if isinstance(session_id, PactSessionInfo):
            session_id = session_id.session_id
        info = self._sessions.pop(session_id, None)
        if info and not info.is_closed:
            info.pact_session.close()

    def verify_session_chain(self, session: PactSessionInfo) -> bool:
        """Verify the delegation chain for a session is valid."""
        chain = session.pact_session.chain
        if not chain:
            return False

        opts = VerifyOptions()
        opts.revocation_checker = self._revocations.is_revoked
        result = verify_chain(chain, opts)
        return result.valid

    def revoke_session(self, session_id: str | "PactSessionInfo", reason: str = "manual") -> bool:
        """Revoke a session's delegation, making it permanently invalid."""
        if isinstance(session_id, PactSessionInfo):
            session_id = session_id.session_id
        info = self._sessions.get(session_id)
        if not info:
            return False

        chain = info.pact_session.chain
        if chain:
            # Revoke the last delegation in the chain
            last = chain[-1]
            revocation = new_revocation(
                delegation_id=last.id,
                revoker=self._root,
                reason=reason,
            )
            self._revocations.revoke(revocation)

        self.end_session(session_id)
        return True

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all active sessions."""
        self._cleanup_expired()
        return [info.to_dict() for info in self._sessions.values()]

    def _cleanup_expired(self) -> None:
        """Remove sessions whose delegation chains have expired."""
        to_remove = []
        for sid, info in self._sessions.items():
            if info.is_closed:
                to_remove.append(sid)
                continue
            # Check if the chain's expiry has passed
            chain = info.pact_session.chain
            if chain:
                from datetime import datetime, timezone
                last = chain[-1]
                try:
                    expires = datetime.fromisoformat(last.constraints.expires)
                    if expires.tzinfo is None:
                        expires = expires.replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) > expires:
                        to_remove.append(sid)
                except (ValueError, AttributeError):
                    pass

        for sid in to_remove:
            self.end_session(sid)

    def export_identity_card(self) -> dict[str, Any]:
        """Export the public identity card (shareable, no secrets)."""
        return {
            "protocol": "pact",
            "version": "1.0",
            "agent": {
                "type": self._root.type,
                "id": self._root.id,
                "name": self._root.name,
                "public_key": self._root.public_key,
            },
            "owner": {
                "type": self._owner.type,
                "id": self._owner.id,
                "public_key": self._owner.public_key,
            },
        }

    def session_count(self) -> int:
        """Number of active sessions."""
        return len(self._sessions)
