"""Background jobs API routes."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class JobCreateRequest(BaseModel):
    """Request to create a background job."""
    task: str


@router.get("/jobs")
async def list_jobs(limit: int = 20):
    """List background jobs."""
    from unclaude.agent.background import BackgroundAgentManager
    
    manager = BackgroundAgentManager()
    jobs = manager.list_jobs(limit=limit)
    
    return {
        "jobs": [
            {
                "job_id": job.job_id,
                "task": job.task,
                "status": job.status,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "result": job.result[:500] if job.result else None,
                "error": job.error,
            }
            for job in jobs
        ]
    }


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Get a specific job by ID."""
    from unclaude.agent.background import BackgroundAgentManager
    
    manager = BackgroundAgentManager()
    job = manager.get_job_status(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "job_id": job.job_id,
        "task": job.task,
        "status": job.status,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "result": job.result,
        "error": job.error,
    }


@router.post("/jobs")
async def create_job(request: JobCreateRequest):
    """Create a new background job."""
    from unclaude.agent.background import BackgroundAgentManager
    
    manager = BackgroundAgentManager()
    job_id = manager.start_background_task(request.task)
    
    return {
        "success": True,
        "job_id": job_id,
        "message": f"Background job started: {job_id}"
    }


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    """Cancel a running job (mark as cancelled)."""
    import json
    from pathlib import Path
    
    jobs_dir = Path.home() / ".unclaude" / "background_jobs"
    job_file = jobs_dir / f"{job_id}.json"
    
    if not job_file.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    
    try:
        with open(job_file, "r+") as f:
            data = json.load(f)
            if data["status"] == "running":
                data["status"] = "cancelled"
                data["error"] = "Cancelled by user"
                f.seek(0)
                json.dump(data, f, indent=2)
                f.truncate()
                return {"success": True, "message": "Job cancelled"}
            else:
                return {"success": False, "message": f"Job is already {data['status']}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
