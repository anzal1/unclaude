"""Background agent execution for non-blocking tasks."""

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()


@dataclass
class BackgroundJob:
    """Represents a background agent job."""
    
    job_id: str
    task: str
    status: str  # "running", "completed", "failed"
    started_at: datetime
    completed_at: datetime | None = None
    result: str | None = None
    error: str | None = None


class BackgroundAgentManager:
    """Manages background agent execution."""

    def __init__(self):
        self.jobs_dir = Path.home() / ".unclaude" / "background_jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def _get_job_file(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}.json"

    def _save_job(self, job: BackgroundJob) -> None:
        """Save job state to file."""
        with open(self._get_job_file(job.job_id), "w") as f:
            json.dump({
                "job_id": job.job_id,
                "task": job.task,
                "status": job.status,
                "started_at": job.started_at.isoformat(),
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "result": job.result,
                "error": job.error,
            }, f, indent=2)

    def _load_job(self, job_id: str) -> BackgroundJob | None:
        """Load job state from file."""
        job_file = self._get_job_file(job_id)
        if not job_file.exists():
            return None

        with open(job_file) as f:
            data = json.load(f)
            return BackgroundJob(
                job_id=data["job_id"],
                task=data["task"],
                status=data["status"],
                started_at=datetime.fromisoformat(data["started_at"]),
                completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
                result=data.get("result"),
                error=data.get("error"),
            )

    def start_background_task(self, task: str) -> str:
        """Start a task in the background.

        Args:
            task: The task description to run.

        Returns:
            Job ID for tracking.
        """
        import uuid
        job_id = str(uuid.uuid4())[:8]

        # Create job record
        job = BackgroundJob(
            job_id=job_id,
            task=task,
            status="running",
            started_at=datetime.now(),
        )
        self._save_job(job)

        # Start background process
        # Escape task string for embedding in Python script
        escaped_task = task.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'")
        
        script = f'''
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add unclaude src to path (background.py -> agent -> unclaude -> src)
sys.path.insert(0, "{Path(__file__).parent.parent.parent}")

from unclaude.onboarding import load_config, load_credential, PROVIDERS
from unclaude.agent.loop import AgentLoop
from unclaude.providers.llm import Provider

async def run_task():
    try:
        # Load configuration and API key
        config = load_config()
        provider_name = config.get("default_provider", "gemini")
        provider_config = config.get("providers", {{}}).get(provider_name, {{}})
        model = provider_config.get("model")
        
        # Load and set API key
        api_key = load_credential(provider_name)
        if api_key:
            provider_info = PROVIDERS.get(provider_name, {{}})
            env_var = provider_info.get("env_var")
            if env_var:
                os.environ[env_var] = api_key
        
        # Create provider with config
        llm_provider = Provider(provider_name)
        if model:
            llm_provider.config.model = model
        
        agent = AgentLoop(provider=llm_provider, enable_memory=True)
        result = await agent.run("{escaped_task}")
        
        # Save result with runtime timestamp
        with open("{self._get_job_file(job_id)}", "r+") as f:
            data = json.load(f)
            data["status"] = "completed"
            data["completed_at"] = datetime.now().isoformat()
            data["result"] = result
            f.seek(0)
            json.dump(data, f, indent=2)
            f.truncate()
    except Exception as e:
        with open("{self._get_job_file(job_id)}", "r+") as f:
            data = json.load(f)
            data["status"] = "failed"
            data["completed_at"] = datetime.now().isoformat()
            data["error"] = str(e)
            f.seek(0)
            json.dump(data, f, indent=2)
            f.truncate()

asyncio.run(run_task())
'''

        # Write script to temp file
        script_file = self.jobs_dir / f"{job_id}_script.py"
        script_file.write_text(script)

        # Start detached process
        subprocess.Popen(
            [sys.executable, str(script_file)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            cwd=os.getcwd(),
        )

        return job_id

    def get_job_status(self, job_id: str) -> BackgroundJob | None:
        """Get the status of a background job."""
        return self._load_job(job_id)

    def list_jobs(self, limit: int = 10) -> list[BackgroundJob]:
        """List recent jobs."""
        jobs = []
        for job_file in sorted(self.jobs_dir.glob("*.json"), reverse=True)[:limit]:
            job_id = job_file.stem
            job = self._load_job(job_id)
            if job:
                jobs.append(job)
        return jobs


# CLI additions for background agents
def add_background_commands(app: Any) -> None:
    """Add background agent commands to CLI app."""
    import typer

    @app.command()
    def background(
        task: str = typer.Argument(..., help="Task to run in background"),
    ) -> None:
        """Run a task in the background without blocking."""
        manager = BackgroundAgentManager()
        job_id = manager.start_background_task(task)
        console.print(f"[green]Started background job:[/green] {job_id}")
        console.print(f"[dim]Check status with: unclaude jobs {job_id}[/dim]")

    @app.command()
    def jobs(
        job_id: str = typer.Argument(None, help="Specific job ID to check"),
    ) -> None:
        """List or check status of background jobs."""
        manager = BackgroundAgentManager()

        if job_id:
            job = manager.get_job_status(job_id)
            if not job:
                console.print(f"[red]Job not found: {job_id}[/red]")
                return

            console.print(f"\n[bold]Job {job.job_id}[/bold]")
            console.print(f"Task: {job.task}")
            console.print(f"Status: {job.status}")
            console.print(f"Started: {job.started_at}")
            if job.completed_at:
                console.print(f"Completed: {job.completed_at}")
            if job.result:
                console.print(f"Result:\n{job.result[:500]}...")
            if job.error:
                console.print(f"[red]Error: {job.error}[/red]")
        else:
            jobs = manager.list_jobs()
            if not jobs:
                console.print("[yellow]No background jobs found.[/yellow]")
                return

            console.print("\n[bold]Recent Background Jobs:[/bold]\n")
            for job in jobs:
                status_color = "green" if job.status == "completed" else "yellow" if job.status == "running" else "red"
                console.print(f"  [{status_color}]{job.job_id}[/{status_color}] - {job.task[:50]}... ({job.status})")
