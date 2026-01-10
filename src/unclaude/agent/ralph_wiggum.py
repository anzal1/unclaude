"""Ralph Wiggum Mode - Autonomous iteration for long-running tasks."""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from unclaude.config import get_settings


console = Console()


@dataclass
class RalphWiggumResult:
    """Result from a Ralph Wiggum autonomous run."""

    success: bool
    iterations: int
    total_cost: float
    final_output: str
    feedback_results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


class RalphWiggumMode:
    """Autonomous iteration mode for long-running tasks.

    Named after the persistent Simpsons character, this mode enables
    long-running, autonomous, unsupervised coding tasks.
    """

    def __init__(
        self,
        agent_loop: Any,  # AgentLoop - avoiding circular import
        feedback_commands: list[str] | None = None,
        max_iterations: int | None = None,
        max_cost: float | None = None,
        stop_on_success: bool = True,
    ):
        """Initialize Ralph Wiggum mode.

        Args:
            agent_loop: The agent loop to use for iterations.
            feedback_commands: Commands to run for feedback (e.g., tests).
            max_iterations: Maximum number of iterations.
            max_cost: Maximum cost in USD.
            stop_on_success: Whether to stop when all feedback passes.
        """
        self.agent = agent_loop
        settings = get_settings()
        ralph_config = settings.ralph_wiggum

        self.feedback_commands = feedback_commands or ralph_config.feedback_commands
        self.max_iterations = max_iterations or ralph_config.max_iterations
        self.max_cost = max_cost or ralph_config.max_cost
        self.stop_on_success = stop_on_success if stop_on_success is not None else ralph_config.stop_on_success

        self.current_iteration = 0
        self.total_cost = 0.0
        self.feedback_history: list[dict[str, Any]] = []

    async def _run_feedback(self) -> dict[str, Any]:
        """Run feedback commands and collect results.

        Returns:
            Dictionary with command results.
        """
        from unclaude.tools.bash import BashExecuteTool

        bash_tool = BashExecuteTool()
        results = {
            "all_passed": True,
            "commands": [],
        }

        for cmd in self.feedback_commands:
            console.print(f"[dim]Running feedback: {cmd}[/dim]")
            result = await bash_tool.execute(command=cmd, timeout=120)

            cmd_result = {
                "command": cmd,
                "success": result.success,
                "output": result.output[:1000] if result.output else "",
                "error": result.error,
            }
            results["commands"].append(cmd_result)

            if not result.success:
                results["all_passed"] = False

        return results

    async def run(self, initial_task: str) -> RalphWiggumResult:
        """Run the autonomous iteration loop.

        Args:
            initial_task: The initial task description.

        Returns:
            RalphWiggumResult with the final state.
        """
        console.print(
            Panel(
                f"[bold cyan]Ralph Wiggum Mode Activated[/bold cyan]\n\n"
                f"Task: {initial_task[:100]}...\n"
                f"Max iterations: {self.max_iterations}\n"
                f"Max cost: ${self.max_cost}\n"
                f"Feedback commands: {', '.join(self.feedback_commands)}",
                title="🔄 Autonomous Mode",
                border_style="cyan",
            )
        )

        # Initial task execution
        current_task = initial_task
        final_output = ""

        while self.current_iteration < self.max_iterations:
            self.current_iteration += 1
            console.print(f"\n[bold]Iteration {self.current_iteration}/{self.max_iterations}[/bold]")

            try:
                # Run the agent
                response = await self.agent.run(current_task)
                final_output = response

                # Run feedback commands
                feedback = await self._run_feedback()
                self.feedback_history.append(feedback)

                if feedback["all_passed"]:
                    console.print("[bold green]✓ All feedback commands passed![/bold green]")

                    if self.stop_on_success:
                        return RalphWiggumResult(
                            success=True,
                            iterations=self.current_iteration,
                            total_cost=self.total_cost,
                            final_output=final_output,
                            feedback_results=self.feedback_history,
                        )
                else:
                    # Prepare next iteration task
                    failed_commands = [
                        cmd for cmd in feedback["commands"] if not cmd["success"]
                    ]
                    error_summary = "\n".join(
                        f"- {cmd['command']}: {cmd['error'] or cmd['output'][:200]}"
                        for cmd in failed_commands
                    )

                    console.print(f"[yellow]Some feedback failed, iterating...[/yellow]")

                    current_task = (
                        f"The previous attempt had some issues. "
                        f"Please fix the following errors:\n\n{error_summary}\n\n"
                        f"Original task: {initial_task}"
                    )

                # Check cost limit (simplified - would need actual token tracking)
                # For now, estimate based on iterations
                estimated_cost_per_iteration = 0.05  # Rough estimate
                self.total_cost = self.current_iteration * estimated_cost_per_iteration

                if self.total_cost >= self.max_cost:
                    console.print(f"[yellow]Cost limit reached: ${self.total_cost:.2f}[/yellow]")
                    break

            except Exception as e:
                console.print(f"[red]Error in iteration: {e}[/red]")
                return RalphWiggumResult(
                    success=False,
                    iterations=self.current_iteration,
                    total_cost=self.total_cost,
                    final_output=final_output,
                    feedback_results=self.feedback_history,
                    error=str(e),
                )

        # Max iterations reached
        final_feedback = self.feedback_history[-1] if self.feedback_history else {"all_passed": False}

        return RalphWiggumResult(
            success=final_feedback.get("all_passed", False),
            iterations=self.current_iteration,
            total_cost=self.total_cost,
            final_output=final_output,
            feedback_results=self.feedback_history,
            error="Maximum iterations reached" if not final_feedback.get("all_passed") else None,
        )

    def get_status(self) -> dict[str, Any]:
        """Get the current status of the run.

        Returns:
            Status dictionary.
        """
        return {
            "iteration": self.current_iteration,
            "max_iterations": self.max_iterations,
            "total_cost": self.total_cost,
            "max_cost": self.max_cost,
            "feedback_history": self.feedback_history,
        }
