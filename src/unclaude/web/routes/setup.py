"""Setup API routes — web-based onboarding for non-technical users.

Provides endpoints for the full setup flow:
- Setup status (what's configured)
- Soul generation (natural language → YAML)
- Soul management (save, load, preview)
- Daemon control (start, stop, status)
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


# ── Request/Response Models ────────────────────────────

class SoulGenerateRequest(BaseModel):
    """Request to generate a soul from natural language."""
    description: str
    agent_name: str = "UnClaude"


class SoulSaveRequest(BaseModel):
    """Request to save soul YAML content."""
    content: str


class SoulPickListRequest(BaseModel):
    """Request to generate soul from preset behaviors."""
    agent_name: str = "UnClaude"
    tagline: str = "Open-source AI agent that actually does things"
    behaviors: list[str]  # List of behavior keys to enable


# ── Setup Status ───────────────────────────────────────

@router.get("/setup/status")
async def get_setup_status():
    """Get the full setup status — what's configured and what's missing."""
    import os
    from unclaude.onboarding import (
        PROVIDERS, load_config, get_credentials_path, soul_exists,
    )

    config = load_config()

    # Provider status — detect default provider or find first configured one
    provider_name = config.get("default_provider", "")
    if not provider_name:
        # Auto-detect: find first provider with api_key in config
        for pname in config.get("providers", {}):
            if config["providers"][pname].get("api_key"):
                provider_name = pname
                break

    provider_info = PROVIDERS.get(provider_name, {})
    provider_config = config.get("providers", {}).get(provider_name, {})
    provider_model = provider_config.get("model", "")

    # Check for API key in multiple locations
    credentials = {}
    creds_path = get_credentials_path()
    if creds_path.exists():
        import yaml
        with open(creds_path) as f:
            credentials = yaml.safe_load(f) or {}

    has_key = bool(
        provider_config.get("api_key") or
        credentials.get(provider_name) or
        (provider_info.get("env_var")
         and os.environ.get(provider_info["env_var"]))
    )

    # Messaging status
    messaging_configured = False
    try:
        from unclaude.messaging import get_messenger
        messenger = get_messenger()
        status = messenger.get_status()
        platforms = status.get("platforms", {})
        messaging_configured = any(
            p.get("configured", False) for p in platforms.values()
        )
    except Exception:
        pass

    # Soul status
    has_soul = soul_exists()
    soul_summary = None
    if has_soul:
        try:
            import yaml
            soul_path = Path.home() / ".unclaude" / "proactive.yaml"
            raw = soul_path.read_text()
            parsed = yaml.safe_load(raw)
            if isinstance(parsed, dict):
                identity = parsed.get("identity", {})
                behaviors = parsed.get("behaviors", [])
                active = [b for b in behaviors if b.get("enabled", False)]
                soul_summary = {
                    "name": identity.get("name", "UnClaude"),
                    "tagline": identity.get("tagline", ""),
                    "behavior_count": len(active),
                    "behavior_names": [b.get("name", "?") for b in active],
                }
        except Exception:
            pass

    # Daemon status
    daemon_running = False
    try:
        from unclaude.autonomous.daemon import AgentDaemon
        daemon = AgentDaemon(project_path=Path.cwd())
        daemon_running = daemon.is_running()
    except Exception:
        pass

    return {
        "provider": {
            "configured": bool(provider_name and has_key),
            "name": provider_info.get("name", provider_name),
            "model": provider_model,
        },
        "messaging": {
            "configured": messaging_configured,
        },
        "soul": {
            "configured": has_soul,
            "summary": soul_summary,
        },
        "daemon": {
            "running": daemon_running,
        },
        "complete": bool(provider_name and has_key),  # Minimum requirement
        "fully_setup": bool(provider_name and has_key and has_soul),
    }


# ── Soul Endpoints ─────────────────────────────────────

@router.get("/setup/soul")
async def get_soul():
    """Get the current soul file content."""
    soul_path = Path.home() / ".unclaude" / "proactive.yaml"

    if not soul_path.exists():
        return {"exists": False, "content": None, "parsed": None}

    try:
        import yaml
        content = soul_path.read_text()
        parsed = yaml.safe_load(content)
        return {"exists": True, "content": content, "parsed": parsed}
    except Exception as e:
        return {"exists": True, "content": soul_path.read_text(), "parsed": None, "error": str(e)}


@router.post("/setup/soul/generate")
async def generate_soul_from_description(req: SoulGenerateRequest):
    """Generate a soul YAML from a natural language description using the configured LLM."""
    if not req.description.strip():
        raise HTTPException(
            status_code=400, detail="Description cannot be empty")

    try:
        from unclaude.onboarding import _generate_soul_from_description
        result = _generate_soul_from_description(
            req.description, req.agent_name)

        if not result:
            raise HTTPException(
                status_code=500, detail="Soul generation returned empty result")

        return {"success": True, "content": result}
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Missing dependency: {e}")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")


@router.post("/setup/soul/preset")
async def generate_soul_from_presets(req: SoulPickListRequest):
    """Generate a soul from preset behavior selections."""
    from unclaude.onboarding import generate_soul

    content = generate_soul(
        agent_name=req.agent_name,
        tagline=req.tagline,
        enabled_behaviors=req.behaviors,
    )

    return {"success": True, "content": content}


@router.post("/setup/soul/save")
async def save_soul_content(req: SoulSaveRequest):
    """Save soul YAML content to ~/.unclaude/proactive.yaml."""
    import yaml

    # Validate it's parseable YAML
    try:
        parsed = yaml.safe_load(req.content)
        if not isinstance(parsed, dict):
            raise HTTPException(
                status_code=400, detail="Invalid YAML: must be a dictionary")
        if "behaviors" not in parsed:
            raise HTTPException(
                status_code=400, detail="Invalid soul: missing 'behaviors' section")
    except yaml.YAMLError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid YAML syntax: {e}")

    from unclaude.onboarding import save_soul
    path = save_soul(req.content)

    return {"success": True, "path": str(path)}


@router.get("/setup/soul/behaviors")
async def get_default_behaviors():
    """Get the list of default behaviors available for soul creation."""
    from unclaude.onboarding import DEFAULT_BEHAVIORS

    return {
        "behaviors": [
            {
                "key": b["key"],
                "name": b["name"],
                "label": b["label"],
                "interval": b["interval"],
                "active_hours": b["active_hours"],
                "priority": b["priority"],
                "default": b["default"],
                "notify": b["notify"],
            }
            for b in DEFAULT_BEHAVIORS
        ]
    }


# ── Daemon Control ─────────────────────────────────────

@router.get("/setup/daemon/status")
async def get_daemon_status():
    """Get daemon running status."""
    try:
        from unclaude.autonomous.daemon import AgentDaemon
        daemon = AgentDaemon(project_path=Path.cwd())
        running = daemon.is_running()
        pid = None

        if running:
            pid_file = Path.home() / ".unclaude" / "daemon.pid"
            if pid_file.exists():
                try:
                    pid = int(pid_file.read_text().strip())
                except ValueError:
                    pass

        return {"running": running, "pid": pid}
    except Exception as e:
        return {"running": False, "pid": None, "error": str(e)}


@router.post("/setup/daemon/start")
async def start_daemon():
    """Start the agent daemon in the background."""
    try:
        from unclaude.autonomous.daemon import AgentDaemon
        daemon = AgentDaemon(project_path=Path.cwd())

        if daemon.is_running():
            return {"success": True, "message": "Daemon is already running", "already_running": True}

        pid = daemon.start_background()
        return {"success": True, "pid": pid, "message": f"Daemon started (pid {pid})"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to start daemon: {e}")


@router.post("/setup/daemon/stop")
async def stop_daemon():
    """Stop the running daemon."""
    try:
        from unclaude.autonomous.daemon import AgentDaemon
        daemon = AgentDaemon(project_path=Path.cwd())

        if not daemon.is_running():
            return {"success": True, "message": "Daemon is not running"}

        daemon.stop()
        return {"success": True, "message": "Daemon stopped"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to stop daemon: {e}")
