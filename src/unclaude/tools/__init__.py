"""Tools module for UnClaude."""

from unclaude.tools.base import Tool, ToolResult
from unclaude.tools.bash import BashExecuteTool
from unclaude.tools.file import (
    DirectoryListTool,
    FileEditTool,
    FileGlobTool,
    FileGrepTool,
    FileReadTool,
    FileWriteTool,
)
from unclaude.tools.web import WebFetchTool, WebSearchTool
from unclaude.tools.browser import BrowserTool
from unclaude.tools.memory import MemoryTool, MemoryStoreTool
from unclaude.tools.git import GitTool


def get_default_tools() -> list[Tool]:
    """Get the default set of tools."""
    # Lazy import to avoid circular dependency
    from unclaude.agent.subagent import SubagentTool
    
    return [
        FileReadTool(),
        FileWriteTool(),
        FileEditTool(),
        FileGlobTool(),
        FileGrepTool(),
        DirectoryListTool(),
        BashExecuteTool(),
        WebFetchTool(),
        WebSearchTool(),
        BrowserTool(),
        MemoryTool(),
        MemoryStoreTool(),
        GitTool(),
        SubagentTool(),
    ]


__all__ = [
    "Tool",
    "ToolResult",
    "FileReadTool",
    "FileWriteTool",
    "FileEditTool",
    "FileGlobTool",
    "FileGrepTool",
    "DirectoryListTool",
    "BashExecuteTool",
    "WebFetchTool",
    "WebSearchTool",
    "BrowserTool",
    "MemoryTool",
    "MemoryStoreTool",
    "GitTool",
    "get_default_tools",
]
