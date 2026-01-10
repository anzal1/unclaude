"""Plugin system for UnClaude.

This module provides a plugin architecture for extending UnClaude
with custom tools, hooks, and commands.
"""

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

import yaml
from pydantic import BaseModel

from unclaude.tools.base import Tool, ToolResult


class PluginManifest(BaseModel):
    """Plugin manifest (plugin.yaml)."""

    name: str
    version: str
    description: str = ""
    author: str = ""
    
    # Entry points
    tools: list[str] = []  # List of tool module paths
    hooks: list[str] = []  # List of hook module paths
    commands: list[str] = []  # List of command module paths


class Hook(Protocol):
    """Protocol for plugin hooks."""

    async def on_before_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        """Called before a tool is executed.
        
        Args:
            tool_name: Name of the tool.
            arguments: Tool arguments.
            
        Returns:
            Modified arguments or None to use original.
        """
        ...

    async def on_after_tool(self, tool_name: str, result: ToolResult) -> ToolResult | None:
        """Called after a tool is executed.
        
        Args:
            tool_name: Name of the tool.
            result: Tool result.
            
        Returns:
            Modified result or None to use original.
        """
        ...

    async def on_message(self, role: str, content: str) -> str | None:
        """Called when a message is added to the conversation.
        
        Args:
            role: Message role.
            content: Message content.
            
        Returns:
            Modified content or None to use original.
        """
        ...


@dataclass
class Plugin:
    """A loaded plugin."""

    name: str
    path: Path
    manifest: PluginManifest
    tools: list[Tool] = field(default_factory=list)
    hooks: list[Hook] = field(default_factory=list)
    commands: dict[str, Callable] = field(default_factory=dict)


class PluginManager:
    """Manages UnClaude plugins."""

    def __init__(self, plugins_dir: Path | None = None):
        """Initialize the plugin manager.

        Args:
            plugins_dir: Directory containing plugins.
        """
        self.plugins_dir = plugins_dir or (Path.home() / ".unclaude" / "plugins")
        self.plugins: dict[str, Plugin] = {}

    def discover_plugins(self) -> list[Path]:
        """Discover all plugins in the plugins directory.

        Returns:
            List of plugin directories.
        """
        if not self.plugins_dir.exists():
            return []

        plugin_dirs = []
        for item in self.plugins_dir.iterdir():
            if item.is_dir() and (item / "plugin.yaml").exists():
                plugin_dirs.append(item)

        return plugin_dirs

    def load_plugin(self, plugin_path: Path) -> Plugin | None:
        """Load a plugin from a directory.

        Args:
            plugin_path: Path to the plugin directory.

        Returns:
            Loaded Plugin or None if failed.
        """
        manifest_path = plugin_path / "plugin.yaml"
        if not manifest_path.exists():
            return None

        try:
            with open(manifest_path) as f:
                manifest_data = yaml.safe_load(f)
            manifest = PluginManifest(**manifest_data)
        except Exception as e:
            print(f"Failed to load plugin manifest: {e}")
            return None

        plugin = Plugin(
            name=manifest.name,
            path=plugin_path,
            manifest=manifest,
        )

        # Load tools
        for tool_path in manifest.tools:
            tool = self._load_tool(plugin_path, tool_path)
            if tool:
                plugin.tools.append(tool)

        # Load hooks
        for hook_path in manifest.hooks:
            hook = self._load_hook(plugin_path, hook_path)
            if hook:
                plugin.hooks.append(hook)

        # Load commands
        for cmd_path in manifest.commands:
            name, func = self._load_command(plugin_path, cmd_path)
            if name and func:
                plugin.commands[name] = func

        self.plugins[manifest.name] = plugin
        return plugin

    def _load_module(self, plugin_path: Path, module_path: str) -> Any | None:
        """Load a Python module from a plugin.

        Args:
            plugin_path: Path to the plugin directory.
            module_path: Relative path to the module.

        Returns:
            Loaded module or None.
        """
        full_path = plugin_path / module_path
        if not full_path.exists():
            return None

        try:
            spec = importlib.util.spec_from_file_location(
                f"unclaude_plugin_{full_path.stem}",
                full_path,
            )
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
                return module
        except Exception as e:
            print(f"Failed to load module {module_path}: {e}")

        return None

    def _load_tool(self, plugin_path: Path, tool_path: str) -> Tool | None:
        """Load a tool from a plugin.

        Args:
            plugin_path: Path to the plugin directory.
            tool_path: Relative path to the tool module.

        Returns:
            Tool instance or None.
        """
        module = self._load_module(plugin_path, tool_path)
        if module and hasattr(module, "create_tool"):
            return module.create_tool()
        return None

    def _load_hook(self, plugin_path: Path, hook_path: str) -> Hook | None:
        """Load a hook from a plugin.

        Args:
            plugin_path: Path to the plugin directory.
            hook_path: Relative path to the hook module.

        Returns:
            Hook instance or None.
        """
        module = self._load_module(plugin_path, hook_path)
        if module and hasattr(module, "create_hook"):
            return module.create_hook()
        return None

    def _load_command(
        self, plugin_path: Path, cmd_path: str
    ) -> tuple[str | None, Callable | None]:
        """Load a command from a plugin.

        Args:
            plugin_path: Path to the plugin directory.
            cmd_path: Relative path to the command module.

        Returns:
            Tuple of (command_name, command_function) or (None, None).
        """
        module = self._load_module(plugin_path, cmd_path)
        if module:
            name = getattr(module, "COMMAND_NAME", None)
            func = getattr(module, "run_command", None)
            if name and func:
                return name, func
        return None, None

    def load_all_plugins(self) -> list[Plugin]:
        """Load all discovered plugins.

        Returns:
            List of loaded plugins.
        """
        plugin_dirs = self.discover_plugins()
        loaded = []

        for plugin_path in plugin_dirs:
            plugin = self.load_plugin(plugin_path)
            if plugin:
                loaded.append(plugin)

        return loaded

    def get_all_tools(self) -> list[Tool]:
        """Get all tools from loaded plugins.

        Returns:
            List of tools.
        """
        tools: list[Tool] = []
        for plugin in self.plugins.values():
            tools.extend(plugin.tools)
        return tools

    def get_all_hooks(self) -> list[Hook]:
        """Get all hooks from loaded plugins.

        Returns:
            List of hooks.
        """
        hooks: list[Hook] = []
        for plugin in self.plugins.values():
            hooks.extend(plugin.hooks)
        return hooks

    def get_command(self, name: str) -> Callable | None:
        """Get a command by name.

        Args:
            name: Command name.

        Returns:
            Command function or None.
        """
        for plugin in self.plugins.values():
            if name in plugin.commands:
                return plugin.commands[name]
        return None


