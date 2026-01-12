"""Settings API routes."""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class ProviderConfig(BaseModel):
    """Provider configuration."""
    name: str
    api_key: str | None = None
    model: str | None = None


class SettingsUpdate(BaseModel):
    """Settings update request."""
    default_provider: str | None = None
    provider_model: dict[str, str] | None = None  # {provider: model}
    api_key: dict[str, str] | None = None  # {provider: api_key}


@router.get("/settings")
async def get_settings():
    """Get current settings."""
    from unclaude.onboarding import PROVIDERS, get_models_for_provider, load_config, get_credentials_path
    
    config = load_config()
    
    # Load credentials to check which providers have keys
    credentials = {}
    creds_path = get_credentials_path()
    if creds_path.exists():
        import yaml
        with open(creds_path) as f:
            credentials = yaml.safe_load(f) or {}
    
    settings = {
        "default_provider": config.get("default_provider", "gemini"),
        "providers": {},
        "config_path": str(Path.home() / ".unclaude" / "config.yaml"),
        "config_exists": (Path.home() / ".unclaude" / "config.yaml").exists(),
    }
    
    # Build provider info with current model and key status
    for provider_name, provider_info in PROVIDERS.items():
        provider_config = config.get("providers", {}).get(provider_name, {})
        env_var = provider_info.get("env_var")
        
        settings["providers"][provider_name] = {
            "display_name": provider_info["name"],
            "model": provider_config.get("model", provider_info["default_model"]),
            "has_key": bool(credentials.get(provider_name) or (env_var and os.environ.get(env_var))),
            "env_var": env_var,
        }
    
    return settings


@router.get("/settings/providers")
async def get_available_providers():
    """Get list of available providers with dynamic model lists."""
    from unclaude.onboarding import PROVIDERS, get_models_for_provider
    
    providers = []
    for name, info in PROVIDERS.items():
        # Get dynamic model list
        models = get_models_for_provider(name)
        
        providers.append({
            "name": name,
            "display_name": info["name"],
            "models": models,
            "default_model": info["default_model"],
            "env_var": info.get("env_var"),
            "docs_url": info.get("docs_url"),
        })
    
    return {"providers": providers}


@router.get("/settings/models/{provider}")
async def get_provider_models(provider: str):
    """Get available models for a specific provider."""
    from unclaude.onboarding import PROVIDERS, get_models_for_provider, get_all_custom_models
    
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found")
    
    models = get_models_for_provider(provider)
    custom_models = get_all_custom_models().get(provider, [])
    
    return {
        "provider": provider,
        "models": models,
        "custom_models": custom_models,
        "default": PROVIDERS[provider]["default_model"],
    }


class CustomModelRequest(BaseModel):
    """Request to add a custom model."""
    provider: str
    model: str


@router.post("/settings/models/custom")
async def add_custom_model_endpoint(request: CustomModelRequest):
    """Add a custom model that doesn't exist in LiteLLM mapping."""
    from unclaude.onboarding import PROVIDERS, add_custom_model
    
    if request.provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Provider '{request.provider}' not found")
    
    if not request.model or not request.model.strip():
        raise HTTPException(status_code=400, detail="Model name is required")
    
    success = add_custom_model(request.provider, request.model.strip())
    
    if success:
        return {"success": True, "message": f"Custom model '{request.model}' added for {request.provider}"}
    else:
        return {"success": False, "message": f"Model '{request.model}' already exists"}


@router.delete("/settings/models/custom/{provider}/{model}")
async def remove_custom_model_endpoint(provider: str, model: str):
    """Remove a custom model."""
    from unclaude.onboarding import PROVIDERS, remove_custom_model
    
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found")
    
    success = remove_custom_model(provider, model)
    
    if success:
        return {"success": True, "message": f"Custom model '{model}' removed from {provider}"}
    else:
        raise HTTPException(status_code=404, detail=f"Custom model '{model}' not found for {provider}")


@router.get("/settings/models/custom")
async def list_custom_models():
    """List all custom models."""
    from unclaude.onboarding import get_all_custom_models
    return {"custom_models": get_all_custom_models()}


@router.post("/settings/models/refresh/{provider}")
async def refresh_models(provider: str):
    """Force refresh model list from LiteLLM (clears cache)."""
    from unclaude.onboarding import PROVIDERS, get_models_for_provider
    
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found")
    
    # Get fresh models (include_custom=False to see base LiteLLM models)
    models = get_models_for_provider(provider, include_custom=False)
    
    return {
        "provider": provider,
        "models": models,
        "count": len(models),
    }


@router.post("/settings")
async def update_settings(request: SettingsUpdate):
    """Update settings (default provider, models)."""
    import yaml
    from unclaude.onboarding import load_config, get_config_path, get_credentials_path
    
    config = load_config()
    changed = False
    
    # Update default provider
    if request.default_provider:
        config["default_provider"] = request.default_provider
        changed = True
    
    # Update provider models
    if request.provider_model:
        if "providers" not in config:
            config["providers"] = {}
        for provider_name, model in request.provider_model.items():
            if provider_name not in config["providers"]:
                config["providers"][provider_name] = {}
            config["providers"][provider_name]["model"] = model
            changed = True
    
    # Update API keys (stored in credentials file)
    if request.api_key:
        creds_path = get_credentials_path()
        credentials = {}
        if creds_path.exists():
            with open(creds_path) as f:
                credentials = yaml.safe_load(f) or {}
        
        for provider_name, api_key in request.api_key.items():
            if api_key:  # Only update if key is provided
                credentials[provider_name] = api_key
        
        # Save credentials
        with open(creds_path, "w") as f:
            yaml.dump(credentials, f, default_flow_style=False)
        os.chmod(creds_path, 0o600)  # Secure permissions
        changed = True
    
    # Save config
    if changed:
        config_path = get_config_path()
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
        
        return {"success": True, "message": "Settings saved"}
    
    return {"success": True, "message": "No changes to save"}


@router.delete("/settings/api-key/{provider}")
async def delete_api_key(provider: str):
    """Delete an API key for a provider."""
    import yaml
    from unclaude.onboarding import get_credentials_path
    
    creds_path = get_credentials_path()
    if not creds_path.exists():
        raise HTTPException(status_code=404, detail="No credentials found")
    
    with open(creds_path) as f:
        credentials = yaml.safe_load(f) or {}
    
    if provider in credentials:
        del credentials[provider]
        with open(creds_path, "w") as f:
            yaml.dump(credentials, f, default_flow_style=False)
        return {"success": True, "message": f"API key for {provider} deleted"}
    
    raise HTTPException(status_code=404, detail=f"No API key found for {provider}")


@router.get("/settings/hooks")
async def get_hooks():
    """Get hooks configuration."""
    hooks_path = Path.cwd() / ".unclaude" / "hooks.yaml"
    
    if not hooks_path.exists():
        return {"hooks": [], "path": str(hooks_path), "exists": False}
    
    try:
        import yaml
        with open(hooks_path) as f:
            data = yaml.safe_load(f) or {}
        return {
            "hooks": data.get("hooks", []),
            "path": str(hooks_path),
            "exists": True,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/settings/skills")
async def get_skills():
    """Get available skills."""
    from unclaude.skills import SkillsEngine
    
    engine = SkillsEngine()
    skills = engine.load_skills()
    
    return {
        "skills": [
            {
                "name": skill.name,
                "description": skill.description,
                "steps": len(skill.steps),
            }
            for skill in skills.values()
        ]
    }
