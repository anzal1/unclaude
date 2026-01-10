"""Planner Agent for UnClaude.

This agent is responsible for creating and updating the execution plan (TASK.md)
before the main coding agent takes over.
"""

from pathlib import Path
from unclaude.agent.loop import AgentLoop
from unclaude.tools import Tool, ToolResult

PLANNER_PROMPT = """You are UnClaude's Planner Agent.
Your ONLY goal is to create a detailed, step-by-step execution plan in `TASK.md`.

Use the `file_write` tool to create or update `TASK.md`.

GUIDELINES:
1. **Understand the Goal**: Read the user's request and any existing files.
2. **Break it Down**: Create small, verifiable checkpoints.
3. **Format**:
   - Use Markdown checklist format: `- [ ] Step description`
   - Group steps into Phases if complex.
4. **No Coding**: Do not implement the code. Just plan the implementation.
5. **Verify**: Ensure the plan covers all user requirements.

Current working directory: {cwd}
{context_additions}
"""

class PlannerAgent(AgentLoop):
    """Specialized agent for planning tasks."""

    def __init__(self, **kwargs):
        """Initialize the planner agent."""
        super().__init__(
            system_prompt=PLANNER_PROMPT,
            max_iterations=10,  # Planning shouldn't take too long
            **kwargs
        )
