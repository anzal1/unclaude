"""24/7 autonomous agent daemon.

This is the core of UnClaude's autonomous mode. Instead of users
typing commands, the daemon:

1. Watches for tasks (file changes, TASKS.md, webhooks, git events)
2. Picks up tasks from a priority queue
3. Spawns the right agent (or swarm) to handle each task
4. Reports results via notifications / dashboard
5. Learns from outcomes to improve over time

Usage:
    unclaude agent start          # Start daemon in background
    unclaude agent start --fg     # Start in foreground (for debugging)
    unclaude agent status         # Check daemon status
    unclaude agent stop           # Stop daemon
    unclaude agent task "fix X"   # Submit a task to the running daemon
"""

import asyncio
import json
import os
import re
import signal
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

console = Console()


class DaemonStatus(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    IDLE = "idle"
    PROCESSING = "processing"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class TaskPriority(str, Enum):
    CRITICAL = "critical"   # Security fixes, production bugs
    HIGH = "high"           # Feature requests, important refactors
    NORMAL = "normal"       # Regular tasks
    LOW = "low"             # Nice-to-haves, optimizations
    BACKGROUND = "background"  # Long-running, low-priority


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


@dataclass
class DaemonTask:
    """A task in the daemon's queue."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.QUEUED
    source: str = "manual"  # manual, file_watch, webhook, git, schedule
    project_path: str = ""

    # Execution
    result: str | None = None
    error: str | None = None
    agent_id: str | None = None
    iterations: int = 0
    cost_usd: float = 0.0

    # Timing
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None

    # Retry
    max_retries: int = 2
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "source": self.source,
            "project_path": self.project_path,
            "result": self.result,
            "error": self.error,
            "agent_id": self.agent_id,
            "iterations": self.iterations,
            "cost_usd": self.cost_usd,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DaemonTask":
        return cls(
            task_id=d.get("task_id", str(uuid.uuid4())[:8]),
            description=d.get("description", ""),
            priority=TaskPriority(d.get("priority", "normal")),
            status=TaskStatus(d.get("status", "queued")),
            source=d.get("source", "manual"),
            project_path=d.get("project_path", ""),
            result=d.get("result"),
            error=d.get("error"),
            agent_id=d.get("agent_id"),
            iterations=d.get("iterations", 0),
            cost_usd=d.get("cost_usd", 0.0),
            created_at=d.get("created_at", time.time()),
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            retry_count=d.get("retry_count", 0),
        )


class TaskQueue:
    """Persistent priority task queue backed by JSON file."""

    def __init__(self, queue_dir: Path | None = None):
        self.queue_dir = queue_dir or (Path.home() / ".unclaude" / "daemon")
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.queue_file = self.queue_dir / "task_queue.json"
        self._tasks: list[DaemonTask] = []
        self._load()

    def _load(self) -> None:
        if self.queue_file.exists():
            try:
                with open(self.queue_file) as f:
                    data = json.load(f)
                self._tasks = [DaemonTask.from_dict(t) for t in data]
            except (json.JSONDecodeError, Exception):
                self._tasks = []

    def _save(self) -> None:
        with open(self.queue_file, "w") as f:
            json.dump([t.to_dict() for t in self._tasks], f, indent=2)

    def push(self, task: DaemonTask) -> str:
        """Add a task to the queue. Returns task_id."""
        self._tasks.append(task)
        self._save()
        return task.task_id

    def pop(self) -> DaemonTask | None:
        """Get the highest-priority queued task.

        Re-reads from disk to pick up tasks added by other code paths
        (e.g. Telegram handler pushing tasks via a separate TaskQueue instance).
        """
        self._load()  # Refresh from disk
        priority_order = [
            TaskPriority.CRITICAL,
            TaskPriority.HIGH,
            TaskPriority.NORMAL,
            TaskPriority.LOW,
            TaskPriority.BACKGROUND,
        ]
        for priority in priority_order:
            for task in self._tasks:
                if task.status == TaskStatus.QUEUED and task.priority == priority:
                    task.status = TaskStatus.RUNNING
                    task.started_at = time.time()
                    self._save()
                    return task
        return None

    def complete(self, task_id: str, result: str) -> None:
        for task in self._tasks:
            if task.task_id == task_id:
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.completed_at = time.time()
                self._save()
                return

    def fail(self, task_id: str, error: str) -> None:
        for task in self._tasks:
            if task.task_id == task_id:
                if task.retry_count < task.max_retries:
                    task.status = TaskStatus.QUEUED
                    task.retry_count += 1
                    task.error = error
                else:
                    task.status = TaskStatus.FAILED
                    task.error = error
                    task.completed_at = time.time()
                self._save()
                return

    def get(self, task_id: str) -> DaemonTask | None:
        for task in self._tasks:
            if task.task_id == task_id:
                return task
        return None

    def list_tasks(
        self, status: TaskStatus | None = None, limit: int = 50
    ) -> list[DaemonTask]:
        tasks = self._tasks
        if status:
            tasks = [t for t in tasks if t.status == status]
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)[:limit]

    def pending_count(self) -> int:
        return sum(1 for t in self._tasks if t.status == TaskStatus.QUEUED)


class AgentDaemon:
    """The 24/7 autonomous agent daemon.

    Runs as a long-lived process that:
    1. Monitors the task queue
    2. Watches for file changes (TASKS.md, TODO.md, .unclaude/tasks/)
    3. Processes tasks using the EnhancedAgentLoop
    4. Reports results and learns from outcomes

    Start with:
        daemon = AgentDaemon(project_path=Path.cwd())
        await daemon.run()
    """

    def __init__(
        self,
        project_path: Path | None = None,
        poll_interval: float = 5.0,
        max_concurrent: int = 1,
    ):
        self.project_path = project_path or Path.cwd()
        self.poll_interval = poll_interval
        self.max_concurrent = max_concurrent

        # State
        self.status = DaemonStatus.STOPPED
        self.state_dir = Path.home() / ".unclaude" / "daemon"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.pid_file = self.state_dir / "daemon.pid"
        self.status_file = self.state_dir / "status.json"

        # Task queue
        self.queue = TaskQueue(self.state_dir)

        # Active tasks
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._shutdown_event = asyncio.Event()

        # Stats
        self._tasks_completed = 0
        self._tasks_failed = 0
        self._total_cost = 0.0
        self._started_at: float | None = None

    def submit_task(
        self,
        description: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        source: str = "manual",
    ) -> str:
        """Submit a task to the daemon queue."""
        task = DaemonTask(
            description=description,
            priority=priority,
            source=source,
            project_path=str(self.project_path),
        )
        task_id = self.queue.push(task)
        return task_id

    def _write_status(self) -> None:
        """Write daemon status to file (for CLI queries)."""
        status_data = {
            "status": self.status.value,
            "pid": os.getpid(),
            "project_path": str(self.project_path),
            "started_at": self._started_at,
            "tasks_completed": self._tasks_completed,
            "tasks_failed": self._tasks_failed,
            "total_cost_usd": self._total_cost,
            "queue_pending": self.queue.pending_count(),
            "active_tasks": len(self._active_tasks),
            "updated_at": time.time(),
        }
        with open(self.status_file, "w") as f:
            json.dump(status_data, f, indent=2)

    @staticmethod
    def read_status() -> dict[str, Any] | None:
        """Read daemon status from file (for CLI)."""
        status_file = Path.home() / ".unclaude" / "daemon" / "status.json"
        if not status_file.exists():
            return None
        try:
            with open(status_file) as f:
                return json.load(f)
        except Exception:
            return None

    async def _process_task(self, task: DaemonTask) -> None:
        """Process a single task using the EnhancedAgentLoop."""
        from unclaude.agent.enhanced_loop import EnhancedAgentLoop
        from unclaude.providers.llm import Provider
        from unclaude.config import get_settings
        from unclaude.onboarding import load_config, load_credential, PROVIDERS

        task_start = time.time()
        console.print()
        console.print(
            f"[bold cyan]>>> Task picked up:[/bold cyan] [white]{task.task_id}[/white]")
        console.print(
            f"    [dim]Priority:[/dim] {task.priority.value} | [dim]Source:[/dim] {task.source}")
        console.print(
            f"    [dim]Description:[/dim] {task.description[:120]}{'...' if len(task.description) > 120 else ''}")
        console.print(
            f"    [dim]Started at:[/dim] {datetime.now().strftime('%H:%M:%S')}")
        console.print()

        try:
            # Load config and create provider
            config = load_config()
            provider_name = config.get("default_provider", "gemini")
            provider_config = config.get(
                "providers", {}).get(provider_name, {})
            model = provider_config.get("model")

            api_key = load_credential(provider_name)
            if api_key:
                provider_info = PROVIDERS.get(provider_name, {})
                env_var = provider_info.get("env_var")
                if env_var:
                    os.environ[env_var] = api_key

            llm_provider = Provider(provider_name)
            if model:
                llm_provider.config.model = model

            console.print(
                f"    [dim]Using provider:[/dim] {provider_name} ({model or 'default model'})")

            settings = get_settings()

            # Create agent with autonomous profile
            agent = EnhancedAgentLoop(
                provider=llm_provider,
                security_profile=settings.security.profile,
                project_path=Path(
                    task.project_path) if task.project_path else self.project_path,
                preferred_provider=provider_name,
            )

            # Auto-approve all tool calls in daemon mode (no human at the keyboard)
            agent._auto_approve_all = True

            # Wire task ID for usage tracking
            llm_provider._task_id = task.task_id
            llm_provider._request_type = "daemon"

            console.print(
                f"    [dim]Agent initialized, executing (auto-approve on)...[/dim]")

            # Enhance task description with context for messaging tasks
            task_description = task.description
            if task.source.startswith("messaging:"):
                task_description = (
                    f"{task.description}\n\n"
                    f"[Context: This task was sent by the user via {task.source.split(':')[1]}. "
                    f"When they say 'my system', 'my computer', 'my files', they mean their "
                    f"home directory ({Path.home()}), NOT the project directory. "
                    f"Search ~/Documents, ~/Downloads, ~/Desktop, ~/Pictures etc. "
                    f"Use `find` or `mdfind` (macOS Spotlight) for file searches. "
                    f"NEVER search .venv/, node_modules/, or __pycache__/.]"
                )

            # Run the task — agent has its own smart stuck-detection,
            # no hard timeout needed
            result = await agent.run(task_description)

            # Mark complete
            elapsed = time.time() - task_start
            self.queue.complete(task.task_id, result)
            self._tasks_completed += 1

            # Track cost from usage tracker
            try:
                from unclaude.usage import get_usage_tracker
                tracker = get_usage_tracker()
                task_summary = tracker.get_summary(
                    period="custom",
                    start_time=task_start,
                    end_time=time.time(),
                )
                task.cost_usd = task_summary.total_cost_usd
                self._total_cost += task.cost_usd
            except Exception:
                pass

            console.print()
            console.print(
                f"[bold green]<<< Task completed:[/bold green] [white]{task.task_id}[/white] ({elapsed:.1f}s)")
            if task.cost_usd > 0:
                console.print(
                    f"    [dim]Cost:[/dim] ${task.cost_usd:.6f}")
            # Show a preview of the result (first 500 chars)
            if result:
                preview = result[:500]
                if len(result) > 500:
                    preview += "..."
                console.print(f"    [dim]Result preview:[/dim]")
                for line in preview.splitlines()[:15]:
                    console.print(f"    [dim]{line}[/dim]")
                if len(result.splitlines()) > 15:
                    console.print(
                        f"    [dim]... ({len(result.splitlines())} total lines)[/dim]")
            console.print()

            # Notify via messaging (Telegram/WhatsApp)
            try:
                from unclaude.messaging import get_messenger
                messenger = get_messenger()
                await messenger.notify_task_complete(
                    task_id=task.task_id,
                    description=task.description,
                    result=result or "",
                    cost_usd=task.cost_usd,
                )
            except Exception:
                pass  # Don't let messaging failures affect the daemon

        except Exception as e:
            elapsed = time.time() - task_start
            self.queue.fail(task.task_id, str(e))
            self._tasks_failed += 1
            console.print()
            console.print(
                f"[bold red]!!! Task failed:[/bold red] [white]{task.task_id}[/white] ({elapsed:.1f}s)")
            console.print(f"    [red]Error: {str(e)[:200]}[/red]")
            console.print()

            # Notify via messaging
            try:
                from unclaude.messaging import get_messenger
                messenger = get_messenger()
                await messenger.notify_task_failed(
                    task_id=task.task_id,
                    description=task.description,
                    error=str(e),
                )
            except Exception:
                pass

        finally:
            self._active_tasks.pop(task.task_id, None)
            self._write_status()
            console.print(
                f"[dim]    Stats: {self._tasks_completed} completed, {self._tasks_failed} failed, {self.queue.pending_count()} pending[/dim]")

    async def _watch_task_files(self) -> None:
        """Watch for task files and auto-submit them.

        Watches:
        - .unclaude/tasks/*.md  → Each file becomes a task
        - TASKS.md              → Each unchecked checkbox becomes a task
        """
        tasks_dir = self.project_path / ".unclaude" / "tasks"
        tasks_md = self.project_path / "TASKS.md"
        processed_file = self.state_dir / "processed_tasks.json"

        # Load processed task tracking
        processed: set[str] = set()
        if processed_file.exists():
            try:
                with open(processed_file) as f:
                    processed = set(json.load(f))
            except Exception:
                pass

        def save_processed() -> None:
            with open(processed_file, "w") as f:
                json.dump(list(processed), f)

        while not self._shutdown_event.is_set():
            # Check .unclaude/tasks/ directory
            if tasks_dir.exists():
                for task_file in tasks_dir.glob("*.md"):
                    file_key = f"file:{task_file.name}:{task_file.stat().st_mtime}"
                    if file_key not in processed:
                        content = task_file.read_text().strip()
                        if content:
                            self.submit_task(
                                description=content,
                                source="file_watch",
                                priority=TaskPriority.NORMAL,
                            )
                            processed.add(file_key)
                            save_processed()

            # Check TASKS.md for unchecked checkboxes
            if tasks_md.exists():
                content = tasks_md.read_text()
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("- [ ] "):
                        task_text = stripped[6:].strip()
                        task_key = f"tasks_md:{task_text}"
                        if task_key not in processed and task_text:
                            self.submit_task(
                                description=task_text,
                                source="file_watch",
                                priority=TaskPriority.NORMAL,
                            )
                            processed.add(task_key)
                            save_processed()

            await asyncio.sleep(self.poll_interval * 2)

    # ── Proactive Engine ─────────────────────────────────────────
    # The soul of the agent: reads proactive.yaml and self-generates
    # tasks on schedule, so the agent acts without being asked.

    def _load_soul(self) -> dict[str, Any] | None:
        """Load the proactive.yaml soul file."""
        soul_path = Path.home() / ".unclaude" / "proactive.yaml"
        if not soul_path.exists():
            return None
        try:
            with open(soul_path) as f:
                return yaml.safe_load(f)
        except Exception as e:
            console.print(f"[red]Failed to load proactive.yaml: {e}[/red]")
            return None

    def _parse_interval(self, interval_str: str) -> float:
        """Parse interval string like '4h', '30m', '1d' to seconds."""
        match = re.match(
            r'^(\d+(?:\.\d+)?)\s*([smhd])$', interval_str.strip().lower())
        if not match:
            console.print(
                f"[yellow]Invalid interval '{interval_str}', defaulting to 1h[/yellow]")
            return 3600.0
        value = float(match.group(1))
        unit = match.group(2)
        multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        return value * multipliers[unit]

    def _is_in_active_hours(self, active_hours: Any) -> bool:
        """Check if current time is within active hours."""
        if active_hours == "always" or active_hours is None:
            return True
        if isinstance(active_hours, list) and len(active_hours) == 2:
            now_hour = datetime.now().hour
            start, end = active_hours
            if start <= end:
                return start <= now_hour < end
            else:
                # Wraps midnight (e.g. [22, 6])
                return now_hour >= start or now_hour < end
        return True

    def _load_proactive_state(self) -> dict[str, float]:
        """Load last-run timestamps for proactive behaviors."""
        state_file = self.state_dir / "proactive_state.json"
        if state_file.exists():
            try:
                with open(state_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_proactive_state(self, state: dict[str, float]) -> None:
        """Save last-run timestamps for proactive behaviors."""
        state_file = self.state_dir / "proactive_state.json"
        with open(state_file, "w") as f:
            json.dump(state, f, indent=2)

    async def _proactive_loop(self) -> None:
        """The proactive engine — reads the soul file and self-generates tasks.

        This is what makes the agent autonomous. Without this, it just waits.
        With this, it has purpose.
        """
        # Wait a bit after startup before kicking in
        await asyncio.sleep(30)

        console.print("[bold magenta]Proactive engine started[/bold magenta]")

        # Track when the daemon last became idle
        last_busy_time = time.time()
        proactive_state = self._load_proactive_state()

        while not self._shutdown_event.is_set():
            try:
                # Reload soul file each cycle (allows live editing)
                soul = self._load_soul()
                if not soul:
                    await asyncio.sleep(60)
                    continue

                behaviors = soul.get("behaviors", [])
                check_interval = soul.get("check_interval_seconds", 60)
                idle_threshold = soul.get("idle_threshold_seconds", 120)

                # Only run proactive behaviors when idle
                if self._active_tasks:
                    last_busy_time = time.time()
                    await asyncio.sleep(check_interval)
                    continue

                idle_duration = time.time() - last_busy_time
                if idle_duration < idle_threshold:
                    await asyncio.sleep(check_interval)
                    continue

                # Check each behavior
                now = time.time()
                for behavior in behaviors:
                    if not isinstance(behavior, dict):
                        continue

                    name = behavior.get("name", "")
                    enabled = behavior.get("enabled", True)
                    task_desc = behavior.get("task", "")
                    interval_str = behavior.get("interval", "1h")
                    active_hours = behavior.get("active_hours", "always")
                    priority_str = behavior.get("priority", "background")
                    notify = behavior.get("notify", False)

                    if not enabled or not task_desc or not name:
                        continue

                    # Check active hours
                    if not self._is_in_active_hours(active_hours):
                        continue

                    # Check interval
                    interval_seconds = self._parse_interval(interval_str)
                    last_run = proactive_state.get(name, 0)
                    if (now - last_run) < interval_seconds:
                        continue

                    # Don't stack proactive tasks — skip if queue already has
                    # a proactive task from this behavior
                    already_queued = any(
                        t.source == f"proactive:{name}" and t.status == TaskStatus.QUEUED
                        for t in self.queue._tasks
                    )
                    if already_queued:
                        continue

                    # Map priority string
                    priority_map = {
                        "critical": TaskPriority.CRITICAL,
                        "high": TaskPriority.HIGH,
                        "normal": TaskPriority.NORMAL,
                        "low": TaskPriority.LOW,
                        "background": TaskPriority.BACKGROUND,
                    }
                    priority = priority_map.get(
                        priority_str, TaskPriority.BACKGROUND)

                    # Build the task description with soul context
                    identity = soul.get("identity", {})
                    drives = soul.get("drives", [])
                    boundaries = soul.get("boundaries", [])

                    soul_context = (
                        f"[Proactive Task: {name}]\n"
                        f"You are {identity.get('name', 'UnClaude')} — "
                        f"{identity.get('tagline', 'an autonomous AI agent')}.\n"
                    )
                    if drives:
                        soul_context += f"Your drives: {'; '.join(drives[:3])}\n"
                    if boundaries:
                        soul_context += (
                            f"BOUNDARIES (never violate): "
                            f"{'; '.join(boundaries)}\n"
                        )
                    if notify:
                        soul_context += (
                            "After completing this task, use the notify_owner tool "
                            "to briefly tell the owner what you did.\n"
                        )
                    soul_context += f"\n--- Task ---\n{task_desc}"

                    # Submit!
                    task_id = self.submit_task(
                        description=soul_context,
                        priority=priority,
                        source=f"proactive:{name}",
                    )

                    # Update state
                    proactive_state[name] = now
                    self._save_proactive_state(proactive_state)

                    now_str = datetime.now().strftime('%H:%M:%S')
                    console.print(
                        f"[magenta]{now_str} | Proactive:[/magenta] "
                        f"[white]{name}[/white] → queued as {task_id} "
                        f"(next in {interval_str})"
                    )

                    # Only submit one proactive task per cycle
                    # Let it finish before starting another
                    break

                await asyncio.sleep(check_interval)

            except Exception as e:
                console.print(f"[red]Proactive engine error: {e}[/red]")
                await asyncio.sleep(60)

    async def _main_loop(self) -> None:
        """Main daemon loop — pick tasks and process them."""
        heartbeat_counter = 0
        while not self._shutdown_event.is_set():
            # Check for available capacity
            if len(self._active_tasks) < self.max_concurrent:
                task = self.queue.pop()
                if task:
                    self.status = DaemonStatus.PROCESSING
                    self._write_status()
                    async_task = asyncio.create_task(self._process_task(task))
                    self._active_tasks[task.task_id] = async_task
                    heartbeat_counter = 0
                else:
                    if not self._active_tasks:
                        self.status = DaemonStatus.IDLE
                        self._write_status()

            # Periodic heartbeat every ~30s when idle
            heartbeat_counter += 1
            if heartbeat_counter % 6 == 0 and not self._active_tasks:
                now = datetime.now().strftime('%H:%M:%S')
                console.print(
                    f"[dim]{now} | Idle — waiting for tasks... ({self._tasks_completed} done, {self.queue.pending_count()} pending)[/dim]")

                # Send messaging heartbeat (has its own interval check)
                try:
                    from unclaude.messaging import get_messenger
                    messenger = get_messenger()
                    await messenger.send_heartbeat()
                except Exception:
                    pass

            await asyncio.sleep(self.poll_interval)

    async def run(self) -> None:
        """Run the daemon (foreground mode)."""
        self.status = DaemonStatus.STARTING
        self._started_at = time.time()

        # Write PID file
        with open(self.pid_file, "w") as f:
            f.write(str(os.getpid()))

        self._write_status()

        console.print(
            f"[bold green]Agent daemon started[/bold green] "
            f"(pid={os.getpid()}, project={self.project_path})"
        )
        console.print(
            f"[dim]Polling every {self.poll_interval}s | Max concurrent: {self.max_concurrent}[/dim]")
        console.print(
            f"[dim]Submit tasks: unclaude agent task \"your task here\"[/dim]")
        console.print(f"[dim]Or drop .md files in .unclaude/tasks/[/dim]")
        console.print(f"[dim]Or add checkboxes to TASKS.md[/dim]\n")

        # Show soul status
        soul = self._load_soul()
        if soul:
            identity = soul.get("identity", {})
            behaviors = soul.get("behaviors", [])
            enabled_behaviors = [b for b in behaviors if isinstance(
                b, dict) and b.get("enabled", True)]
            console.print(
                f"[bold magenta]Soul loaded:[/bold magenta] "
                f"{identity.get('name', 'UnClaude')} — {identity.get('tagline', '')}"
            )
            console.print(
                f"[magenta]{len(enabled_behaviors)} proactive behaviors active:[/magenta] "
                f"{', '.join(b.get('name', '?') for b in enabled_behaviors)}"
            )
            console.print()
        else:
            console.print(
                f"[dim]No proactive.yaml found — agent will only respond to submitted tasks[/dim]\n"
            )

        self.status = DaemonStatus.RUNNING
        self._write_status()

        # Handle shutdown signals
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: self._shutdown_event.set())

        try:
            # Build task list — always run main loop + file watcher + proactive engine
            tasks = [
                self._main_loop(),
                self._watch_task_files(),
                self._proactive_loop(),
            ]

            # Auto-start Telegram polling if configured
            messenger = None
            try:
                from unclaude.messaging import get_messenger, Platform, TelegramAdapter, create_chat_handler
                messenger = get_messenger()
                tg_adapter = messenger.adapters.get(Platform.TELEGRAM)
                if tg_adapter and isinstance(tg_adapter, TelegramAdapter) and tg_adapter.is_configured():
                    # Wire up LLM chat handler for free-form messages
                    chat_handler = create_chat_handler()
                    messenger.set_handler(chat_handler)
                    console.print(
                        "[bold cyan]📱 Telegram bot polling active (AI chat enabled)[/bold cyan]")
                    tasks.append(tg_adapter.start_polling(
                        messenger,
                        shutdown_event=self._shutdown_event,
                    ))
            except Exception as e:
                console.print(f"[dim]Telegram polling skipped: {e}[/dim]")

            # Auto-start WhatsApp Green API polling if configured
            try:
                if messenger is None:
                    from unclaude.messaging import get_messenger, Platform
                    messenger = get_messenger()
                from unclaude.messaging import WhatsAppGreenAPIAdapter
                wa_adapter = messenger.adapters.get(Platform.WHATSAPP)
                if wa_adapter and isinstance(wa_adapter, WhatsAppGreenAPIAdapter) and wa_adapter.is_configured():
                    console.print(
                        "[bold cyan]📱 WhatsApp Green API polling active[/bold cyan]")
                    tasks.append(wa_adapter.start_polling(
                        messenger,
                        shutdown_event=self._shutdown_event,
                    ))
            except Exception as e:
                console.print(f"[dim]WhatsApp polling skipped: {e}[/dim]")

            # Send "I'm alive" notification to all registered chats
            if messenger:
                try:
                    await messenger.notify_alive()
                    console.print(
                        "[bold green]📤 Alive notification sent[/bold green]")
                except Exception as e:
                    console.print(
                        f"[dim]Alive notification skipped: {e}[/dim]")

            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            await self._shutdown()

    async def _shutdown(self) -> None:
        """Graceful shutdown."""
        self.status = DaemonStatus.STOPPING
        self._write_status()

        console.print("\n[yellow]Shutting down daemon...[/yellow]")

        # Send shutdown notification via messaging
        try:
            from unclaude.messaging import get_messenger
            messenger = get_messenger()
            await messenger.notify_shutdown()
            console.print("[dim]Shutdown notification sent[/dim]")
        except Exception as e:
            console.print(f"[dim]Shutdown notification skipped: {e}[/dim]")

        # Cancel active tasks
        for task_id, async_task in self._active_tasks.items():
            async_task.cancel()
            self.queue.fail(task_id, "Daemon shutdown")

        # Wait for cancellations
        if self._active_tasks:
            await asyncio.gather(
                *self._active_tasks.values(), return_exceptions=True
            )

        self.status = DaemonStatus.STOPPED
        self._write_status()

        # Clean PID file
        if self.pid_file.exists():
            self.pid_file.unlink()

        console.print("[dim]Daemon stopped.[/dim]")

    def start_background(self) -> int:
        """Start the daemon as a background process. Returns PID."""
        import subprocess

        log_file = Path.home() / ".unclaude" / "daemon" / "daemon.log"

        script = f"""
import asyncio
import sys
sys.path.insert(0, "{Path(__file__).parent.parent}")
from unclaude.autonomous.daemon import AgentDaemon
from pathlib import Path

daemon = AgentDaemon(project_path=Path("{self.project_path}"))
asyncio.run(daemon.run())
"""
        log_handle = open(log_file, "a")
        proc = subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=log_handle,
            stderr=log_handle,
            start_new_session=True,
        )
        return proc.pid

    @staticmethod
    def stop_daemon() -> bool:
        """Stop the running daemon. Returns True if stopped."""
        pid_file = Path.home() / ".unclaude" / "daemon" / "daemon.pid"
        if not pid_file.exists():
            return False

        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            pid_file.unlink(missing_ok=True)
            return True
        except (ProcessLookupError, ValueError):
            pid_file.unlink(missing_ok=True)
            return False

    @staticmethod
    def is_running() -> bool:
        """Check if the daemon is currently running."""
        pid_file = Path.home() / ".unclaude" / "daemon" / "daemon.pid"
        if not pid_file.exists():
            return False
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)  # Signal 0 = check if process exists
            return True
        except (ProcessLookupError, ValueError, PermissionError):
            return False
