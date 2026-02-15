"""Heartbeat manager - scheduling layer for proactive agent tasks.

The HeartbeatManager is the second layer (after HeartbeatWake) in the
2-layer heartbeat architecture inspired by OpenClaw:

HeartbeatWake (request-merge) → HeartbeatManager (scheduling + execution)

Features:
- Scheduled proactive tasks (file watching, status checks, reminders)
- Active hours configuration (avoid running at night)
- Duplicate suppression
- Task lifecycle management
- Integration with bootstrap file HEARTBEAT.md for task definitions
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Awaitable

from .wake import HeartbeatWake, HeartbeatRequest


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class HeartbeatTask:
    """A proactive task the agent can schedule."""
    task_id: str
    name: str
    description: str
    task_type: str  # "interval", "cron", "event", "oneshot"

    # Scheduling
    interval_seconds: float = 300  # For interval tasks
    max_runs: int = 0  # 0 = unlimited
    active_hours: tuple[int, int] = (8, 22)  # Start, end hour (24h)

    # Execution
    handler: Callable[..., Awaitable[Any]] | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    # State
    status: TaskStatus = TaskStatus.PENDING
    run_count: int = 0
    last_run: float = 0.0
    last_result: str = ""
    created_at: float = field(default_factory=time.time)

    def is_due(self) -> bool:
        """Check if this task is due for execution."""
        if self.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED):
            return False

        if self.max_runs > 0 and self.run_count >= self.max_runs:
            return False

        # Check active hours
        current_hour = datetime.now().hour
        start, end = self.active_hours
        if start < end:
            if not (start <= current_hour < end):
                return False
        else:  # Wraps midnight (e.g., 22-6)
            if end <= current_hour < start:
                return False

        # Check interval
        if self.task_type == "interval":
            return (time.time() - self.last_run) >= self.interval_seconds

        if self.task_type == "oneshot":
            return self.run_count == 0

        return False


class HeartbeatManager:
    """Manages proactive agent tasks.

    Usage:
        manager = HeartbeatManager()
        manager.register_task(HeartbeatTask(
            task_id="status_check",
            name="Check build status",
            description="Periodically check if the build is passing",
            task_type="interval",
            interval_seconds=60,
        ))

        await manager.start()
        # ... tasks run proactively ...
        await manager.stop()
    """

    def __init__(
        self,
        active_hours: tuple[int, int] = (8, 22),
        check_interval_s: float = 10.0,
    ):
        self.active_hours = active_hours
        self.check_interval_s = check_interval_s

        self._tasks: dict[str, HeartbeatTask] = {}
        self._wake = HeartbeatWake(merge_window_ms=250)
        self._wake.set_dispatch_callback(self._on_wake_dispatch)

        self._running = False
        self._scheduler_task: asyncio.Task | None = None

        # Event handlers
        self._task_handlers: dict[str, Callable[..., Awaitable[Any]]] = {}

        # Suppress duplicate runs within this window
        self._suppress_window_s: float = 5.0
        self._recent_runs: dict[str, float] = {}

    def register_task(self, task: HeartbeatTask) -> None:
        """Register a proactive task."""
        if task.active_hours == (8, 22):  # Default - use manager's setting
            task.active_hours = self.active_hours
        self._tasks[task.task_id] = task

    def unregister_task(self, task_id: str) -> None:
        """Remove a task."""
        self._tasks.pop(task_id, None)

    def register_handler(
        self,
        task_type: str,
        handler: Callable[..., Awaitable[Any]],
    ) -> None:
        """Register a handler for a task type."""
        self._task_handlers[task_type] = handler

    async def start(self) -> None:
        """Start the heartbeat manager."""
        self._running = True
        await self._wake.start()
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())

    async def stop(self) -> None:
        """Stop the heartbeat manager."""
        self._running = False
        await self._wake.stop()
        if self._scheduler_task and not self._scheduler_task.done():
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass

    def trigger(self, task_id: str, priority: int = 0) -> bool:
        """Manually trigger a task via the wake layer."""
        task = self._tasks.get(task_id)
        if not task:
            return False

        return self._wake.request(HeartbeatRequest(
            source="manual",
            task_type=task.task_type,
            payload={"task_id": task_id, **task.payload},
            priority=priority,
        ))

    @property
    def tasks(self) -> dict[str, HeartbeatTask]:
        """Get all registered tasks."""
        return dict(self._tasks)

    @property
    def active_tasks(self) -> list[HeartbeatTask]:
        """Get tasks that are pending or running."""
        return [
            t for t in self._tasks.values()
            if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
        ]

    def get_status(self) -> dict[str, Any]:
        """Get heartbeat system status."""
        return {
            "running": self._running,
            "total_tasks": len(self._tasks),
            "active_tasks": len(self.active_tasks),
            "pending_wakes": self._wake.pending_count,
            "tasks": {
                tid: {
                    "name": t.name,
                    "status": t.status.value,
                    "run_count": t.run_count,
                    "is_due": t.is_due(),
                }
                for tid, t in self._tasks.items()
            },
        }

    async def _scheduler_loop(self) -> None:
        """Main scheduling loop - checks for due tasks."""
        while self._running:
            await asyncio.sleep(self.check_interval_s)

            for task in self._tasks.values():
                if task.is_due() and not self._is_suppressed(task.task_id):
                    # Submit through wake layer for deduplication
                    self._wake.request(HeartbeatRequest(
                        source="scheduler",
                        task_type=task.task_type,
                        payload={"task_id": task.task_id, **task.payload},
                        priority=0,
                    ))

    async def _on_wake_dispatch(
        self,
        requests: list[HeartbeatRequest],
    ) -> None:
        """Handle dispatched (merged) requests from wake layer."""
        for req in requests:
            task_id = req.payload.get("task_id")
            if not task_id:
                continue

            task = self._tasks.get(task_id)
            if not task:
                continue

            # Suppress check
            if self._is_suppressed(task_id):
                continue

            await self._execute_task(task, req)

    async def _execute_task(
        self,
        task: HeartbeatTask,
        request: HeartbeatRequest,
    ) -> None:
        """Execute a single heartbeat task."""
        task.status = TaskStatus.RUNNING
        self._recent_runs[task.task_id] = time.time()

        try:
            # Use task's own handler first, then type handler
            handler = task.handler or self._task_handlers.get(task.task_type)
            if handler:
                result = await handler(task, request)
                task.last_result = str(result) if result else "ok"
                task.status = TaskStatus.PENDING  # Ready for next run
            else:
                task.last_result = "no handler"
                task.status = TaskStatus.SKIPPED

        except Exception as e:
            task.last_result = f"error: {e}"
            task.status = TaskStatus.FAILED

        task.run_count += 1
        task.last_run = time.time()

        # Check if we've hit max runs
        if task.max_runs > 0 and task.run_count >= task.max_runs:
            task.status = TaskStatus.COMPLETED

    def _is_suppressed(self, task_id: str) -> bool:
        """Check if a task is within its suppression window."""
        last = self._recent_runs.get(task_id, 0)
        return (time.time() - last) < self._suppress_window_s
