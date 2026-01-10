"""Bash execution tool for UnClaude."""

import asyncio
import shlex
from typing import Any

from unclaude.tools.base import Tool, ToolResult


# Commands that are typically long-running or start servers
BACKGROUND_COMMANDS = [
    "http.server", "serve", "npm start", "npm run dev", "yarn start",
    "python -m http.server", "python3 -m http.server", "flask run",
    "uvicorn", "gunicorn", "node server", "live-server", "vite",
]


class BashExecuteTool(Tool):
    """Execute bash commands."""

    @property
    def name(self) -> str:
        return "bash_execute"

    @property
    def description(self) -> str:
        return (
            "Execute a bash command and return its output. "
            "Use this to run commands, scripts, tests, or any shell operation. "
            "The command runs in a subprocess with a timeout. "
            "For long-running commands like servers, use 'background=true'."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute",
                },
                "working_directory": {
                    "type": "string",
                    "description": "Directory to run the command in (optional)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default 60)",
                },
                "background": {
                    "type": "boolean",
                    "description": "Run command in background (for servers, default false)",
                },
            },
            "required": ["command"],
        }

    @property
    def requires_permission(self) -> bool:
        return True

    def _is_background_command(self, command: str) -> bool:
        """Check if command is typically a background/server command."""
        cmd_lower = command.lower()
        return any(bg in cmd_lower for bg in BACKGROUND_COMMANDS) or command.strip().endswith("&")

    async def execute(
        self,
        command: str,
        working_directory: str | None = None,
        timeout: int = 60,
        background: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        # Auto-detect background commands
        is_background = background or self._is_background_command(command)
        
        if is_background:
            # For background commands, use shorter timeout and don't kill
            timeout = min(timeout, 5)
        
        try:
            # Create the process
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_directory,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
                
                stdout_str = stdout.decode("utf-8", errors="replace")
                stderr_str = stderr.decode("utf-8", errors="replace")

                output = stdout_str
                if stderr_str:
                    output += f"\n\nSTDERR:\n{stderr_str}"

                return ToolResult(
                    success=process.returncode == 0,
                    output=output.strip() if output.strip() else "(No output)",
                    error=None if process.returncode == 0 else f"Exit code: {process.returncode}",
                )
                
            except asyncio.TimeoutError:
                if is_background:
                    # For background commands, this is expected - the process is running
                    return ToolResult(
                        success=True,
                        output=f"✓ Background process started (PID: {process.pid}). "
                               f"Command is running. Check the expected URL/port.",
                    )
                else:
                    # For regular commands, timeout is an error
                    process.kill()
                    await process.wait()
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Command timed out after {timeout} seconds. "
                              f"For long-running commands, use background=true.",
                    )

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

