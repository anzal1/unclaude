"""Multi-agent swarm orchestrator.

When a task is too big for one agent, the swarm breaks it into
subtasks, assigns specialized agents, coordinates their work,
and merges results.

Architecture:
    SwarmOrchestrator
    ├── Planner Agent     → Breaks task into subtasks
    ├── Worker Agents     → Execute subtasks (parallel where possible)
    ├── Reviewer Agent    → Reviews results, requests fixes
    └── Merger Agent      → Combines all results into final output

Usage:
    swarm = SwarmOrchestrator(provider=provider)
    result = await swarm.execute("Build user auth system with tests")
    # Spawns: planner → [api_agent, db_agent, test_agent] → reviewer → merge
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()


class AgentRole(str, Enum):
    """Roles agents can play in a swarm."""
    PLANNER = "planner"       # Decomposes tasks
    CODER = "coder"           # Writes code
    TESTER = "tester"         # Writes and runs tests
    REVIEWER = "reviewer"     # Reviews code quality
    DEBUGGER = "debugger"     # Fixes bugs
    DOCUMENTER = "documenter"  # Writes docs
    DEVOPS = "devops"         # CI/CD, deployment
    RESEARCHER = "researcher"  # Investigates, reads code
    MERGER = "merger"         # Combines subtask results


class SubtaskStatus(str, Enum):
    PENDING = "pending"
    BLOCKED = "blocked"    # Waiting on dependencies
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    REVIEWING = "reviewing"


@dataclass
class SwarmSubtask:
    """A subtask assigned to an agent in the swarm."""
    subtask_id: str = field(default_factory=lambda: str(uuid.uuid4())[:6])
    description: str = ""
    role: AgentRole = AgentRole.CODER
    status: SubtaskStatus = SubtaskStatus.PENDING

    # Dependencies (other subtask IDs that must complete first)
    depends_on: list[str] = field(default_factory=list)

    # Results
    result: str | None = None
    error: str | None = None
    files_modified: list[str] = field(default_factory=list)

    # Timing
    started_at: float | None = None
    completed_at: float | None = None

    def is_ready(self, completed_ids: set[str]) -> bool:
        """Check if all dependencies are satisfied."""
        return all(dep in completed_ids for dep in self.depends_on)


@dataclass
class SwarmTask:
    """The top-level task being executed by the swarm."""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    description: str = ""
    subtasks: list[SwarmSubtask] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


@dataclass
class SwarmResult:
    """Result of a swarm execution."""
    task_id: str
    success: bool
    summary: str
    subtask_results: list[dict[str, Any]] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    total_time: float = 0.0
    total_cost: float = 0.0
    agents_used: int = 0


# System prompts for each role
ROLE_PROMPTS: dict[AgentRole, str] = {
    AgentRole.PLANNER: """You are a Task Planner Agent. Your ONLY job is to break down a complex task
into smaller, actionable subtasks. Output a JSON array of subtasks.

Each subtask should have:
- "description": What to do (be specific, include file paths where possible)
- "role": One of: coder, tester, reviewer, debugger, documenter, devops, researcher
- "depends_on": Array of subtask indices (0-based) that must complete first

Rules:
- Keep subtasks focused and independent where possible
- Put research/reading tasks first
- Testing should depend on coding
- Review should depend on both coding and testing
- Be specific about files and functions

Respond ONLY with a JSON array. No other text.""",

    AgentRole.CODER: """You are a focused Coding Agent in a multi-agent swarm.
Your job is to implement EXACTLY what is described in your task.
- Read existing code before writing
- Follow the project's existing style
- Write clean, well-documented code
- Don't over-engineer — do exactly what's asked""",

    AgentRole.TESTER: """You are a Testing Agent in a multi-agent swarm.
Your job is to write and run tests for the code.
- Write comprehensive unit tests (pytest style)
- Cover edge cases and error paths
- Run tests and report results
- If tests fail, report what failed and why""",

    AgentRole.REVIEWER: """You are a Code Review Agent in a multi-agent swarm.
