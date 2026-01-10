"""Git integration tools for version control."""

import subprocess
from typing import Any

from unclaude.tools.base import Tool, ToolResult


class GitTool(Tool):
    """Tool for Git version control operations."""

    @property
    def name(self) -> str:
        return "git"

    @property
    def description(self) -> str:
        return (
            "Perform Git version control operations: commit changes, view diffs, "
            "check status, create branches, and push to remote. "
            "Use this to track your work and collaborate."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "diff", "add", "commit", "push", "branch", "log", "checkout"],
                    "description": "Git action to perform",
                },
                "message": {
                    "type": "string",
                    "description": "Commit message (required for 'commit' action)",
                },
                "files": {
                    "type": "string",
                    "description": "Files to add/stage (for 'add' action, use '.' for all)",
                },
                "branch_name": {
                    "type": "string",
                    "description": "Branch name (for 'branch' or 'checkout' actions)",
                },
                "count": {
                    "type": "integer",
                    "description": "Number of commits to show (for 'log' action, default: 5)",
                },
            },
            "required": ["action"],
        }

    @property
    def requires_permission(self) -> bool:
        return True  # Git operations modify state

    async def execute(
        self,
        action: str,
        message: str | None = None,
        files: str | None = None,
        branch_name: str | None = None,
        count: int = 5,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            if action == "status":
                result = subprocess.run(
                    ["git", "status", "--short"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                output = result.stdout or "Working tree clean"
                return ToolResult(success=True, output=output)

            elif action == "diff":
                result = subprocess.run(
                    ["git", "diff", "--stat"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                output = result.stdout or "No changes"
                # Also show actual diff (limited)
                diff_result = subprocess.run(
                    ["git", "diff", "--no-color"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if diff_result.stdout:
                    output += "\n\n" + diff_result.stdout[:2000]
                    if len(diff_result.stdout) > 2000:
                        output += "\n... (diff truncated)"
                return ToolResult(success=True, output=output)

            elif action == "add":
                files_to_add = files or "."
                result = subprocess.run(
                    ["git", "add", files_to_add],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode != 0:
                    return ToolResult(success=False, output="", error=result.stderr)
                return ToolResult(success=True, output=f"Staged: {files_to_add}")

            elif action == "commit":
                if not message:
                    return ToolResult(success=False, output="", error="Commit message required")
                result = subprocess.run(
                    ["git", "commit", "-m", message],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode != 0:
                    return ToolResult(success=False, output="", error=result.stderr or result.stdout)
                return ToolResult(success=True, output=result.stdout)

            elif action == "push":
                result = subprocess.run(
                    ["git", "push"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode != 0:
                    return ToolResult(success=False, output="", error=result.stderr)
                return ToolResult(success=True, output=result.stdout or "Pushed successfully")

            elif action == "branch":
                if branch_name:
                    # Create new branch
                    result = subprocess.run(
                        ["git", "checkout", "-b", branch_name],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                else:
                    # List branches
                    result = subprocess.run(
                        ["git", "branch", "-a"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                if result.returncode != 0:
                    return ToolResult(success=False, output="", error=result.stderr)
                return ToolResult(success=True, output=result.stdout)

            elif action == "checkout":
                if not branch_name:
                    return ToolResult(success=False, output="", error="Branch name required for checkout")
                result = subprocess.run(
                    ["git", "checkout", branch_name],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode != 0:
                    return ToolResult(success=False, output="", error=result.stderr)
                return ToolResult(success=True, output=f"Switched to {branch_name}")

            elif action == "log":
                result = subprocess.run(
                    ["git", "log", "--oneline", f"-{count}"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                return ToolResult(success=True, output=result.stdout or "No commits yet")

            else:
                return ToolResult(success=False, output="", error=f"Unknown action: {action}")

        except subprocess.TimeoutExpired:
            return ToolResult(success=False, output="", error="Git command timed out")
        except FileNotFoundError:
            return ToolResult(success=False, output="", error="Git is not installed")
        except Exception as e:
            return ToolResult(success=False, output="", error=f"Git error: {str(e)}")
