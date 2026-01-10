"""File system tools for UnClaude."""

import fnmatch
import os
import re
from pathlib import Path
from typing import Any

from unclaude.tools.base import Tool, ToolResult


class FileReadTool(Tool):
    """Read the contents of a file."""

    @property
    def name(self) -> str:
        return "file_read"

    @property
    def description(self) -> str:
        return (
            "Read the contents of a file. Can optionally read specific line ranges. "
            "Use this to examine code, config files, or any text file."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file to read",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Starting line number (1-indexed, optional)",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Ending line number (1-indexed, inclusive, optional)",
                },
            },
            "required": ["path"],
        }

    async def execute(
        self,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            file_path = Path(path).expanduser().resolve()

            if not file_path.exists():
                return ToolResult(success=False, output="", error=f"File not found: {path}")

            if not file_path.is_file():
                return ToolResult(success=False, output="", error=f"Not a file: {path}")

            content = file_path.read_text()

            # Handle line ranges
            if start_line is not None or end_line is not None:
                lines = content.splitlines(keepends=True)
                start = (start_line or 1) - 1  # Convert to 0-indexed
                end = end_line if end_line else len(lines)
                content = "".join(lines[start:end])

            return ToolResult(success=True, output=content)

        except PermissionError:
            return ToolResult(success=False, output="", error=f"Permission denied: {path}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class FileWriteTool(Tool):
    """Write content to a file (creates new file)."""

    @property
    def name(self) -> str:
        return "file_write"

    @property
    def description(self) -> str:
        return (
            "Create a new file or overwrite an existing file with the given content. "
            "Parent directories will be created if they don't exist."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
            },
            "required": ["path", "content"],
        }

    @property
    def requires_permission(self) -> bool:
        return True

    async def execute(self, path: str, content: str, **kwargs: Any) -> ToolResult:
        try:
            file_path = Path(path).expanduser().resolve()

            # Create parent directories
            file_path.parent.mkdir(parents=True, exist_ok=True)

            file_path.write_text(content)
            return ToolResult(success=True, output=f"Successfully wrote {len(content)} bytes to {path}")

        except PermissionError:
            return ToolResult(success=False, output="", error=f"Permission denied: {path}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class FileEditTool(Tool):
    """Edit an existing file by replacing content."""

    @property
    def name(self) -> str:
        return "file_edit"

    @property
    def description(self) -> str:
        return (
            "Edit an existing file by finding and replacing text. "
            "The old_content must match exactly (including whitespace)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file to edit",
                },
                "old_content": {
                    "type": "string",
                    "description": "The exact content to find and replace",
                },
                "new_content": {
                    "type": "string",
                    "description": "The content to replace it with",
                },
            },
            "required": ["path", "old_content", "new_content"],
        }

    @property
    def requires_permission(self) -> bool:
        return True

    async def execute(
        self, path: str, old_content: str, new_content: str, **kwargs: Any
    ) -> ToolResult:
        try:
            file_path = Path(path).expanduser().resolve()

            if not file_path.exists():
                return ToolResult(success=False, output="", error=f"File not found: {path}")

            content = file_path.read_text()

            if old_content not in content:
                return ToolResult(
                    success=False,
                    output="",
                    error="old_content not found in file. Make sure it matches exactly.",
                )

            # Count occurrences
            count = content.count(old_content)
            if count > 1:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"old_content found {count} times. Please make the match more specific.",
                )

            new_file_content = content.replace(old_content, new_content, 1)
            file_path.write_text(new_file_content)

            return ToolResult(success=True, output=f"Successfully edited {path}")

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class FileGlobTool(Tool):
    """Find files matching a glob pattern."""

    @property
    def name(self) -> str:
        return "file_glob"

    @property
    def description(self) -> str:
        return (
            "Find files matching a glob pattern. "
            "Use patterns like '**/*.py' to find all Python files recursively."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g., '**/*.py', 'src/**/*.ts')",
                },
                "directory": {
                    "type": "string",
                    "description": "Base directory to search in (defaults to current directory)",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default 50)",
                },
            },
            "required": ["pattern"],
        }

    async def execute(
        self,
        pattern: str,
        directory: str = ".",
        max_results: int = 50,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            base_path = Path(directory).expanduser().resolve()

            if not base_path.exists():
                return ToolResult(success=False, output="", error=f"Directory not found: {directory}")

            matches = list(base_path.glob(pattern))[:max_results]
            result = "\n".join(str(m) for m in matches)

            if not matches:
                return ToolResult(success=True, output="No files found matching the pattern.")

            return ToolResult(success=True, output=result)

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class FileGrepTool(Tool):
    """Search for text patterns in files."""

    @property
    def name(self) -> str:
        return "file_grep"

    @property
    def description(self) -> str:
        return (
            "Search for a text pattern in files. "
            "Returns matching lines with file paths and line numbers."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Text or regex pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory to search in",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g., '*.py')",
                },
                "ignore_case": {
                    "type": "boolean",
                    "description": "Whether to ignore case in matching",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (default 50)",
                },
            },
            "required": ["pattern", "path"],
        }

    async def execute(
        self,
        pattern: str,
        path: str,
        file_pattern: str = "*",
        ignore_case: bool = False,
        max_results: int = 50,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            base_path = Path(path).expanduser().resolve()
            flags = re.IGNORECASE if ignore_case else 0

            try:
                regex = re.compile(pattern, flags)
            except re.error:
                # Fall back to literal search if not valid regex
                regex = re.compile(re.escape(pattern), flags)

            results = []

            if base_path.is_file():
                files = [base_path]
            else:
                files = list(base_path.rglob(file_pattern))

            for file_path in files:
                if not file_path.is_file():
                    continue

                try:
                    content = file_path.read_text()
                    for i, line in enumerate(content.splitlines(), 1):
                        if regex.search(line):
                            results.append(f"{file_path}:{i}: {line.strip()}")
                            if len(results) >= max_results:
                                break
                except (UnicodeDecodeError, PermissionError):
                    continue

                if len(results) >= max_results:
                    break

            if not results:
                return ToolResult(success=True, output="No matches found.")

            return ToolResult(success=True, output="\n".join(results))

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))


class DirectoryListTool(Tool):
    """List contents of a directory."""

    @property
    def name(self) -> str:
        return "directory_list"

    @property
    def description(self) -> str:
        return "List the contents of a directory, showing files and subdirectories."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the directory to list",
                },
                "show_hidden": {
                    "type": "boolean",
                    "description": "Whether to show hidden files (starting with .)",
                },
            },
            "required": ["path"],
        }

    async def execute(
        self, path: str, show_hidden: bool = False, **kwargs: Any
    ) -> ToolResult:
        try:
            dir_path = Path(path).expanduser().resolve()

            if not dir_path.exists():
                return ToolResult(success=False, output="", error=f"Directory not found: {path}")

            if not dir_path.is_dir():
                return ToolResult(success=False, output="", error=f"Not a directory: {path}")

            entries = []
            for entry in sorted(dir_path.iterdir()):
                if not show_hidden and entry.name.startswith("."):
                    continue

                if entry.is_dir():
                    entries.append(f"📁 {entry.name}/")
                else:
                    size = entry.stat().st_size
                    entries.append(f"📄 {entry.name} ({size} bytes)")

            if not entries:
                return ToolResult(success=True, output="Directory is empty.")

            return ToolResult(success=True, output="\n".join(entries))

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))
