"""Task intake — multiple ways to feed tasks to the autonomous agent.

Sources:
    1. CLI direct     → `unclaude agent task "fix the login bug"`
    2. File drop      → Drop a .md file in .unclaude/tasks/
    3. TASKS.md       → Add unchecked checkboxes to TASKS.md
    4. Git hooks      → Post-commit, post-push analysis
    5. Webhook        → HTTP endpoint for external integrations
    6. Scheduled      → Cron-like recurring tasks
    7. Watch mode     → File system changes trigger analysis

Each intake source produces a DaemonTask that gets queued.
"""

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from unclaude.autonomous.daemon import DaemonTask, TaskPriority, TaskStatus


class IntakeSource(str, Enum):
    """Where a task came from."""
    CLI = "cli"
    FILE_DROP = "file_drop"
    TASKS_MD = "tasks_md"
    GIT_HOOK = "git_hook"
    WEBHOOK = "webhook"
    SCHEDULE = "schedule"
    FILE_WATCH = "file_watch"


@dataclass
class IntakeRule:
    """A rule that maps file patterns or events to task creation."""
    name: str
    pattern: str          # glob or regex
    template: str         # Task template with {placeholders}
    priority: TaskPriority = TaskPriority.NORMAL
    source: IntakeSource = IntakeSource.FILE_WATCH
    enabled: bool = True


@dataclass
class ScheduledTask:
    """A recurring task definition."""
    name: str
    description: str
    # Cron expression (simplified: "hourly", "daily", "weekly", or "*/N minutes")
    cron: str
    priority: TaskPriority = TaskPriority.BACKGROUND
    enabled: bool = True
    last_run: float | None = None
    next_run: float | None = None


