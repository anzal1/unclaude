"""Audit logging for agent actions.

Every tool execution, permission check, and policy decision
is recorded here. This creates an immutable trail of what
the agent did, when, and why.

The audit log answers:
- What files did the agent modify?
- What commands did it run?
- What was denied and why?
- How much did this session cost?
- What was the agent's reasoning chain?
"""

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class AuditEventType(str, Enum):
    """Types of auditable events."""

    # Agent lifecycle
    SESSION_START = "session:start"
    SESSION_END = "session:end"
    AGENT_SPAWN = "agent:spawn"
    AGENT_COMPLETE = "agent:complete"

    # Tool execution
    TOOL_REQUEST = "tool:request"
    TOOL_EXECUTE = "tool:execute"
    TOOL_RESULT = "tool:result"
    TOOL_ERROR = "tool:error"

    # Auth decisions
    CAPABILITY_CHECK = "auth:capability_check"
    CAPABILITY_DENIED = "auth:capability_denied"
    POLICY_VIOLATION = "auth:policy_violation"
    PERMISSION_GRANTED = "auth:permission_granted"
    PERMISSION_DENIED = "auth:permission_denied"

    # File operations
    FILE_READ = "file:read"
    FILE_WRITE = "file:write"
    FILE_DELETE = "file:delete"

    # Execution
    COMMAND_EXECUTE = "exec:command"
    COMMAND_OUTPUT = "exec:output"

    # Network
    NETWORK_REQUEST = "net:request"
    NETWORK_RESPONSE = "net:response"

    # LLM
    LLM_REQUEST = "llm:request"
    LLM_RESPONSE = "llm:response"
    LLM_ERROR = "llm:error"

    # Memory
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"

    # Cost
    COST_INCURRED = "cost:incurred"


@dataclass
class AuditEvent:
    """A single audit event."""

    event_type: AuditEventType
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Context
    session_id: str = ""
    agent_id: str = ""
    tool_name: str = ""
    capability: str = ""

    # Payload
    data: dict[str, Any] = field(default_factory=dict)

    # Outcome
    success: bool = True
    error_message: str = ""

    # Security
    risk_level: str = "low"  # low, medium, high, critical

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "tool_name": self.tool_name,
            "capability": self.capability,
            "data": self.data,
            "success": self.success,
            "error_message": self.error_message,
            "risk_level": self.risk_level,
        }


class AuditLog:
    """Persistent audit log for agent actions.

    Stores all events in SQLite with structured querying support.
    Events are append-only — once written, they cannot be modified.
    """

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or (Path.home() / ".unclaude" / "audit.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

        # In-memory buffer for batch writing
        self._buffer: list[AuditEvent] = []
        self._buffer_size = 50

    def _init_db(self) -> None:
        """Initialize the audit database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                timestamp REAL NOT NULL,
                session_id TEXT,
                agent_id TEXT,
                tool_name TEXT,
                capability TEXT,
                data TEXT,
                success BOOLEAN,
                error_message TEXT,
                risk_level TEXT DEFAULT 'low',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Indexes for common queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_session
            ON audit_events(session_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_type
            ON audit_events(event_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp
            ON audit_events(timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_risk
            ON audit_events(risk_level)
        """)

        conn.commit()
        conn.close()

    def log(self, event: AuditEvent) -> None:
        """Log an audit event.

        Events are buffered for performance and flushed periodically.
        """
        self._buffer.append(event)
        if len(self._buffer) >= self._buffer_size:
            self.flush()

    def log_now(self, event: AuditEvent) -> None:
        """Log an event immediately (bypass buffer)."""
        self._write_event(event)

    def flush(self) -> None:
        """Flush the buffer to disk."""
        if not self._buffer:
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        for event in self._buffer:
            cursor.execute(
                """INSERT OR IGNORE INTO audit_events
                   (event_id, event_type, timestamp, session_id, agent_id,
                    tool_name, capability, data, success, error_message, risk_level)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.event_id,
                    event.event_type.value,
                    event.timestamp,
                    event.session_id,
                    event.agent_id,
                    event.tool_name,
                    event.capability,
                    json.dumps(event.data),
                    event.success,
                    event.error_message,
                    event.risk_level,
                ),
            )

        conn.commit()
        conn.close()
        self._buffer.clear()

    def _write_event(self, event: AuditEvent) -> None:
        """Write a single event to disk."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """INSERT OR IGNORE INTO audit_events
               (event_id, event_type, timestamp, session_id, agent_id,
                tool_name, capability, data, success, error_message, risk_level)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.event_id,
                event.event_type.value,
                event.timestamp,
                event.session_id,
                event.agent_id,
                event.tool_name,
                event.capability,
                json.dumps(event.data),
                event.success,
                event.error_message,
                event.risk_level,
            ),
        )

        conn.commit()
        conn.close()

    def query(
        self,
        session_id: str | None = None,
        event_type: AuditEventType | None = None,
        risk_level: str | None = None,
        since: float | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query audit events.

        Args:
            session_id: Filter by session.
            event_type: Filter by event type.
            risk_level: Filter by risk level.
            since: Only events after this timestamp.
            limit: Max results.

        Returns:
            List of event dictionaries.
        """
        self.flush()  # Ensure buffer is written

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = "SELECT * FROM audit_events WHERE 1=1"
        params: list[Any] = []

        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type.value)
        if risk_level:
            query += " AND risk_level = ?"
            params.append(risk_level)
        if since:
            query += " AND timestamp > ?"
            params.append(since)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]

        conn.close()
        return results

    def get_session_summary(self, session_id: str) -> dict[str, Any]:
        """Get a summary of a session's audit trail.

        Returns:
            Summary with counts, risk events, files modified, etc.
        """
        self.flush()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Total events
        cursor.execute(
            "SELECT COUNT(*) FROM audit_events WHERE session_id = ?",
            (session_id,),
        )
        total = cursor.fetchone()[0]

        # Events by type
        cursor.execute(
            """SELECT event_type, COUNT(*) FROM audit_events
               WHERE session_id = ? GROUP BY event_type""",
            (session_id,),
        )
        by_type = dict(cursor.fetchall())

        # High risk events
        cursor.execute(
            """SELECT COUNT(*) FROM audit_events
               WHERE session_id = ? AND risk_level IN ('high', 'critical')""",
            (session_id,),
        )
        high_risk = cursor.fetchone()[0]

        # Denied actions
        cursor.execute(
            """SELECT COUNT(*) FROM audit_events
               WHERE session_id = ? AND success = 0""",
            (session_id,),
        )
        denied = cursor.fetchone()[0]

        # Files modified
        cursor.execute(
            """SELECT DISTINCT json_extract(data, '$.path') FROM audit_events
               WHERE session_id = ? AND event_type = 'file:write'""",
            (session_id,),
        )
        files_modified = [row[0] for row in cursor.fetchall() if row[0]]

        # Commands executed
        cursor.execute(
            """SELECT json_extract(data, '$.command') FROM audit_events
               WHERE session_id = ? AND event_type = 'exec:command'""",
            (session_id,),
        )
        commands = [row[0] for row in cursor.fetchall() if row[0]]

        conn.close()

        return {
            "session_id": session_id,
            "total_events": total,
            "events_by_type": by_type,
            "high_risk_events": high_risk,
            "denied_actions": denied,
            "files_modified": files_modified,
            "commands_executed": commands,
        }

    def __del__(self):
        """Ensure buffer is flushed on destruction."""
        try:
            self.flush()
        except Exception:
            pass
