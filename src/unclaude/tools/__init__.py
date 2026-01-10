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


def get_default_tools() -> list[Tool]:
    """Get the default set of tools."""
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
    "get_default_tools",
]
