"""Core agentic loop engine for UnClaude."""

import asyncio
import os
from pathlib import Path
from typing import Any, Callable

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from unclaude.config import get_settings
from unclaude.context import ContextLoader
from unclaude.hooks import HooksEngine
from unclaude.memory import MemoryStore
from unclaude.providers import Message, Provider, ToolCall, ToolDefinition
from unclaude.tools import Tool, ToolResult, get_default_tools


console = Console()


SYSTEM_PROMPT = """You are UnClaude, an open-source AI coding assistant. You help developers write, debug, and understand code.

You have access to tools that allow you to:
- Read, write, and edit files
- Search for files and content
- Execute bash commands
- Navigate the file system
- Search the web and fetch URLs

AGENCY GUIDELINES:
1. **PLAN FIRST**: complex tasks must start with a plan. Break tasks into checkpoints.
2. **PARALLELISM**: Call multiple non-dependent tools in parallel to save time (e.g., read multiple files at once).
3. **VERIFY**: Always verify your changes work (e.g., run tests or check output).
4. **CONTEXT**: Use your memory. If you've done this before, recall it.
5. **SAFETY**: Read files before editing. Do not edit massive files blindly.

Current working directory: {cwd}
{context_additions}
"""


class AgentLoop:
    """The core agentic loop that processes user requests."""

    def __init__(
        self,
        provider: Provider | None = None,
        tools: list[Tool] | None = None,
        max_iterations: int = 50,
        project_path: Path | None = None,
        enable_memory: bool = True,
        conversation_id: str | None = None,
        system_prompt: str | None = None,
    ):
        """Initialize the agent loop.

        Args:
            provider: LLM provider to use. If None, uses default from config.
            tools: List of tools available to the agent. If None, uses defaults.
            max_iterations: Maximum number of tool-use iterations per request.
            project_path: Path to the project directory for context loading.
            enable_memory: Whether to enable conversation persistence.
            conversation_id: ID of existing conversation to resume.
        """
        self.provider = provider or Provider()
        self.tools = tools or get_default_tools()
        self.max_iterations = max_iterations
        self.settings = get_settings()
        self.messages: list[Message] = []
        self._tool_map: dict[str, Tool] = {tool.name: tool for tool in self.tools}

        # Context loading
        self.project_path = project_path or Path.cwd()
        self.context_loader = ContextLoader(self.project_path)

        # Memory/persistence
        self.enable_memory = enable_memory
        self.memory_store = MemoryStore() if enable_memory else None
        self.conversation_id = conversation_id

        if enable_memory and not conversation_id:
            self.conversation_id = self.memory_store.create_conversation(
                str(self.project_path)
            )

        self.system_prompt = system_prompt or SYSTEM_PROMPT

        # Hooks engine for pre/post tool automation
        self.hooks_engine = HooksEngine(self.project_path)

    def _get_tool_definitions(self) -> list[ToolDefinition]:
        """Get tool definitions for the LLM."""
        return [tool.to_definition() for tool in self.tools]

    async def _check_permission(self, tool: Tool, call: ToolCall) -> bool:
        """Check if we have permission to execute a tool.

        Args:
            tool: The tool to execute.
            call: The tool call with arguments.

        Returns:
            True if execution is allowed.
        """
        if not tool.requires_permission:
            return True

        # Check if auto-approve is enabled for this session
        if getattr(self, '_auto_approve_all', False):
            return True
        
        if getattr(self, '_auto_approve_tools', None) is None:
            self._auto_approve_tools = set()
        
        if tool.name in self._auto_approve_tools:
            return True

        # Check whitelist
        if tool.name == "bash_execute":
            command = call.arguments.get("command", "")
            for pattern in self.settings.whitelist.bash:
                if pattern.endswith("*"):
                    if command.startswith(pattern[:-1]):
                        return True
                elif command == pattern:
                    return True

        # Ask user with more options
        console.print(
            Panel(
                f"[bold yellow]Permission Required[/bold yellow]\n\n"
                f"Tool: [cyan]{tool.name}[/cyan]\n"
                f"Arguments: {call.arguments}",
                title="🔒 Permission Request",
            )
        )
        console.print("[dim]y=yes, n=no, a=yes to all, t=yes to this tool type[/dim]")
        
        choice = Prompt.ask(
            "Allow this operation?",
            choices=["y", "n", "a", "t"],
            default="y",
        )
        
        if choice == "a":
            self._auto_approve_all = True
            return True
        elif choice == "t":
            self._auto_approve_tools.add(tool.name)
            return True
        elif choice == "y":
            return True
        return False

    async def _execute_tool(self, call: ToolCall) -> ToolResult:
        """Execute a tool call.

        Args:
            call: The tool call to execute.

        Returns:
            ToolResult from the execution.
        """
        tool = self._tool_map.get(call.name)
        if not tool:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown tool: {call.name}",
            )

        # Check permission
        if not await self._check_permission(tool, call):
            return ToolResult(
                success=False,
                output="",
                error="Permission denied by user",
            )

        # Execute the tool with hooks
        console.print(f"[dim]Executing {call.name}...[/dim]")
        try:
            # Pre-tool hooks
            await self.hooks_engine.execute_hooks("pre_tool", call.name, call.arguments)
            
            # Execute the tool
            result = await tool.execute(**call.arguments)
            
            # Post-tool hooks
            await self.hooks_engine.execute_hooks("post_tool", call.name, call.arguments, result)
            
            return result
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    async def run(self, user_input: str) -> str:
        """Process a user request through the agentic loop.

        Args:
            user_input: The user's message/request.

        Returns:
            The final response from the agent.
        """
        # Initialize with system prompt if this is the first message
        if not self.messages:
            # Load project context
            context_additions = self.context_loader.get_system_prompt_addition()

            system_content = self.system_prompt.format(
                cwd=str(self.project_path),
                context_additions=context_additions,
            )

            system_msg = Message(role="system", content=system_content)
            self.messages.append(system_msg)

            # Save to memory
            if self.enable_memory and self.memory_store:
                self.memory_store.save_message(
                    self.conversation_id, "system", system_content
                )

        # Add user message
        user_msg = Message(role="user", content=user_input)
        self.messages.append(user_msg)

        # Save user message to memory
        if self.enable_memory and self.memory_store:
            self.memory_store.save_message(
                self.conversation_id, "user", user_input
            )
            
            # Index this message for long-term recall (Infinite Memory)
            import uuid
            memory_id = f"msg-{uuid.uuid4()}"
            self.memory_store.save_memory(
                memory_id=memory_id,
                content=user_input,
                memory_type="recall",
                metadata={"conversation_id": self.conversation_id, "role": "user"},
                project_path=str(self.project_path),
            )
            
            # Infinite Memory: Retrieve relevant context
            # Project-scoped for speed: only search memories from this project
            memories = self.memory_store.search_memories(
                user_input, 
                project_path=str(self.project_path),
                limit=3
            )
            if memories:
                memory_context = "\n".join([f"- {m['content'][:200]}" for m in memories])
                
                # Avoid injecting if it exactly matches current input
                if memory_context and user_input not in memory_context:
                    console.print(Panel(f"[dim]Recalled {len(memories)} project memories[/dim]", title="Brain 🧠"))
                    self.messages.append(
                        Message(
                            role="system", 
                            content=f"RECALLED MEMORY (from this project):\n{memory_context}\nUse this context if relevant."
                        )
                    )


        iterations = 0
        tool_definitions = self._get_tool_definitions()

        while iterations < self.max_iterations:
            iterations += 1

            # Get LLM response
            console.print("[dim]Thinking...[/dim]")
            
            try:
                response = await self.provider.chat(
                    messages=self.messages,
                    tools=tool_definitions,
                )
            except Exception as e:
                error_msg = str(e)
                console.print(f"[red]LLM Error: {error_msg[:200]}[/red]")
                # If it's an empty response error, retry without tools
                if "empty" in error_msg.lower() or "must contain" in error_msg.lower():
                    console.print("[yellow]Retrying without tools...[/yellow]")
                    try:
                        response = await self.provider.chat(
                            messages=self.messages,
                            tools=None,
                        )
                    except Exception:
                        return f"I encountered an error: {error_msg}. Please try rephrasing your request."
                else:
                    return f"I encountered an error: {error_msg}. Please try again."

            # If there are no tool calls, we're done
            if not response.tool_calls:
                if response.content:
                    self.messages.append(
                        Message(role="assistant", content=response.content)
                    )
                    # Save assistant response to long-term memory
                    if self.enable_memory and self.memory_store:
                        import uuid
                        memory_id = f"msg-{uuid.uuid4()}"
                        self.memory_store.save_memory(
                            memory_id=memory_id,
                            content=response.content,
                            memory_type="recall",
                            metadata={"conversation_id": self.conversation_id, "role": "assistant"},
                            project_path=str(self.project_path),
                        )
                return response.content or "I'm not sure how to respond to that."

            # Add assistant message with tool calls
            import json
            self.messages.append(
                Message(
                    role="assistant",
                    content=response.content,
                    tool_calls=[
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in response.tool_calls
                    ],
                )
            )

            # Track consecutive failures to prevent loops
            if not hasattr(self, '_failure_tracker'):
                self._failure_tracker = {}
            
            all_failed = True
            
            # Execute each tool call
            for call in response.tool_calls:
                result = await self._execute_tool(call)

                # Show result
                if result.success:
                    output = result.output[:500] + "..." if len(result.output) > 500 else result.output
                    console.print(f"[green]✓[/green] {call.name}: {output[:100]}...")
                    # Reset failure counter on success
                    self._failure_tracker[call.name] = 0
                    all_failed = False
                else:
                    console.print(f"[red]✗[/red] {call.name}: {result.error}")
                    
                    # Track consecutive failures (exclude bash exit codes which are valid feedback)
                    is_bash_exit = call.name == "bash_execute" and "Exit code" in (result.error or "")
                    
                    if not is_bash_exit:
                        self._failure_tracker[call.name] = self._failure_tracker.get(call.name, 0) + 1
                    
                    # Check for loop: if same tool fails 3+ times, inject a hint
                    if not is_bash_exit and self._failure_tracker[call.name] >= 3:
                        console.print(f"[yellow]⚠ Tool {call.name} failed {self._failure_tracker[call.name]} times consecutively[/yellow]")
                        result = ToolResult(
                            success=False,
                            output="",
                            error=f"{result.error}\n\nNOTE: This tool has failed multiple times. Please try a different approach or explain the issue to the user.",
                        )

                # Add tool result to messages
                self.messages.append(
                    Message(
                        role="tool",
                        content=result.output if result.success else f"Error: {result.error}",
                        tool_call_id=call.id,
                        name=call.name,
                    )
                )
            
            # If all tools failed 5+ times each, break out
            has_failures = any(v > 0 for v in self._failure_tracker.values())
            if all_failed and has_failures and all(v >= 5 for v in self._failure_tracker.values() if v > 0):
                console.print("[red]Breaking out of loop - multiple consecutive failures detected[/red]")
                return "I encountered repeated errors and couldn't complete the task. Please check the error messages above and try a different approach."

        return "Maximum iterations reached. Please try a simpler request."

    def reset(self) -> None:
        """Reset the conversation history."""
        self.messages = []
