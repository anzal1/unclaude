"""MCP (Model Context Protocol) client for UnClaude.

This module implements an MCP client that can connect to MCP servers
and expose their tools to the agent.
"""

import asyncio
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from unclaude.tools.base import Tool, ToolResult


class MCPServerConfig(BaseModel):
    """Configuration for an MCP server."""

    command: str
    args: list[str] = []
    env: dict[str, str] = {}


class MCPTool(Tool):
    """A tool exposed by an MCP server."""

    def __init__(
        self,
        tool_name: str,
        tool_description: str,
        tool_parameters: dict[str, Any],
        server_name: str,
        mcp_client: "MCPClient",
    ):
        self._name = tool_name
        self._description = tool_description
        self._parameters = tool_parameters
        self.server_name = server_name
        self.mcp_client = mcp_client

    @property
    def name(self) -> str:
        return f"mcp_{self.server_name}_{self._name}"

    @property
    def description(self) -> str:
        return f"[MCP:{self.server_name}] {self._description}"

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    @property
    def requires_permission(self) -> bool:
        return True  # MCP tools always require permission

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the MCP tool by calling the server."""
        return await self.mcp_client.call_tool(
            self.server_name, self._name, kwargs
        )


@dataclass
class MCPServer:
    """An active MCP server connection."""

    name: str
    config: MCPServerConfig
    process: subprocess.Popen | None = None
    tools: list[MCPTool] = field(default_factory=list)
    resources: list[dict[str, Any]] = field(default_factory=list)


class MCPClient:
    """Client for connecting to MCP servers."""

    def __init__(self, config_path: Path | None = None):
        """Initialize the MCP client.

        Args:
            config_path: Path to MCP configuration file.
        """
        self.config_path = config_path or (Path.home() / ".unclaude" / "mcp.yaml")
        self.servers: dict[str, MCPServer] = {}
        self._request_id = 0

    def _load_config(self) -> dict[str, MCPServerConfig]:
        """Load MCP server configurations."""
        if not self.config_path.exists():
            return {}

        with open(self.config_path) as f:
            config = yaml.safe_load(f) or {}

        servers = {}
        servers_config = config.get("servers") or {}
        for name, server_config in servers_config.items():
            servers[name] = MCPServerConfig(**server_config)

        return servers

    async def start_server(self, name: str, config: MCPServerConfig) -> MCPServer:
        """Start an MCP server.

        Args:
            name: Name of the server.
            config: Server configuration.

        Returns:
            MCPServer instance.
        """
        # Build environment with config env vars
        import os
        env = os.environ.copy()
        for key, value in config.env.items():
            # Expand environment variables in values
            env[key] = os.path.expandvars(value)

        # Start the server process
        cmd = [config.command] + config.args
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        server = MCPServer(name=name, config=config, process=process)

        # Initialize the connection
        await self._initialize_server(server)

        self.servers[name] = server
        return server

    async def _initialize_server(self, server: MCPServer) -> None:
        """Initialize connection with an MCP server."""
        # Send initialize request
        response = await self._send_request(
            server,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "unclaude",
                    "version": "0.1.0",
                },
            },
        )

        # List available tools
        tools_response = await self._send_request(server, "tools/list", {})
        
        if tools_response and "tools" in tools_response:
            for tool_data in tools_response["tools"]:
                tool = MCPTool(
                    tool_name=tool_data["name"],
                    tool_description=tool_data.get("description", ""),
                    tool_parameters=tool_data.get("inputSchema", {}),
                    server_name=server.name,
                    mcp_client=self,
                )
                server.tools.append(tool)

        # List available resources
        resources_response = await self._send_request(server, "resources/list", {})
        if resources_response and "resources" in resources_response:
            server.resources = resources_response["resources"]

    async def _send_request(
        self, server: MCPServer, method: str, params: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Send a JSON-RPC request to an MCP server.

        Args:
            server: The server to send to.
            method: The method name.
            params: Method parameters.

        Returns:
            Response result or None.
        """
        if not server.process or not server.process.stdin or not server.process.stdout:
            return None

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        try:
            # Write request
            request_line = json.dumps(request) + "\n"
            server.process.stdin.write(request_line.encode())
            server.process.stdin.flush()

            # Read response
            response_line = server.process.stdout.readline()
            if response_line:
                response = json.loads(response_line.decode())
                return response.get("result")
        except Exception as e:
            print(f"MCP request error: {e}")

        return None

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any]
    ) -> ToolResult:
        """Call a tool on an MCP server.

        Args:
            server_name: Name of the server.
            tool_name: Name of the tool.
            arguments: Tool arguments.

        Returns:
            ToolResult with the output.
        """
        server = self.servers.get(server_name)
        if not server:
            return ToolResult(
                success=False,
                output="",
                error=f"MCP server '{server_name}' not found",
            )

        response = await self._send_request(
            server,
            "tools/call",
            {
                "name": tool_name,
                "arguments": arguments,
            },
        )

        if response:
            content = response.get("content", [])
            if content and isinstance(content, list):
                text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
                return ToolResult(success=True, output="\n".join(text_parts))
            return ToolResult(success=True, output=str(response))

        return ToolResult(
            success=False,
            output="",
            error="No response from MCP server",
        )

    async def connect_all(self) -> list[Tool]:
        """Connect to all configured MCP servers.

        Returns:
            List of tools from all servers.
        """
        configs = self._load_config()
        all_tools: list[Tool] = []

        for name, config in configs.items():
            try:
                server = await self.start_server(name, config)
                all_tools.extend(server.tools)
            except Exception as e:
                print(f"Failed to connect to MCP server '{name}': {e}")

        return all_tools

    def get_all_tools(self) -> list[Tool]:
        """Get all tools from connected servers.

        Returns:
            List of all MCP tools.
        """
        tools: list[Tool] = []
        for server in self.servers.values():
            tools.extend(server.tools)
        return tools

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        for server in self.servers.values():
            if server.process:
                server.process.terminate()
                try:
                    server.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.process.kill()

        self.servers.clear()


def create_mcp_config_template() -> str:
    """Create a template MCP configuration file.

    Returns:
        YAML string with example configuration.
    """
    return """# MCP Server Configuration for UnClaude
# Add your MCP servers here

servers:
  # GitHub MCP Server (requires GITHUB_TOKEN env var)
  # github:
  #   command: npx
  #   args: ["-y", "@modelcontextprotocol/server-github"]
  #   env:
  #     GITHUB_TOKEN: ${GITHUB_TOKEN}

  # Filesystem MCP Server
  # filesystem:
  #   command: npx
  #   args: ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/dir"]

  # PostgreSQL MCP Server
  # postgres:
  #   command: npx
  #   args: ["-y", "@modelcontextprotocol/server-postgres"]
  #   env:
  #     DATABASE_URL: ${DATABASE_URL}
"""