class TaskIntake:
    """Manages all task intake sources.

    Usage:
        intake = TaskIntake(project_path)
        intake.on_task = lambda task: daemon.submit_task(task.description)

        # Start watching for tasks
        await intake.start()

        # Submit directly
        intake.submit("Fix the auth bug", priority=TaskPriority.HIGH)
    """

    def __init__(self, project_path: Path | None = None):
        self.project_path = (project_path or Path.cwd()).resolve()
        self.tasks_dir = self.project_path / ".unclaude" / "tasks"
        self.tasks_md = self.project_path / "TASKS.md"
        self.config_file = self.project_path / ".unclaude" / "intake.json"

        # Callback for new tasks
        self.on_task: Callable[[DaemonTask], None] | None = None

        # State
        self._running = False
        self._watchers: list[asyncio.Task] = []
        self._known_task_files: set[str] = set()
        self._known_tasks_md_items: set[str] = set()
        self._scheduled_tasks: list[ScheduledTask] = []
        self._intake_rules: list[IntakeRule] = []

        # Load config
        self._load_config()

    def _load_config(self):
        """Load intake configuration."""
        if not self.config_file.exists():
            return

        try:
            data = json.loads(self.config_file.read_text())
            for rule_data in data.get("rules", []):
                self._intake_rules.append(IntakeRule(**rule_data))
            for sched_data in data.get("scheduled", []):
                self._scheduled_tasks.append(ScheduledTask(**sched_data))
        except Exception:
            pass

    def save_config(self):
        """Save intake configuration."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "rules": [
                {
                    "name": r.name, "pattern": r.pattern,
                    "template": r.template, "priority": r.priority.value,
                    "source": r.source.value, "enabled": r.enabled,
                }
                for r in self._intake_rules
            ],
            "scheduled": [
                {
                    "name": s.name, "description": s.description,
                    "cron": s.cron, "priority": s.priority.value,
                    "enabled": s.enabled,
                }
                for s in self._scheduled_tasks
            ],
        }
        self.config_file.write_text(json.dumps(data, indent=2))

    def submit(
        self,
        description: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        source: IntakeSource = IntakeSource.CLI,
    ) -> DaemonTask:
        """Submit a task directly."""
        task = DaemonTask(
            description=description,
            priority=priority,
            metadata={"source": source.value},
        )

        if self.on_task:
            self.on_task(task)

        return task

    async def start(self):
        """Start all intake watchers."""
        self._running = True

        # Ensure directories exist
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

        # Initialize known state (avoid processing existing items on startup)
        self._scan_existing_state()

        # Start watchers
        self._watchers = [
            asyncio.create_task(self._watch_task_files()),
            asyncio.create_task(self._watch_tasks_md()),
            asyncio.create_task(self._run_scheduler()),
        ]

    async def stop(self):
        """Stop all intake watchers."""
        self._running = False
        for watcher in self._watchers:
            watcher.cancel()
        self._watchers.clear()

    def _scan_existing_state(self):
        """Record existing state so we don't re-process on startup."""
        # Known task files
        if self.tasks_dir.exists():
            for f in self.tasks_dir.glob("*.md"):
                self._known_task_files.add(f.name)

        # Known TASKS.md items
        if self.tasks_md.exists():
            self._known_tasks_md_items = self._parse_tasks_md()

    async def _watch_task_files(self):
        """Watch .unclaude/tasks/ for new .md files."""
        while self._running:
            try:
                if self.tasks_dir.exists():
                    current_files = {
                        f.name for f in self.tasks_dir.glob("*.md")}
                    new_files = current_files - self._known_task_files

                    for filename in new_files:
                        filepath = self.tasks_dir / filename
                        try:
                            content = filepath.read_text().strip()
                            if content:
                                self.submit(
                                    description=content,
                                    source=IntakeSource.FILE_DROP,
                                    priority=TaskPriority.NORMAL,
                                )
                        except Exception:
                            pass

                    self._known_task_files = current_files
            except Exception:
                pass

            await asyncio.sleep(5)

    async def _watch_tasks_md(self):
        """Watch TASKS.md for new unchecked items."""
        while self._running:
            try:
                if self.tasks_md.exists():
                    current_items = self._parse_tasks_md()
                    new_items = current_items - self._known_tasks_md_items

                    for item in new_items:
                        self.submit(
                            description=item,
                            source=IntakeSource.TASKS_MD,
                            priority=TaskPriority.NORMAL,
                        )

                    self._known_tasks_md_items = current_items
            except Exception:
                pass

            await asyncio.sleep(10)

    def _parse_tasks_md(self) -> set[str]:
        """Parse TASKS.md for unchecked checkbox items."""
        items = set()
        try:
            content = self.tasks_md.read_text()
            # Match unchecked checkboxes: - [ ] task description
            matches = re.findall(
                r"^[-*]\s*\[\s*\]\s+(.+)$", content, re.MULTILINE)
            items = {m.strip() for m in matches if m.strip()}
        except Exception:
            pass
        return items

    async def _run_scheduler(self):
        """Run scheduled tasks at their intervals."""
        while self._running:
            now = time.time()

            for sched in self._scheduled_tasks:
                if not sched.enabled:
                    continue

                # Calculate next run
                if sched.next_run is None:
                    sched.next_run = self._calc_next_run(sched.cron, now)

                if now >= sched.next_run:
                    self.submit(
                        description=sched.description,
                        source=IntakeSource.SCHEDULE,
                        priority=sched.priority,
                    )
                    sched.last_run = now
                    sched.next_run = self._calc_next_run(sched.cron, now)

            await asyncio.sleep(60)  # Check every minute

    def _calc_next_run(self, cron: str, from_time: float) -> float:
        """Calculate next run time from a simplified cron expression."""
        cron = cron.strip().lower()

        if cron == "hourly":
            return from_time + 3600
        elif cron == "daily":
            return from_time + 86400
        elif cron == "weekly":
            return from_time + 604800
        elif cron.startswith("*/"):
            # */N minutes
            try:
                minutes = int(cron.split()[0].replace("*/", ""))
                return from_time + (minutes * 60)
            except (ValueError, IndexError):
                return from_time + 3600
        else:
            return from_time + 3600  # Default: hourly

    # --- Git hook integration ---

    def install_git_hooks(self):
        """Install git hooks that feed tasks to the agent."""
        hooks_dir = self.project_path / ".git" / "hooks"
        if not hooks_dir.exists():
            return False

        # Post-commit hook
        post_commit = hooks_dir / "post-commit"
        hook_content = """#!/bin/sh
# unclaude: auto-analyze commits
COMMIT_MSG=$(git log -1 --pretty=%B)
CHANGED_FILES=$(git diff --name-only HEAD~1)
echo "$COMMIT_MSG" > .unclaude/tasks/_commit_review.md
echo "" >> .unclaude/tasks/_commit_review.md
echo "Changed files:" >> .unclaude/tasks/_commit_review.md
echo "$CHANGED_FILES" >> .unclaude/tasks/_commit_review.md
echo "" >> .unclaude/tasks/_commit_review.md
echo "Review this commit for bugs, issues, or improvements." >> .unclaude/tasks/_commit_review.md
"""
        if not post_commit.exists():
            post_commit.write_text(hook_content)
            post_commit.chmod(0o755)

        return True

    def add_scheduled_task(
        self,
        name: str,
        description: str,
        interval: str = "daily",
        priority: TaskPriority = TaskPriority.BACKGROUND,
    ):
        """Add a recurring scheduled task."""
        self._scheduled_tasks.append(ScheduledTask(
            name=name,
            description=description,
            cron=interval,
            priority=priority,
        ))
        self.save_config()

    def add_watch_rule(
        self,
        name: str,
        pattern: str,
        template: str,
        priority: TaskPriority = TaskPriority.NORMAL,
    ):
        """Add a file watch rule."""
        self._intake_rules.append(IntakeRule(
            name=name,
            pattern=pattern,
            template=template,
            priority=priority,
        ))
        self.save_config()
