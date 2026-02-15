"""JSONL-based session store for conversation persistence.

Design decisions (from OpenClaw learnings):
1. JSONL format: Each line is a JSON message. Append-only, crash-safe.
   If process dies mid-write, we lose at most one message, not the whole file.

2. Session keys: Format is "agent:{agent_id}:{session_id}".
   This namespaces sessions by agent, allowing multi-agent setups.

3. Compaction: When a session file gets too large, we compact it by
   summarizing older messages and keeping recent ones.

4. Recovery: On startup, we scan the sessions directory and rebuild
   the session index from JSONL files.
"""

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator


@dataclass
class SessionKey:
    """Structured session key with agent namespacing.

    Format: agent:{agent_id}:{session_id}
    """
    agent_id: str = "main"
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    @classmethod
    def parse(cls, key: str) -> "SessionKey":
        """Parse a session key string.

        Supports:
        - "agent:main:abc123" -> full format
        - "abc123" -> shorthand, defaults agent_id to "main"
        """
        parts = key.split(":")
        if len(parts) == 3 and parts[0] == "agent":
            return cls(agent_id=parts[1], session_id=parts[2])
        return cls(agent_id="main", session_id=key)

    def __str__(self) -> str:
        return f"agent:{self.agent_id}:{self.session_id}"

    @property
    def filename(self) -> str:
        """Get the JSONL filename for this session."""
        return f"{self.agent_id}_{self.session_id}.jsonl"


@dataclass
class SessionMessage:
    """A message in a session."""
    role: str
    content: str | None = None
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    name: str | None = None
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        d: dict[str, Any] = {"role": self.role, "timestamp": self.timestamp}
        if self.content is not None:
            d["content"] = self.content
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.name:
            d["name"] = self.name
        if self.metadata:
            d["metadata"] = self.metadata
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SessionMessage":
        return cls(
            role=d["role"],
            content=d.get("content"),
            tool_calls=d.get("tool_calls"),
            tool_call_id=d.get("tool_call_id"),
            name=d.get("name"),
            timestamp=d.get("timestamp", time.time()),
            metadata=d.get("metadata", {}),
        )

    def to_llm_message(self) -> dict[str, Any]:
        """Convert to LLM-compatible message format."""
        msg: dict[str, Any] = {"role": self.role}
        if self.content is not None:
            msg["content"] = self.content
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.name:
            msg["name"] = self.name
        return msg


@dataclass
class ConversationSession:
    """A conversation session with its message history."""

    key: SessionKey
    project_path: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    messages: list[SessionMessage] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Compaction state
    compaction_summary: str | None = None
    compacted_count: int = 0  # Messages that were compacted

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def is_empty(self) -> bool:
        return len(self.messages) == 0

    def get_llm_messages(self) -> list[dict[str, Any]]:
        """Get messages in LLM-compatible format.

        If compaction has occurred, injects the compaction summary
        as a system message before the remaining messages.
        """
        messages = []

        # Inject compaction summary if present
        if self.compaction_summary:
            messages.append({
                "role": "system",
                "content": f"[CONVERSATION HISTORY SUMMARY]\n{self.compaction_summary}\n[END SUMMARY - Recent messages follow]",
            })

        for msg in self.messages:
            messages.append(msg.to_llm_message())

        return messages


