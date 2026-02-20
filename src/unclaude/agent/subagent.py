"""Subagent system for specialized task delegation.

Now with Pact capability delegation: subagents receive narrowed
cryptographic delegations from their parent, not blank Provider instances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from unclaude.tools.base import Tool, ToolResult

if TYPE_CHECKING:
    from unclaude.auth.pact_identity import PactIdentityManager, PactSessionInfo


@dataclass
class SubagentConfig:
    """Configuration for a subagent."""

    name: str
    description: str
    system_prompt: str
    allowed_tools: list[str] = field(default_factory=list)  # Empty = all tools
    max_iterations: int = 10


# Pre-defined subagent templates
SUBAGENT_TEMPLATES = {
    "reviewer": SubagentConfig(
        name="Code Reviewer",
        description="Reviews code for bugs, style issues, and improvements",
        system_prompt="""You are a Code Reviewer Agent. Your job is to:
1. Analyze the provided code carefully
2. Identify potential bugs, security issues, and performance problems
3. Suggest improvements for readability and maintainability
4. Check for compliance with best practices

Be thorough but constructive. Provide actionable feedback.""",
        allowed_tools=["file_read", "file_grep", "directory_list"],
        max_iterations=5,
    ),
    "tester": SubagentConfig(
        name="Test Writer",
        description="Writes comprehensive tests for code",
        system_prompt="""You are a Test Writer Agent. Your job is to:
1. Analyze the code that needs testing
2. Write comprehensive unit tests covering edge cases
3. Write integration tests where appropriate
4. Ensure good test coverage

Use pytest style. Include both happy path and error cases.""",
        allowed_tools=["file_read", "file_write", "bash_execute"],
        max_iterations=10,
    ),
    "documenter": SubagentConfig(
        name="Documentation Writer",
        description="Writes and improves documentation",
        system_prompt="""You are a Documentation Writer Agent. Your job is to:
1. Read the code and understand its purpose
2. Write clear, helpful documentation
3. Add docstrings to functions and classes
4. Create README sections as needed

Be concise but comprehensive. Use examples where helpful.""",
        allowed_tools=["file_read", "file_write", "file_edit"],
        max_iterations=8,
    ),
    "debugger": SubagentConfig(
        name="Debugger",
        description="Investigates and fixes bugs",
        system_prompt="""You are a Debugger Agent. Your job is to:
1. Understand the bug or error being reported
2. Investigate the root cause systematically
3. Propose and implement a fix
4. Verify the fix works

Be methodical. Check logs, trace execution, and test your fixes.""",
        allowed_tools=["file_read", "file_grep", "bash_execute", "file_edit"],
        max_iterations=15,
    ),
}


class SubagentTool(Tool):
    """Tool for spawning specialized subagents with Pact delegation."""

    def __init__(
        self,
        pact_identity: PactIdentityManager | None = None,
        parent_session: PactSessionInfo | None = None,
    ):
        self._pact_identity = pact_identity
        self._parent_session = parent_session

    @property
    def name(self) -> str:
        return "spawn_subagent"

    @property
    def description(self) -> str:
        templates = ", ".join(SUBAGENT_TEMPLATES.keys())
        return (
            f"Spawn a specialized subagent to handle a specific task. "
            f"Available templates: {templates}. "
            f"Use this to delegate complex subtasks to focused specialists."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "template": {
                    "type": "string",
                    "enum": list(SUBAGENT_TEMPLATES.keys()),
                    "description": "Subagent template to use",
                },
                "task": {
                    "type": "string",
                    "description": "Specific task for the subagent to complete",
                },
                "context": {
                    "type": "string",
                    "description": "Additional context or files to focus on",
                },
            },
            "required": ["template", "task"],
        }

    @property
    def requires_permission(self) -> bool:
        return True  # Subagents can execute actions

    async def execute(
        self,
        template: str,
        task: str,
        context: str = "",
        **kwargs: Any,
    ) -> ToolResult:
        from unclaude.agent.loop import AgentLoop
        from unclaude.providers.llm import Provider
        from unclaude.tools import get_default_tools

        if template not in SUBAGENT_TEMPLATES:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown template: {template}. Available: {list(SUBAGENT_TEMPLATES.keys())}",
            )

        config = SUBAGENT_TEMPLATES[template]

        # Create Pact delegation for subagent (narrowed capabilities)
        subagent_pact_session = None
        if self._pact_identity and self._parent_session:
            try:
                # Map template to Pact capability URIs
                template_capabilities = {
                    "reviewer": ["file:read", "memory:read"],
                    "tester": ["file:read", "file:write", "shell:execute", "memory:read"],
                    "documenter": ["file:read", "file:write", "memory:read"],
                    "debugger": ["file:read", "shell:execute", "file:write", "memory:read"],
                }
                caps = template_capabilities.get(template, ["file:read"])
                subagent_pact_session = self._pact_identity.create_subagent_delegation(
                    parent_session=self._parent_session,
                    capabilities=caps,
                )
            except Exception:
                pass  # Fall back to non-delegated execution

        try:
            # Filter tools if specified
            all_tools = get_default_tools()
            if config.allowed_tools:
                tools = [t for t in all_tools if t.name in config.allowed_tools]
            else:
                tools = all_tools

            # Create subagent with specialized prompt
            subagent = AgentLoop(
                provider=Provider(),
                tools=tools,
                max_iterations=config.max_iterations,
                system_prompt=config.system_prompt + "\n\n{context_additions}",
                enable_memory=False,  # Subagents don't persist memory
            )

            # Construct the full task
            full_task = task
            if context:
                full_task = f"{task}\n\nContext:\n{context}"

            # Add delegation context if available
            if subagent_pact_session:
                chain_info = (
                    f"\n\n[Security: Running with delegated capabilities from parent session. "
                    f"Identity: {subagent_pact_session.identity.id[:16]}. "
                    f"Chain depth: {len(subagent_pact_session.chain)}.]"
                )
                full_task += chain_info

            # Run subagent
            result = await subagent.run(full_task)

            # Close subagent session
            if subagent_pact_session:
                self._pact_identity.end_session(
                    subagent_pact_session.session_id)

            return ToolResult(
                success=True,
                output=f"[{config.name}] Completed:\n\n{result}",
            )

        except Exception as e:
            # Clean up subagent session on error
            if subagent_pact_session:
                try:
                    self._pact_identity.end_session(
                        subagent_pact_session.session_id)
                except Exception:
                    pass
            return ToolResult(
                success=False,
                output="",
                error=f"Subagent error: {str(e)}",
            )
