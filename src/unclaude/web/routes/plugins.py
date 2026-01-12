"""Plugins API routes."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


@router.get("/plugins")
async def list_plugins():
    """List installed plugins."""
    from unclaude.plugins import PluginManager
    
    plugin_manager = PluginManager()
    plugins = plugin_manager.load_all_plugins()
    
    return {
        "plugins": [
            {
                "name": p.name,
                "version": p.manifest.version,
                "description": p.manifest.description,
                "tools_count": len(p.tools),
                "hooks_count": len(p.hooks),
            }
            for p in plugins
        ],
        "plugins_dir": str(plugin_manager.plugins_dir),
    }


class CreatePluginRequest(BaseModel):
    """Request to create a new plugin."""
    name: str


@router.post("/plugins/create")
async def create_plugin(request: CreatePluginRequest):
    """Create a new plugin template."""
    from unclaude.plugins import PluginManager, create_plugin_template
    
    if not request.name or not request.name.strip():
        raise HTTPException(status_code=400, detail="Plugin name is required")
    
    plugin_manager = PluginManager()
    plugin_path = plugin_manager.plugins_dir / request.name.strip()
    
    if plugin_path.exists():
        raise HTTPException(status_code=400, detail=f"Plugin '{request.name}' already exists")
    
    create_plugin_template(request.name, plugin_path)
    
    return {
        "success": True,
        "message": f"Plugin '{request.name}' created",
        "path": str(plugin_path),
    }


@router.get("/plugins/{name}")
async def get_plugin(name: str):
    """Get details about a specific plugin."""
    from unclaude.plugins import PluginManager
    
    plugin_manager = PluginManager()
    plugins = plugin_manager.load_all_plugins()
    
    plugin = next((p for p in plugins if p.name == name), None)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
    
    return {
        "name": plugin.name,
        "version": plugin.manifest.version,
        "description": plugin.manifest.description,
        "tools": [{"name": t.__name__, "doc": t.__doc__} for t in plugin.tools],
        "hooks": list(plugin.hooks.keys()),
        "path": str(plugin.path),
    }
