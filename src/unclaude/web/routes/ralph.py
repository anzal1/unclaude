"""Ralph Wiggum mode API routes."""

import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class RalphStartRequest(BaseModel):
    """Request to start Ralph Wiggum mode."""
    task: str
    max_iterations: int = 50
    max_cost: float = 10.0
    feedback_commands: list[str] = ["npm test"]


class RalphJob:
    """In-memory storage for Ralph jobs (simple implementation)."""
    jobs: dict = {}


@router.post("/ralph/start")
async def start_ralph(request: RalphStartRequest):
    """Start Ralph Wiggum autonomous mode."""
    import uuid
    from datetime import datetime
    
    job_id = str(uuid.uuid4())[:8]
    
    # Store job info
    RalphJob.jobs[job_id] = {
        "id": job_id,
        "task": request.task,
        "status": "starting",
        "started_at": datetime.now().isoformat(),
        "max_iterations": request.max_iterations,
        "max_cost": request.max_cost,
        "feedback_commands": request.feedback_commands,
        "current_iteration": 0,
        "result": None,
        "error": None,
    }
    
    # Start background task (in real impl, would use BackgroundAgentManager)
    async def run_ralph_task():
        try:
            RalphJob.jobs[job_id]["status"] = "running"
            
            # Import and run Ralph mode
            from unclaude.agent import AgentLoop, RalphWiggumMode
            from unclaude.onboarding import ensure_configured, get_provider_api_key, PROVIDERS
            import os
            
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
            ralph_mode = RalphWiggumMode(
                agent_loop=agent,
                feedback_commands=request.feedback_commands,
                max_iterations=request.max_iterations,
                max_cost=request.max_cost,
            )
            
            result = await ralph_mode.run(request.task)
            
            RalphJob.jobs[job_id]["status"] = "completed" if result.success else "failed"
            RalphJob.jobs[job_id]["result"] = {
                "success": result.success,
                "iterations": result.iterations,
                "total_cost": result.total_cost,
                "error": result.error,
            }
            
        except Exception as e:
            RalphJob.jobs[job_id]["status"] = "failed"
            RalphJob.jobs[job_id]["error"] = str(e)
    
    # Start in background
    asyncio.create_task(run_ralph_task())
    
    return {
        "success": True,
        "job_id": job_id,
        "message": f"Ralph mode started for task: {request.task[:50]}...",
    }


@router.get("/ralph/status/{job_id}")
async def get_ralph_status(job_id: str):
    """Get Ralph job status."""
    if job_id not in RalphJob.jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    
    return RalphJob.jobs[job_id]


@router.get("/ralph/jobs")
async def list_ralph_jobs():
    """List all Ralph jobs."""
    return {"jobs": list(RalphJob.jobs.values())}


@router.post("/ralph/stop/{job_id}")
async def stop_ralph(job_id: str):
    """Stop a running Ralph job."""
    if job_id not in RalphJob.jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    
    job = RalphJob.jobs[job_id]
    if job["status"] == "running":
        job["status"] = "stopped"
        return {"success": True, "message": f"Job {job_id} stop requested"}
    else:
        return {"success": False, "message": f"Job {job_id} is not running (status: {job['status']})"}
