"""Memory tool for querying stored memories."""

from typing import Any

from unclaude.memory import MemoryStore
from unclaude.tools.base import Tool, ToolResult


class MemoryTool(Tool):
    """Tool for searching and managing long-term memories."""

    def __init__(self):
        self._memory_store = MemoryStore()

    @property
    def name(self) -> str:
        return "memory_search"

    @property
    def description(self) -> str:
        return (
            "Search your long-term memory for past conversations, tasks, and context. "
            "Use this when the user asks about previous work, history, or things you should remember. "
            "You can search globally (all projects) or filter by project path."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keywords to search for in memories (e.g., 'API key', 'React app', 'deployment')",
                },
                "scope": {
                    "type": "string",
                    "enum": ["global", "project"],
                    "description": "Search scope: 'global' for all memories ever, 'project' for current project only",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of memories to return (default: 10)",
                },
            },
            "required": ["query"],
        }

    @property
    def requires_permission(self) -> bool:
        return False  # Read-only, safe to auto-run

    async def execute(self, query: str, scope: str = "global", limit: int = 10, **kwargs: Any) -> ToolResult:
        try:
            # Determine project filter
            project_path = None
            if scope == "project":
                import os
                project_path = os.getcwd()

            # Search memories
            memories = self._memory_store.search_memories(
                query=query,
                project_path=project_path,
                limit=limit,
            )

            if not memories:
                return ToolResult(
                    success=True,
                    output=f"No memories found matching '{query}'.",
                )

            # Format results
            results = []
            for mem in memories:
                content_preview = mem["content"][:300] + "..." if len(mem["content"]) > 300 else mem["content"]
                project = mem.get("project_path", "unknown")
                created = mem.get("created_at", "unknown")
                results.append(f"[{created}] ({project})\n{content_preview}")

            output = f"Found {len(memories)} memories:\n\n" + "\n\n---\n\n".join(results)
            return ToolResult(success=True, output=output)

        except Exception as e:
            return ToolResult(success=False, output="", error=f"Memory search failed: {str(e)}")


class MemoryStoreTool(Tool):
    """Tool for explicitly saving important information to memory."""

    def __init__(self):
        self._memory_store = MemoryStore()

    @property
    def name(self) -> str:
        return "memory_save"

    @property
    def description(self) -> str:
        return (
            "Save an important piece of information to long-term memory. "
            "Use this when the user explicitly asks you to 'remember' something important, "
            "like API keys, architecture decisions, or project-specific facts."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The information to remember (be specific and include context)",
                },
                "memory_type": {
                    "type": "string",
                    "enum": ["core", "recall"],
                    "description": "'core' for critical facts, 'recall' for general context",
                },
            },
            "required": ["content"],
        }

    @property
    def requires_permission(self) -> bool:
        return False  # Safe

    async def execute(self, content: str, memory_type: str = "core", **kwargs: Any) -> ToolResult:
        try:
            import os
            import uuid
            
            memory_id = f"explicit-{uuid.uuid4()}"
            self._memory_store.save_memory(
                memory_id=memory_id,
                content=content,
                memory_type=memory_type,
                metadata={"explicit": True},
                project_path=os.getcwd(),
            )

            return ToolResult(
                success=True,
                output=f"Saved to {memory_type} memory: '{content[:100]}...'",
            )

        except Exception as e:
            return ToolResult(success=False, output="", error=f"Memory save failed: {str(e)}")
