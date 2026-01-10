"""Memory system for persistent context across sessions."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class MemoryEntry(BaseModel):
    """A single memory entry."""

    id: str
    content: str
    memory_type: str  # core, recall, archival
    metadata: dict[str, Any] = {}
    created_at: datetime
    updated_at: datetime


class MemoryStore:
    """SQLite-based memory store for conversation persistence."""

    def __init__(self, db_path: Path | None = None):
        """Initialize the memory store.

        Args:
            db_path: Path to the SQLite database. Defaults to ~/.unclaude/memory.db
        """
        self.db_path = db_path or (Path.home() / ".unclaude" / "memory.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Conversations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                project_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT,
                role TEXT,
                content TEXT,
                tool_calls TEXT,
                tool_call_id TEXT,
                name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id)
            )
        """)

        # Memory table for long-term storage
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                memory_type TEXT,
                content TEXT,
                metadata TEXT,
                project_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    def create_conversation(self, project_path: str | None = None) -> str:
        """Create a new conversation.

        Args:
            project_path: Path to the project directory.

        Returns:
            The conversation ID.
        """
        import uuid

        conv_id = str(uuid.uuid4())
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO conversations (id, project_path) VALUES (?, ?)",
            (conv_id, project_path),
        )

        conn.commit()
        conn.close()
        return conv_id

    def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str | None,
        tool_calls: list[dict] | None = None,
        tool_call_id: str | None = None,
        name: str | None = None,
    ) -> None:
        """Save a message to a conversation.

        Args:
            conversation_id: The conversation ID.
            role: Message role (system, user, assistant, tool).
            content: Message content.
            tool_calls: Tool calls made by assistant.
            tool_call_id: ID of the tool call this message responds to.
            name: Name of the tool.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """INSERT INTO messages 
               (conversation_id, role, content, tool_calls, tool_call_id, name)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                conversation_id,
                role,
                content,
                json.dumps(tool_calls) if tool_calls else None,
                tool_call_id,
                name,
            ),
        )

        # Update conversation timestamp
        cursor.execute(
            "UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (conversation_id,),
        )

        conn.commit()
        conn.close()

    def get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        """Get all messages in a conversation.

        Args:
            conversation_id: The conversation ID.

        Returns:
            List of message dictionaries.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """SELECT role, content, tool_calls, tool_call_id, name
               FROM messages WHERE conversation_id = ? ORDER BY id""",
            (conversation_id,),
        )

        messages = []
        for row in cursor.fetchall():
            msg: dict[str, Any] = {"role": row[0]}
            if row[1]:
                msg["content"] = row[1]
            if row[2]:
                msg["tool_calls"] = json.loads(row[2])
            if row[3]:
                msg["tool_call_id"] = row[3]
            if row[4]:
                msg["name"] = row[4]
            messages.append(msg)

        conn.close()
        return messages

    def get_recent_conversations(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent conversations.

        Args:
            limit: Maximum number of conversations to return.

        Returns:
            List of conversation dictionaries.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """SELECT id, project_path, created_at, updated_at
               FROM conversations ORDER BY updated_at DESC LIMIT ?""",
            (limit,),
        )

        conversations = []
        for row in cursor.fetchall():
            conversations.append({
                "id": row[0],
                "project_path": row[1],
                "created_at": row[2],
                "updated_at": row[3],
            })

        conn.close()
        return conversations

    def save_memory(
        self,
        memory_id: str,
        content: str,
        memory_type: str = "recall",
        metadata: dict[str, Any] | None = None,
        project_path: str | None = None,
    ) -> None:
        """Save a memory entry.

        Args:
            memory_id: Unique ID for the memory.
            content: Memory content.
            memory_type: Type of memory (core, recall, archival).
            metadata: Additional metadata.
            project_path: Associated project path.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """INSERT OR REPLACE INTO memories 
               (id, memory_type, content, metadata, project_path, updated_at)
               VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (
                memory_id,
                memory_type,
                content,
                json.dumps(metadata or {}),
                project_path,
            ),
        )

        conn.commit()
        conn.close()

    def search_memories(
        self,
        query: str,
        memory_type: str | None = None,
        project_path: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search memories by content.

        Args:
            query: Search query.
            memory_type: Filter by memory type.
            project_path: Filter by project path.
            limit: Maximum number of results.

        Returns:
            List of matching memories.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Token-based OR search for better recall
        words = query.split()
        keywords = [w for w in words if len(w) > 3] # Filter short words
        if not keywords:
            keywords = [query]
            
        conditions = ["content LIKE ?" for _ in keywords]
        sql = f"SELECT id, memory_type, content, metadata, project_path, created_at FROM memories WHERE ({' OR '.join(conditions)})"
        params: list[Any] = [f"%{k}%" for k in keywords]
        
        if memory_type:
            sql += " AND memory_type = ?"
            params.append(memory_type)

        if project_path:
            sql += " AND project_path = ?"
            params.append(project_path)

        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(sql, params)

        memories = []
        for row in cursor.fetchall():
            memories.append({
                "id": row[0],
                "memory_type": row[1],
                "content": row[2],
                "metadata": json.loads(row[3]) if row[3] else {},
                "project_path": row[4],
                "created_at": row[5],
            })

        conn.close()
        return memories

    def delete_conversation(self, conversation_id: str) -> None:
        """Delete a conversation and its messages.

        Args:
            conversation_id: The conversation ID.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

        conn.commit()
        conn.close()
