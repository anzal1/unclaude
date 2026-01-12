"""Skills API routes."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


@router.get("/skills")
async def list_skills():
    """List available skills."""
    from unclaude.skills import SkillsEngine
    
    engine = SkillsEngine()
    skills = engine.load_skills()
    
    return {
        "skills": [
            {
                "name": name,
                "description": skill.description,
                "steps": len(skill.steps),
                "steps_preview": [s.get("name", s.get("action", "step")) for s in skill.steps[:3]],
            }
            for name, skill in skills.items()
        ]
    }


@router.get("/skills/{name}")
async def get_skill(name: str):
    """Get details about a specific skill."""
    from unclaude.skills import SkillsEngine
    
    engine = SkillsEngine()
    skill = engine.get_skill(name)
    
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    
    return {
        "name": skill.name,
        "description": skill.description,
        "steps": skill.steps,
    }


class RunSkillRequest(BaseModel):
    """Request to run a skill."""
    variables: dict = {}


@router.post("/skills/{name}/run")
async def run_skill(name: str, request: RunSkillRequest = None):
    """Run a skill by name."""
    import asyncio
    from unclaude.skills import SkillsEngine
    from unclaude.agent import AgentLoop
    from unclaude.onboarding import ensure_configured, get_provider_api_key, PROVIDERS
    import os
    
    engine = SkillsEngine()
    skill = engine.get_skill(name)
    
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    
    # Generate prompt for the skill
    prompt = engine.generate_skill_prompt(skill)
    
    try:
        # Get provider config
        config = ensure_configured()
        use_provider = config.get("default_provider", "gemini")
        provider_config = config.get("providers", {}).get(use_provider, {})
        use_model = provider_config.get("model")
        
        # Set API key
        api_key = get_provider_api_key(use_provider)
        if api_key:
            provider_info = PROVIDERS.get(use_provider, {})
            env_var = provider_info.get("env_var")
            if env_var:
                os.environ[env_var] = api_key
        
        # Create provider and agent
        from unclaude.providers.llm import Provider as LLMProvider
        llm_provider = LLMProvider(use_provider)
        if use_model:
            llm_provider.config.model = use_model
        
        agent = AgentLoop(provider=llm_provider)
        response = await agent.run(prompt)
        
        return {
            "success": True,
            "skill": name,
            "response": response,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CreateSkillRequest(BaseModel):
    """Request to create a new skill."""
    name: str
    description: str = ""


@router.post("/skills/create")
async def create_skill(request: CreateSkillRequest):
    """Create a new skill template."""
    from unclaude.skills import create_skill_template
    
    if not request.name or not request.name.strip():
        raise HTTPException(status_code=400, detail="Skill name is required")
    
    skill_path = Path.home() / ".unclaude" / "skills" / f"{request.name.strip()}.yaml"
    
    if skill_path.exists():
        raise HTTPException(status_code=400, detail=f"Skill '{request.name}' already exists")
    
    create_skill_template(request.name, skill_path)
    
    return {
        "success": True,
        "message": f"Skill '{request.name}' created",
        "path": str(skill_path),
    }