class SessionStore:
    """JSONL-based session store.

    Sessions are persisted as JSONL files in the sessions directory.
    Each file is named {agent_id}_{session_id}.jsonl and contains
    one JSON object per line representing a message.

    File format:
    - Line 1: Session metadata ({"_type": "session_meta", ...})
    - Line 2+: Messages ({"role": "...", "content": "...", ...})
    """

    def __init__(self, sessions_dir: Path | None = None):
        self.sessions_dir = sessions_dir or (
            Path.home() / ".unclaude" / "sessions")
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, ConversationSession] = {}

    def _get_session_path(self, key: SessionKey) -> Path:
        """Get the JSONL file path for a session."""
        return self.sessions_dir / key.filename

    def create(
        self,
        agent_id: str = "main",
        session_id: str | None = None,
        project_path: str = "",
    ) -> ConversationSession:
        """Create a new session.

        Args:
            agent_id: Agent identifier.
            session_id: Custom session ID (auto-generated if None).
            project_path: Project directory path.

        Returns:
            New ConversationSession.
        """
        key = SessionKey(
            agent_id=agent_id,
            session_id=session_id or str(uuid.uuid4())[:8],
        )

        session = ConversationSession(
            key=key,
            project_path=project_path,
        )

        # Write session metadata to JSONL
        path = self._get_session_path(key)
        meta = {
            "_type": "session_meta",
            "key": str(key),
            "project_path": project_path,
            "created_at": session.created_at,
        }
        with open(path, "w") as f:
            f.write(json.dumps(meta) + "\n")

        self._sessions[str(key)] = session
        return session

    def append(self, key: SessionKey | str, message: SessionMessage) -> None:
        """Append a message to a session.

        This is crash-safe: we append a single line to the JSONL file.
        If the process crashes, we lose at most this one message.

        Args:
            key: Session key.
            message: Message to append.
        """
        if isinstance(key, str):
            key = SessionKey.parse(key)

        path = self._get_session_path(key)

        # Append to JSONL
        with open(path, "a") as f:
            f.write(json.dumps(message.to_dict()) + "\n")

        # Update in-memory cache
        session = self._sessions.get(str(key))
        if session:
            session.messages.append(message)
            session.updated_at = time.time()

    def load(self, key: SessionKey | str) -> ConversationSession | None:
        """Load a session from its JSONL file.

        Args:
            key: Session key.

        Returns:
            ConversationSession or None if not found.
        """
        if isinstance(key, str):
            key = SessionKey.parse(key)

        # Check cache
        cached = self._sessions.get(str(key))
        if cached:
            return cached

        path = self._get_session_path(key)
        if not path.exists():
            return None

        session = ConversationSession(key=key)
        messages: list[SessionMessage] = []

        with open(path) as f:
            for line_num, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue  # Skip corrupted lines

                if data.get("_type") == "session_meta":
                    session.project_path = data.get("project_path", "")
                    session.created_at = data.get("created_at", time.time())
                elif data.get("_type") == "compaction":
                    session.compaction_summary = data.get("summary", "")
                    session.compacted_count = data.get("compacted_count", 0)
                else:
                    messages.append(SessionMessage.from_dict(data))

        session.messages = messages
        session.updated_at = time.time()

        self._sessions[str(key)] = session
        return session

    def list_sessions(
        self,
        agent_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List available sessions.

        Args:
            agent_id: Filter by agent ID.
            limit: Max results.

        Returns:
            List of session summaries.
        """
        results = []

        for path in sorted(
            self.sessions_dir.glob("*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            if len(results) >= limit:
                break

            # Parse filename
            stem = path.stem  # agent_id_session_id
            parts = stem.split("_", 1)
            if len(parts) != 2:
                continue

            file_agent_id, session_id = parts
            if agent_id and file_agent_id != agent_id:
                continue

            # Read first line for metadata
            try:
                with open(path) as f:
                    first_line = f.readline().strip()
                    meta = json.loads(first_line) if first_line else {}

                    # Count messages
                    msg_count = sum(1 for _ in f)
            except (json.JSONDecodeError, OSError):
                continue

            results.append({
                "key": f"agent:{file_agent_id}:{session_id}",
                "agent_id": file_agent_id,
                "session_id": session_id,
                "project_path": meta.get("project_path", ""),
                "created_at": meta.get("created_at", path.stat().st_ctime),
                "updated_at": path.stat().st_mtime,
                "message_count": msg_count,
            })

        return results

    def compact(
        self,
        key: SessionKey | str,
        summary: str,
        keep_recent: int = 20,
    ) -> None:
        """Compact a session by replacing old messages with a summary.

        This is the key to managing context window size.
        Old messages are replaced with a summary, keeping only
        the most recent messages.

        Args:
            key: Session key.
            summary: LLM-generated summary of the compacted messages.
            keep_recent: Number of recent messages to keep.
        """
        if isinstance(key, str):
            key = SessionKey.parse(key)

        session = self.load(key)
        if not session or len(session.messages) <= keep_recent:
            return

        # Messages to compact vs keep
        compact_count = len(session.messages) - keep_recent
        recent_messages = session.messages[-keep_recent:]

        # Rewrite the JSONL file
        path = self._get_session_path(key)
        with open(path, "w") as f:
            # Session metadata
            meta = {
                "_type": "session_meta",
                "key": str(key),
                "project_path": session.project_path,
                "created_at": session.created_at,
            }
            f.write(json.dumps(meta) + "\n")

            # Compaction record
            compaction = {
                "_type": "compaction",
                "summary": summary,
                "compacted_count": session.compacted_count + compact_count,
                "timestamp": time.time(),
            }
            f.write(json.dumps(compaction) + "\n")

            # Recent messages
            for msg in recent_messages:
                f.write(json.dumps(msg.to_dict()) + "\n")

        # Update in-memory state
        session.compaction_summary = summary
        session.compacted_count += compact_count
        session.messages = recent_messages

    def delete(self, key: SessionKey | str) -> bool:
        """Delete a session and its JSONL file.

        Args:
            key: Session key.

        Returns:
            True if deleted, False if not found.
        """
        if isinstance(key, str):
            key = SessionKey.parse(key)

        path = self._get_session_path(key)
        key_str = str(key)

        if key_str in self._sessions:
            del self._sessions[key_str]

        if path.exists():
            path.unlink()
            return True

        return False

    def recover_all(self) -> list[str]:
        """Recover all sessions from JSONL files on disk.

        Called on startup to rebuild the session index.

        Returns:
            List of recovered session keys.
        """
        recovered = []
        for path in self.sessions_dir.glob("*.jsonl"):
            stem = path.stem
            parts = stem.split("_", 1)
            if len(parts) != 2:
                continue

            agent_id, session_id = parts
            key = SessionKey(agent_id=agent_id, session_id=session_id)

            session = self.load(key)
            if session:
                recovered.append(str(key))

        return recovered