Review the work done by other agents.
- Check for bugs, security issues, and performance problems
- Verify the implementation matches the requirements
- Check test coverage
- Suggest improvements (be specific)
If everything looks good, say APPROVED. If not, list specific issues.""",

    AgentRole.DEBUGGER: """You are a Debugger Agent in a multi-agent swarm.
Your job is to investigate and fix bugs.
- Be systematic in your investigation
- Check logs, traces, and error messages
- Fix the root cause, not just symptoms
- Verify your fix doesn't break other things""",

    AgentRole.DOCUMENTER: """You are a Documentation Agent in a multi-agent swarm.
Write clear, helpful documentation for the code.
- Add/update docstrings
- Update README if needed
- Document public APIs
- Include usage examples""",

    AgentRole.RESEARCHER: """You are a Research Agent in a multi-agent swarm.
Your job is to investigate and gather information.
- Read relevant code files
- Understand the codebase structure
- Find relevant patterns and conventions
- Report your findings clearly so other agents can use them""",
}


class SwarmOrchestrator:
    """Orchestrates multiple agents to tackle complex tasks.

    The orchestrator:
    1. Uses a planner agent to decompose the task
    2. Identifies parallelizable subtasks
    3. Spawns agents for each subtask (respecting dependencies)
    4. Collects results and handles failures
    5. Optionally runs a reviewer agent
    6. Produces a final merged result
    """

    def __init__(
        self,
        project_path: Path | None = None,
        max_parallel: int = 3,
        enable_review: bool = True,
        max_subtask_iterations: int = 15,
    ):
        self.project_path = project_path or Path.cwd()
        self.max_parallel = max_parallel
        self.enable_review = enable_review
        self.max_subtask_iterations = max_subtask_iterations

    async def execute(self, task_description: str) -> SwarmResult:
        """Execute a complex task using a swarm of agents.

        Args:
            task_description: Natural language description of the task.

        Returns:
            SwarmResult with all outcomes.
        """
        start_time = time.time()
        task = SwarmTask(description=task_description)

        console.print(Panel(
            f"[bold cyan]Swarm Task:[/bold cyan] {task_description}",
            title="🐝 Swarm Orchestrator",
            border_style="cyan",
        ))

        # Phase 1: Plan
        console.print("\n[bold]Phase 1: Planning[/bold]")
        subtasks = await self._plan(task_description)
        task.subtasks = subtasks

        # Show plan
        table = Table(title="Execution Plan")
        table.add_column("#", style="dim")
        table.add_column("Role", style="cyan")
        table.add_column("Task")
        table.add_column("Depends On", style="dim")
        for i, st in enumerate(subtasks):
            deps = ", ".join(f"#{d}" for d in st.depends_on) or "-"
            table.add_row(str(i), st.role.value, st.description[:60], deps)
        console.print(table)

        # Phase 2: Execute
        console.print("\n[bold]Phase 2: Executing[/bold]")
        completed_ids: set[str] = set()
        all_files: list[str] = []
        agents_used = 0

        while True:
            # Find ready subtasks
            ready = [
                st for st in subtasks
                if st.status == SubtaskStatus.PENDING and st.is_ready(completed_ids)
            ]

            if not ready:
                # Check if everything is done or blocked
                pending = [st for st in subtasks if st.status in (
                    SubtaskStatus.PENDING, SubtaskStatus.RUNNING, SubtaskStatus.BLOCKED
                )]
                if not pending:
                    break
                elif all(st.status == SubtaskStatus.BLOCKED for st in pending):
                    console.print(
                        "[red]Deadlock: subtasks are blocking each other[/red]")
                    break
                await asyncio.sleep(1)
                continue

            # Execute ready subtasks (up to max_parallel)
            batch = ready[:self.max_parallel]
            tasks = []
            for st in batch:
                st.status = SubtaskStatus.RUNNING
                st.started_at = time.time()
                agents_used += 1
                console.print(
                    f"  [cyan]▶[/cyan] [{st.role.value}] {st.description[:60]}...")
                tasks.append(self._execute_subtask(st, task_description))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for st, result in zip(batch, results):
                if isinstance(result, Exception):
                    st.status = SubtaskStatus.FAILED
                    st.error = str(result)
                    console.print(
                        f"  [red]✗[/red] [{st.role.value}] {st.error[:80]}")
                elif result:
                    st.status = SubtaskStatus.COMPLETED
                    st.result = result
                    st.completed_at = time.time()
                    completed_ids.add(st.subtask_id)
                    all_files.extend(st.files_modified)
                    console.print(f"  [green]✓[/green] [{st.role.value}] Done")

        # Phase 3: Review (optional)
        review_result = None
        if self.enable_review:
            console.print("\n[bold]Phase 3: Review[/bold]")
            completed_subtasks = [
                st for st in subtasks if st.status == SubtaskStatus.COMPLETED]
            if completed_subtasks:
                review_result = await self._review(task_description, completed_subtasks)
                console.print(f"  [dim]{review_result[:100]}[/dim]")

        # Build result
        total_time = time.time() - start_time
        success = all(
            st.status == SubtaskStatus.COMPLETED
            for st in subtasks
        )

        summary_parts = []
        for st in subtasks:
            status_icon = "✓" if st.status == SubtaskStatus.COMPLETED else "✗"
            summary_parts.append(
                f"{status_icon} [{st.role.value}] {st.description[:60]}")
        if review_result:
            summary_parts.append(f"\nReview: {review_result[:200]}")

        result = SwarmResult(
            task_id=task.task_id,
            success=success,
            summary="\n".join(summary_parts),
            subtask_results=[
                {
                    "role": st.role.value,
                    "description": st.description,
                    "status": st.status.value,
                    "result": st.result[:500] if st.result else None,
                    "error": st.error,
                }
                for st in subtasks
            ],
            files_modified=list(set(all_files)),
            total_time=total_time,
            agents_used=agents_used,
        )

        # Summary panel
        status_color = "green" if success else "red"
        console.print(Panel(
            f"[{status_color}]{'Success' if success else 'Partial failure'}[/{status_color}]\n"
            f"Agents: {agents_used} | Time: {total_time:.1f}s | Files: {len(result.files_modified)}",
            title="🐝 Swarm Complete",
            border_style=status_color,
        ))

        return result

    async def _plan(self, task_description: str) -> list[SwarmSubtask]:
        """Use a planner agent to decompose the task."""
        from unclaude.agent.enhanced_loop import EnhancedAgentLoop
        from unclaude.providers.llm import Provider
        from unclaude.onboarding import load_config, load_credential, PROVIDERS

        # Setup provider
        config = load_config()
        provider_name = config.get("default_provider", "gemini")
        provider_config_data = config.get(
            "providers", {}).get(provider_name, {})
        model = provider_config_data.get("model")

        api_key = load_credential(provider_name)
        if api_key:
            provider_info = PROVIDERS.get(provider_name, {})
            env_var = provider_info.get("env_var")
            if env_var:
                import os
                os.environ[env_var] = api_key

        provider = Provider(provider_name)
        if model:
            provider.config.model = model

        planner = EnhancedAgentLoop(
            provider=provider,
            system_prompt=ROLE_PROMPTS[AgentRole.PLANNER] +
            "\n\n{cwd}\n{session_id}\n{security_profile}\n{routing_profile}\n{bootstrap_context}\n{context_additions}",
            max_iterations=5,
            project_path=self.project_path,
            enable_memory=False,
        )

        plan_response = await planner.run(
            f"Break this task into subtasks:\n\n{task_description}\n\n"
            f"Project: {self.project_path}\n"
            f"Respond with ONLY a JSON array."
        )

        # Parse the plan
        try:
            # Try to extract JSON from the response
            plan_text = plan_response.strip()
            # Find JSON array in the response
            start = plan_text.find("[")
            end = plan_text.rfind("]") + 1
            if start >= 0 and end > start:
                plan_data = json.loads(plan_text[start:end])
            else:
                plan_data = json.loads(plan_text)

            subtasks = []
            for i, item in enumerate(plan_data):
                role_str = item.get("role", "coder").lower()
                try:
                    role = AgentRole(role_str)
                except ValueError:
                    role = AgentRole.CODER

                deps = []
                for dep_idx in item.get("depends_on", []):
                    if isinstance(dep_idx, int) and dep_idx < len(plan_data):
                        deps.append(str(dep_idx))

                subtasks.append(SwarmSubtask(
                    subtask_id=str(i),
                    description=item.get("description", ""),
                    role=role,
                    depends_on=deps,
                ))

            return subtasks

        except (json.JSONDecodeError, Exception):
            # Fallback: single subtask
            return [SwarmSubtask(
                subtask_id="0",
                description=task_description,
                role=AgentRole.CODER,
            )]

    async def _execute_subtask(
        self, subtask: SwarmSubtask, parent_task: str
    ) -> str:
        """Execute a single subtask with a specialized agent."""
        from unclaude.agent.enhanced_loop import EnhancedAgentLoop
        from unclaude.providers.llm import Provider
        from unclaude.onboarding import load_config, load_credential, PROVIDERS

        config = load_config()
        provider_name = config.get("default_provider", "gemini")
        provider_config_data = config.get(
            "providers", {}).get(provider_name, {})
        model = provider_config_data.get("model")

        api_key = load_credential(provider_name)
        if api_key:
            provider_info = PROVIDERS.get(provider_name, {})
            env_var = provider_info.get("env_var")
            if env_var:
                import os
                os.environ[env_var] = api_key

        provider = Provider(provider_name)
        if model:
            provider.config.model = model

        role_prompt = ROLE_PROMPTS.get(
            subtask.role, ROLE_PROMPTS[AgentRole.CODER])

        agent = EnhancedAgentLoop(
            provider=provider,
            system_prompt=role_prompt +
            "\n\nCurrent dir: {cwd}\n{session_id}\n{security_profile}\n{routing_profile}\n{bootstrap_context}\n{context_additions}",
            max_iterations=self.max_subtask_iterations,
            project_path=self.project_path,
            enable_memory=False,
            security_profile="developer",
        )

        prompt = (
            f"PARENT TASK: {parent_task}\n\n"
            f"YOUR SUBTASK: {subtask.description}\n\n"
            f"Complete this subtask. Be focused and efficient."
        )

        return await agent.run(prompt)

    async def _review(
        self, task_description: str, completed: list[SwarmSubtask]
    ) -> str:
        """Run a reviewer agent on completed subtasks."""
        from unclaude.agent.enhanced_loop import EnhancedAgentLoop
        from unclaude.providers.llm import Provider
        from unclaude.onboarding import load_config, load_credential, PROVIDERS

        config = load_config()
        provider_name = config.get("default_provider", "gemini")
        provider_config_data = config.get(
            "providers", {}).get(provider_name, {})
        model = provider_config_data.get("model")

        api_key = load_credential(provider_name)
        if api_key:
            provider_info = PROVIDERS.get(provider_name, {})
            env_var = provider_info.get("env_var")
            if env_var:
                import os
                os.environ[env_var] = api_key

        provider = Provider(provider_name)
        if model:
            provider.config.model = model

        reviewer = EnhancedAgentLoop(
            provider=provider,
            system_prompt=ROLE_PROMPTS[AgentRole.REVIEWER] +
            "\n\n{cwd}\n{session_id}\n{security_profile}\n{routing_profile}\n{bootstrap_context}\n{context_additions}",
            max_iterations=10,
            project_path=self.project_path,
            enable_memory=False,
        )

        subtask_summary = "\n\n".join([
            f"## Subtask: {st.description}\nRole: {st.role.value}\nResult:\n{st.result[:500] if st.result else 'No result'}"
            for st in completed
        ])

        return await reviewer.run(
            f"Review the work done for this task:\n\n"
            f"TASK: {task_description}\n\n"
            f"COMPLETED SUBTASKS:\n{subtask_summary}\n\n"
            f"Review the code changes. Say APPROVED if good, or list issues."
        )