def create_plugin_template(plugin_name: str, plugin_path: Path) -> None:
    """Create a plugin template.

    Args:
        plugin_name: Name of the plugin.
        plugin_path: Path to create the plugin.
    """
    plugin_path.mkdir(parents=True, exist_ok=True)

    # Create plugin.yaml
    manifest = f"""name: {plugin_name}
version: 0.1.0
description: A custom UnClaude plugin
author: Your Name

tools:
  - tools/example_tool.py

hooks: []

commands:
  - commands/example_command.py
"""
    (plugin_path / "plugin.yaml").write_text(manifest)

    # Create tools directory and example tool
    (plugin_path / "tools").mkdir(exist_ok=True)
    example_tool = '''"""Example plugin tool."""

from typing import Any
from unclaude.tools.base import Tool, ToolResult


class ExampleTool(Tool):
    """An example custom tool."""

    @property
    def name(self) -> str:
        return "example_tool"

    @property
    def description(self) -> str:
        return "An example tool that echoes your input."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Message to echo",
                },
            },
            "required": ["message"],
        }

    async def execute(self, message: str, **kwargs: Any) -> ToolResult:
        return ToolResult(
            success=True,
            output=f"Echo: {message}",
        )


def create_tool() -> Tool:
    """Factory function to create the tool."""
    return ExampleTool()
'''
    (plugin_path / "tools" / "example_tool.py").write_text(example_tool)

    # Create commands directory and example command
    (plugin_path / "commands").mkdir(exist_ok=True)
    example_command = '''"""Example plugin command."""

COMMAND_NAME = "example"


def run_command(args: list[str]) -> str:
    """Run the example command.
    
    Args:
        args: Command arguments.
        
    Returns:
        Command output.
    """
    return f"Example command executed with args: {args}"
'''
    (plugin_path / "commands" / "example_command.py").write_text(example_command)
