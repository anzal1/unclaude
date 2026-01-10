"""Hooks system for pre/post tool execution automation."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml


@dataclass
class Hook:
    """A single hook definition."""
    
    name: str
    event: str  # "pre_tool" or "post_tool"
    tool_name: str | None = None  # None = all tools
    command: str | None = None  # Shell command to run
    script: str | None = None  # Python script path


@dataclass
class HooksConfig:
    """Configuration for the hooks system."""
    
    hooks: list[Hook] = field(default_factory=list)


class HooksEngine:
    """Engine for executing hooks before/after tool calls."""

    def __init__(self, project_path: Path | None = None):
        self.project_path = project_path or Path.cwd()
        self.config_path = self.project_path / ".unclaude" / "hooks.yaml"
        self._hooks: list[Hook] = []
        self._load_hooks()

    def _load_hooks(self) -> None:
        """Load hooks from configuration file."""
        if not self.config_path.exists():
            return

        try:
            with open(self.config_path) as f:
                data = yaml.safe_load(f) or {}

            for hook_data in data.get("hooks", []):
                self._hooks.append(Hook(
                    name=hook_data.get("name", "unnamed"),
                    event=hook_data.get("event", "post_tool"),
                    tool_name=hook_data.get("tool"),
                    command=hook_data.get("command"),
                    script=hook_data.get("script"),
                ))
        except Exception:
            pass  # Silently ignore malformed hooks

    def get_hooks(self, event: str, tool_name: str | None = None) -> list[Hook]:
        """Get hooks for a specific event and tool.

        Args:
            event: "pre_tool" or "post_tool"
            tool_name: Name of the tool (or None for tool-agnostic hooks)

        Returns:
            List of matching hooks.
        """
        matching = []
        for hook in self._hooks:
            if hook.event != event:
                continue
            if hook.tool_name and hook.tool_name != tool_name:
                continue
            matching.append(hook)
        return matching

    async def execute_hooks(
        self,
        event: str,
        tool_name: str,
        tool_args: dict[str, Any] | None = None,
        tool_result: Any = None,
    ) -> list[dict[str, Any]]:
        """Execute hooks for an event.

        Args:
            event: "pre_tool" or "post_tool"
            tool_name: Name of the tool being called
            tool_args: Arguments passed to the tool (for pre hooks)
            tool_result: Result from the tool (for post hooks)

        Returns:
            List of hook execution results.
        """
        hooks = self.get_hooks(event, tool_name)
        results = []

        for hook in hooks:
            result = await self._execute_single_hook(hook, tool_name, tool_args, tool_result)
            results.append({
                "hook": hook.name,
                "success": result.get("success", False),
                "output": result.get("output", ""),
            })

        return results

    async def _execute_single_hook(
        self,
        hook: Hook,
        tool_name: str,
        tool_args: dict[str, Any] | None,
        tool_result: Any,
    ) -> dict[str, Any]:
        """Execute a single hook."""
        import os

        env = os.environ.copy()
        env["UNCLAUDE_TOOL_NAME"] = tool_name
        env["UNCLAUDE_HOOK_EVENT"] = hook.event

        if tool_args:
            import json
            env["UNCLAUDE_TOOL_ARGS"] = json.dumps(tool_args)

        if tool_result:
            env["UNCLAUDE_TOOL_RESULT"] = str(tool_result)[:10000]  # Limit size

        try:
            if hook.command:
                result = subprocess.run(
                    hook.command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    cwd=str(self.project_path),
                    env=env,
                )
                return {
                    "success": result.returncode == 0,
                    "output": result.stdout + result.stderr,
                }

            elif hook.script:
                script_path = self.project_path / hook.script
                if script_path.exists():
                    result = subprocess.run(
                        ["python3", str(script_path)],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        cwd=str(self.project_path),
                        env=env,
                    )
                    return {
                        "success": result.returncode == 0,
                        "output": result.stdout + result.stderr,
                    }
                else:
                    return {"success": False, "output": f"Script not found: {hook.script}"}

            return {"success": True, "output": "No action defined"}

        except subprocess.TimeoutExpired:
            return {"success": False, "output": "Hook timed out"}
        except Exception as e:
            return {"success": False, "output": f"Hook error: {str(e)}"}


def create_hooks_template() -> str:
    """Create a template hooks.yaml file."""
    return """# UnClaude Hooks Configuration
# Hooks run before (pre_tool) or after (post_tool) tool execution

hooks:
  # Example: Run linter after file edits
  - name: auto-lint
    event: post_tool
    tool: file_edit
    command: "ruff check --fix ."

  # Example: Run tests after any bash command
  - name: auto-test
    event: post_tool
    tool: bash_execute
    command: "echo 'Bash command completed'"

  # Example: Log all tool calls
  # - name: logger
  #   event: pre_tool
  #   command: "echo \"Running tool: $UNCLAUDE_TOOL_NAME\" >> .unclaude/tool.log"
"""
