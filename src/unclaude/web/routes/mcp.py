"""MCP (Model Context Protocol) API routes."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


@router.get("/mcp/servers")
async def list_mcp_servers():
    """List configured MCP servers."""
    from unclaude.mcp import MCPClient
    
    client = MCPClient()
    configs = client._load_config()
    
    return {
        "servers": [
            {
                "name": name,
                "command": config.command,
                "args": config.args,
            }
            for name, config in configs.items()
        ],
        "config_path": str(client.config_path),
        "config_exists": client.config_path.exists(),
    }


@router.post("/mcp/init")
async def init_mcp_config():
    """Create MCP config template."""
    from unclaude.mcp import MCPClient, create_mcp_config_template
    
    client = MCPClient()
    
    if client.config_path.exists():
        return {
            "success": False,
            "message": f"MCP config already exists at {client.config_path}",
            "path": str(client.config_path),
        }
    
    client.config_path.parent.mkdir(parents=True, exist_ok=True)
    client.config_path.write_text(create_mcp_config_template())
    
    return {
        "success": True,
        "message": "MCP config created",
        "path": str(client.config_path),
    }


class MCPServerConfig(BaseModel):
    """MCP server configuration."""
    name: str
    command: str
    args: list[str] = []
    env: dict = {}


@router.post("/mcp/servers")
async def add_mcp_server(config: MCPServerConfig):
    """Add a new MCP server configuration."""
    import yaml
    from unclaude.mcp import MCPClient
    
    client = MCPClient()
    
    if not client.config_path.exists():
        raise HTTPException(status_code=400, detail="MCP config does not exist. Run /mcp/init first.")
    
    # Load existing config
    with open(client.config_path) as f:
        mcp_config = yaml.safe_load(f) or {}
    
    if "mcpServers" not in mcp_config:
        mcp_config["mcpServers"] = {}
    
    if config.name in mcp_config["mcpServers"]:
        raise HTTPException(status_code=400, detail=f"Server '{config.name}' already exists")
    
    mcp_config["mcpServers"][config.name] = {
        "command": config.command,
        "args": config.args,
    }
    if config.env:
        mcp_config["mcpServers"][config.name]["env"] = config.env
    
    with open(client.config_path, "w") as f:
        yaml.dump(mcp_config, f, default_flow_style=False)
    
    return {
        "success": True,
        "message": f"MCP server '{config.name}' added",
    }


@router.delete("/mcp/servers/{name}")
async def remove_mcp_server(name: str):
    """Remove an MCP server configuration."""
    import yaml
    from unclaude.mcp import MCPClient
    
    client = MCPClient()
    
    if not client.config_path.exists():
        raise HTTPException(status_code=400, detail="MCP config does not exist")
    
    with open(client.config_path) as f:
        mcp_config = yaml.safe_load(f) or {}
    
    if "mcpServers" not in mcp_config or name not in mcp_config["mcpServers"]:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    
    del mcp_config["mcpServers"][name]
    
    with open(client.config_path, "w") as f:
        yaml.dump(mcp_config, f, default_flow_style=False)
    
    return {
        "success": True,
        "message": f"MCP server '{name}' removed",
    }
