"""Enhanced agent loop with integrated security, routing, sessions, and context management.

This module provides EnhancedAgentLoop, which wraps the existing AgentLoop
with the new architecture modules:

1. Auth & Security    → Capability-based tool execution, audit logging
2. Session Management → JSONL persistence, session recovery
3. Context Engine     → Bootstrap files, pruning, compaction
4. Smart Routing      → Cost-optimized model selection per request
5. Hierarchical Memory → Salience-scored, cross-referenced memory
6. Heartbeat          → Proactive background tasks

The EnhancedAgentLoop is a drop-in replacement for AgentLoop.
"""

import asyncio
import json
import os
import uuid
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from unclaude.config import get_settings
from unclaude.context import ContextLoader
from unclaude.hooks import HooksEngine
from unclaude.memory import MemoryStore
from unclaude.memory_v2 import HierarchicalMemory, MemoryLayer, MemoryImportance
from unclaude.providers import Message, Provider, ToolCall, ToolDefinition
from unclaude.tools import Tool, ToolResult, get_default_tools

# New architecture modules
from unclaude.auth import (
    Capability,
    CapabilitySet,
    SandboxPolicy,
    PolicyEngine,
    PolicyViolation,
    AuditLog,
    AuditEvent,
    AuditEventType,
    SessionManager,
    Session,
)
from unclaude.sessions.manager import (
    SessionStore,
    SessionKey,
    SessionMessage,
    ConversationSession,
)
from unclaude.context_engine.bootstrap import BootstrapLoader
from unclaude.context_engine.pruning import ContextPruner
from unclaude.context_engine.compaction import ContextCompactor
from unclaude.routing import SmartRouter, RoutingProfile
from unclaude.heartbeat import HeartbeatManager

console = Console()


ENHANCED_SYSTEM_PROMPT = """You are UnClaude, a world-class open-source AI coding agent.

You operate with capability-based security: each tool execution is authorized
against your current capability set. You cannot exceed your permissions.

CORE PRINCIPLES:
1. **PLAN FIRST**: Complex tasks require a plan with checkpoints.
2. **PARALLELISM**: Execute independent operations concurrently.
3. **VERIFY**: Always verify changes (run tests, check output).
4. **MEMORY**: Use hierarchical memory. Store important findings proactively.
5. **SAFETY**: Read before editing. Respect file/network boundaries.
6. **SECURITY**: Never expose credentials, secrets, or API keys.

FILESYSTEM AWARENESS:
- "My system", "my computer", "my files" = the user's home directory (~), NOT the project directory.
  Search ~/Documents, ~/Downloads, ~/Desktop, ~/Pictures, ~/Music, etc.
- NEVER search inside .venv/, node_modules/, __pycache__/, .git/objects/, or other dependency/build directories.
  These contain thousands of irrelevant library files.
- When looking for user files (documents, images, videos), use `find ~ -name '*.pdf'` or similar shell commands.
  Do NOT use file_glob on the project directory — that only finds project source files.
- Use `mdfind` (macOS Spotlight) for fast system-wide file search when available.
- The project directory ({cwd}) contains SOURCE CODE. The user's HOME (~) contains their PERSONAL FILES.

Current working directory: {cwd}
Home directory: {home}
Session: {session_id}
Security profile: {security_profile}
Routing profile: {routing_profile}

{bootstrap_context}
{context_additions}
{skills_context}
"""


class EnhancedAgentLoop:
    """Enhanced agentic loop with full architecture integration.

    Drop-in replacement for AgentLoop with:
    - Capability-based security (replaces simple permission checks)
    - Session persistence with JSONL (replaces SQLite-only)
    - Smart model routing (replaces single-model)
    - Context pruning & compaction (prevents context overflow)
    - Hierarchical memory (replaces flat LIKE search)
    - Audit trail (every action logged)
    """

    def __init__(
        self,
        provider: Provider | None = None,
        tools: list[Tool] | None = None,
        max_iterations: int = 50,
        project_path: Path | None = None,
        enable_memory: bool = True,
        conversation_id: str | None = None,
        system_prompt: str | None = None,
        # New architecture options
        security_profile: str = "developer",
        routing_profile: RoutingProfile = RoutingProfile.AUTO,
        enable_audit: bool = True,
        enable_heartbeat: bool = False,
        preferred_provider: str | None = None,
    ):
        self.settings = get_settings()
        self.tools = tools or get_default_tools()
        self.max_iterations = max_iterations
        self.messages: list[Message] = []
        self._tool_map: dict[str, Tool] = {
            tool.name: tool for tool in self.tools}

        # ─── Stuck Detection ───
        # (name, args_hash)
        self._recent_tool_calls: list[tuple[str, str]] = []
        self._stuck_warnings_given: int = 0
        self._iterations_without_progress: int = 0

        # Project context
        self.project_path = project_path or Path.cwd()
        self.context_loader = ContextLoader(self.project_path)

        # ─── Auth & Security ───
        self.capability_set = CapabilitySet(security_profile)
        self.policy_engine = PolicyEngine(
            capabilities=self.capability_set,
            policy=SandboxPolicy.for_profile(security_profile),
        )
        self.security_profile = security_profile
        self.session_manager = SessionManager()

        # Create or restore session
        if conversation_id:
            self.session = self.session_manager.get_session(conversation_id)
            if not self.session:
                self.session = self.session_manager.create_session(
                    name="enhanced",
                    session_type="interactive",
                    profile=security_profile,
                    policy_profile=security_profile,
                    project_path=str(self.project_path),
                )
        else:
            self.session = self.session_manager.create_session(
                name="enhanced",
                session_type="interactive",
                profile=security_profile,
                policy_profile=security_profile,
                project_path=str(self.project_path),
            )
        self.conversation_id = self.session.session_id

        # ─── Audit ───
        self.enable_audit = enable_audit
        self.audit_log = AuditLog() if enable_audit else None
        if self.audit_log:
            self.audit_log.log(AuditEvent(
                event_type=AuditEventType.SESSION_START,
                session_id=self.conversation_id,
                data={
                    "security_profile": security_profile,
                    "project": str(self.project_path),
                },
            ))

        # ─── Smart Routing ───
        self.routing_profile = routing_profile
        self.router = SmartRouter(
            default_profile=routing_profile,
            preferred_provider=preferred_provider or self.settings.default_provider,
        )

        # Create provider (may be overridden by routing)
        self.provider = provider or Provider()

        # ─── Session Persistence ───
        self.session_store = SessionStore()
        self.conv_session = self.session_store.create(
            agent_id="unclaude",
            session_id=self.conversation_id,
            project_path=str(self.project_path),
        )
        self.session_key = self.conv_session.key

        # ─── Context Engine ───
        self.bootstrap_loader = BootstrapLoader(self.project_path)
        self.context_pruner = ContextPruner(max_context_tokens=100_000)
        self.context_compactor = ContextCompactor(provider=self.provider)

        # ─── Memory ───
        self.enable_memory = enable_memory
        self.memory_store = MemoryStore() if enable_memory else None
        self.hierarchical_memory = HierarchicalMemory() if enable_memory else None

        # ─── Heartbeat ───
        self.enable_heartbeat = enable_heartbeat
        self.heartbeat = HeartbeatManager() if enable_heartbeat else None

        # ─── Hooks ───
        self.hooks_engine = HooksEngine(self.project_path)

        # ─── Internal State ───
        self.system_prompt = system_prompt or ENHANCED_SYSTEM_PROMPT
        self._auto_approve_all = False
        self._auto_approve_tools: set[str] = set()
        self._failure_tracker: dict[str, int] = {}

    def _get_tool_definitions(self) -> list[ToolDefinition]:
        """Get tool definitions filtered by capabilities."""
        definitions = []
        for tool in self.tools:
            definitions.append(tool.to_definition())
        return definitions

    def _build_skills_context(self) -> str:
        """Load skills and format them as context for the system prompt."""
        try:
            from unclaude.skills import SkillsEngine

            engine = SkillsEngine(project_path=self.project_path)
            skills = engine.load_skills()

            if not skills:
                return ""

            parts = ["## Learned Skills\n"]
            for name, skill in skills.items():
                parts.append(f"### {name}: {skill.description}\n")
                for i, step in enumerate(skill.steps, 1):
                    parts.append(f"{i}. {step.description}")
                parts.append("")

            return "\n".join(parts)
        except Exception:
            return ""

    def _messages_to_dicts(self) -> list[dict[str, Any]]:
        """Convert Message objects to dicts for pruner/compactor."""
        result = []
        for m in self.messages:
            d: dict[str, Any] = {"role": m.role}
            if m.content is not None:
                d["content"] = m.content
            if m.tool_calls:
                d["tool_calls"] = m.tool_calls
            if m.tool_call_id:
                d["tool_call_id"] = m.tool_call_id
            if m.name:
                d["name"] = m.name
            result.append(d)
        return result

    def _dicts_to_messages(self, dicts: list[dict[str, Any]]) -> list[Message]:
        """Convert dicts back to Message objects."""
        return [
            Message(
                role=d["role"],
                content=d.get("content"),
                tool_calls=d.get("tool_calls"),
                tool_call_id=d.get("tool_call_id"),
                name=d.get("name"),
            )
            for d in dicts
        ]

    def _persist_message(self, role: str, content: str | None, **kwargs: Any) -> None:
        """Persist a message to the JSONL session store."""
        msg = SessionMessage(
            role=role,
            content=content,
            tool_calls=kwargs.get("tool_calls"),
            tool_call_id=kwargs.get("tool_call_id"),
            name=kwargs.get("name"),
        )
        self.session_store.append(self.session_key, msg)

    def _tool_to_capability(
        self, call: ToolCall
    ) -> tuple[Capability | None, dict[str, Any]]:
        """Map a tool call to the appropriate capability and policy kwargs.

        Returns:
            (capability, kwargs_for_enforce) tuple.
            capability is None for tools that don't need policy checks.
        """
        args = call.arguments
        name = call.name

        if name in ("file_read", "file_search", "grep_search"):
            path = args.get("path") or args.get(
                "file_path") or args.get("pattern", "")
            return Capability.FILE_READ, {"path": path}
        elif name in ("file_write", "file_edit", "file_create"):
            path = args.get("path") or args.get("file_path", "")
            return Capability.FILE_WRITE, {"path": path}
        elif name in ("bash_execute", "shell_execute"):
            command = args.get("command", "")
            return Capability.EXEC_SHELL, {"command": command}
        elif name in ("web_fetch", "browser_navigate"):
            url = args.get("url", "")
            return Capability.NET_FETCH, {"url": url}
        elif name in ("memory_store", "memory_search"):
            cap = Capability.MEMORY_WRITE if "store" in name else Capability.MEMORY_READ
            return cap, {}

        # No specific capability mapping — allow by default
        return None, {}

    async def _check_permission(self, tool: Tool, call: ToolCall) -> bool:
        """Check permission using capability-based security.

        Replaces the old y/n/a/t prompt with policy engine checks,
        falling back to user prompt only when policy says 'ask'.
        """
        # 1. Map tool name to capability and extract policy-relevant args
        capability, policy_kwargs = self._tool_to_capability(call)

        if capability:
            try:
                self.policy_engine.enforce(capability, **policy_kwargs)
                # Policy says OK - auto-approve
                if self.audit_log:
                    self.audit_log.log(AuditEvent(
                        event_type=AuditEventType.PERMISSION_GRANTED,
                        session_id=self.conversation_id,
                        tool_name=call.name,
                        capability=capability.value,
                        data={"method": "policy"},
                    ))
                return True
            except PolicyViolation as e:
                # Policy explicitly denied
                if self.audit_log:
                    self.audit_log.log(AuditEvent(
                        event_type=AuditEventType.POLICY_VIOLATION,
                        session_id=self.conversation_id,
                        tool_name=call.name,
                        capability=capability.value if capability else "",
                        data={"reason": str(e)},
                        success=False,
                        risk_level="high",
                    ))

        # 2. Fall back to user permission (for non-auto-approved tools)
        if not tool.requires_permission:
            return True

        if self._auto_approve_all:
            return True

        if tool.name in self._auto_approve_tools:
            return True

        # Show permission request
        console.print(
            Panel(
                f"[bold yellow]Permission Required[/bold yellow]\n\n"
                f"Tool: [cyan]{tool.name}[/cyan]\n"
                f"Arguments: {call.arguments}\n"
                f"[dim]Policy: requires manual approval[/dim]",
                title="🔒 Capability Check",
            )
        )
        console.print(
            "[dim]y=yes, n=no, a=yes to all, t=yes to this tool type[/dim]")

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

        if self.audit_log:
            self.audit_log.log(AuditEvent(
                event_type=AuditEventType.PERMISSION_DENIED,
                session_id=self.conversation_id,
                tool_name=call.name,
                data={"method": "user_denied"},
                success=False,
            ))
        return False

    async def _execute_tool(self, call: ToolCall) -> ToolResult:
        """Execute a tool call with security, auditing, and hooks."""
        tool = self._tool_map.get(call.name)
        if not tool:
            return ToolResult(success=False, output="", error=f"Unknown tool: {call.name}")

        # Permission check (policy + user fallback)
        if not await self._check_permission(tool, call):
            return ToolResult(success=False, output="", error="Permission denied")

        # Audit: tool execution start
        if self.audit_log:
            self.audit_log.log(AuditEvent(
                event_type=AuditEventType.TOOL_REQUEST,
                session_id=self.conversation_id,
                tool_name=call.name,
                data={"args": call.arguments},
            ))

        console.print(f"[dim]Executing {call.name}...[/dim]")
        try:
            # Pre-tool hooks
            await self.hooks_engine.execute_hooks("pre_tool", call.name, call.arguments)

            # Execute
            result = await tool.execute(**call.arguments)

            # Post-tool hooks
            await self.hooks_engine.execute_hooks(
                "post_tool", call.name, call.arguments, result
            )

            # Audit: success
            if self.audit_log:
                self.audit_log.log(AuditEvent(
                    event_type=AuditEventType.TOOL_RESULT,
                    session_id=self.conversation_id,
                    tool_name=call.name,
                    data={"output_len": len(result.output)},
                ))

            return result

        except Exception as e:
            # Audit: failure
            if self.audit_log:
                self.audit_log.log(AuditEvent(
                    event_type=AuditEventType.TOOL_ERROR,
                    session_id=self.conversation_id,
                    tool_name=call.name,
                    data={"error": str(e)},
                    success=False,
                    risk_level="medium",
                ))
            return ToolResult(success=False, output="", error=str(e))

    def _detect_stuck(self, iteration: int) -> str | None:
        """Detect if the agent is stuck in a loop and return a nudge message.

        Returns None if not stuck, or a warning/bail message if stuck.
        Uses pattern detection rather than hard timeouts:
        - Repeated identical tool calls (same name + same args)
        - Same tool called excessively without progress
        - Multiple iterations with zero successful tool calls
        """
        import hashlib

        recent = self._recent_tool_calls

        # Need at least a few calls to detect patterns
        if len(recent) < 4:
            return None

        last_8 = recent[-8:]
        last_5 = recent[-5:]

        # Pattern 1: Identical call repeated 3+ times in last 5
        if len(last_5) >= 3:
            unique_calls = set(last_5[-3:])
            if len(unique_calls) == 1:
                self._stuck_warnings_given += 1
                if self._stuck_warnings_given >= 3:
                    return "BAIL"
                tool_name = last_5[-1][0]
                return (
                    f"[SYSTEM] You are repeating the exact same '{tool_name}' call "
                    f"multiple times with identical arguments. This is not making progress. "
                    f"STOP using this approach. Either try a completely different strategy "
                    f"or conclude with what you have so far."
                )

        # Pattern 2: Same tool dominates last 8 calls (6+ out of 8)
        if len(last_8) >= 6:
            tool_names = [t[0] for t in last_8]
            from collections import Counter
            counts = Counter(tool_names)
            dominant_tool, dominant_count = counts.most_common(1)[0]
            if dominant_count >= 6:
                self._stuck_warnings_given += 1
                if self._stuck_warnings_given >= 3:
                    return "BAIL"
                return (
                    f"[SYSTEM] You've called '{dominant_tool}' {dominant_count} times "
                    f"in the last {len(last_8)} tool calls. You appear to be stuck. "
                    f"Step back and reconsider your approach. If the task cannot be "
                    f"completed this way, summarize what you found and conclude."
                )

        # Pattern 3: No progress for many iterations
        if self._iterations_without_progress >= 5:
            self._stuck_warnings_given += 1
            if self._stuck_warnings_given >= 3:
                return "BAIL"
            return (
                "[SYSTEM] Multiple iterations have passed without any successful "
                "tool execution. You may be approaching this incorrectly. "
                "Reconsider the problem, try a simpler approach, or summarize "
                "your findings and conclude."
            )

        return None

    def _track_tool_call(self, tool_name: str, arguments: dict) -> None:
        """Track a tool call for stuck detection."""
        import hashlib
        # Hash the arguments for comparison (normalize by sorting keys)
        args_str = json.dumps(arguments, sort_keys=True, default=str)
        args_hash = hashlib.md5(args_str.encode()).hexdigest()[:12]
        self._recent_tool_calls.append((tool_name, args_hash))
        # Keep only last 20
        if len(self._recent_tool_calls) > 20:
            self._recent_tool_calls = self._recent_tool_calls[-20:]

    async def run(self, user_input: str) -> str:
        """Process a user request through the enhanced agentic loop.

        Integrates: routing → context → security → execution → memory → pruning
        """
        # ─── Smart Routing ───
        routing_decision = self.router.route(
            message=user_input,
            profile=self.routing_profile,
            conversation_depth=len(
                [m for m in self.messages if m.role == "user"]),
            conversation_id=self.conversation_id,
        )
        console.print(
            f"[dim]Route: {routing_decision.tier.value} → "
            f"{routing_decision.model_id} "
            f"(${routing_decision.estimated_cost_per_1k:.4f}/1K)[/dim]"
        )

        # ─── Initialize System Prompt ───
        if not self.messages:
            # Load bootstrap context as formatted string
            bootstrap_context = self.bootstrap_loader.build_context_prompt()

            # Load UNCLAUDE.md context
            context_additions = self.context_loader.get_system_prompt_addition()

            # Load skills
            skills_context = self._build_skills_context()

            system_content = self.system_prompt.format(
                cwd=str(self.project_path),
                home=str(Path.home()),
                session_id=self.conversation_id[:12],
                security_profile=self.security_profile,
                routing_profile=self.routing_profile.value,
                bootstrap_context=bootstrap_context,
                context_additions=context_additions,
                skills_context=skills_context,
            )

            system_msg = Message(role="system", content=system_content)
            self.messages.append(system_msg)

            # Persist to JSONL session store
            self._persist_message("system", system_content)

        # ─── Add User Message ───
        user_msg = Message(role="user", content=user_input)
        self.messages.append(user_msg)
        self._persist_message("user", user_input)

        # ─── Hierarchical Memory Recall ───
        if self.enable_memory and self.hierarchical_memory:
            memories = self.hierarchical_memory.search(
                query=user_input,
                project_path=str(self.project_path),
                limit=5,
            )
            if memories:
                memory_context = "\n".join([
                    f"- [{m.layer.value}/{m.importance.value}] {m.content[:200]}"
                    for m in memories
                    if user_input not in m.content  # Skip exact matches
                ])
                if memory_context:
                    console.print(Panel(
                        f"[dim]Recalled {len(memories)} memories "
                        f"(salience: {memories[0].salience:.2f})[/dim]",
                        title="Memory 🧠",
                    ))
                    self.messages.append(Message(
                        role="system",
                        content=f"RECALLED MEMORY:\n{memory_context}\nUse if relevant.",
                    ))

        # ─── Context Pruning ───
        # Convert to dicts, prune, convert back
        msg_dicts = self._messages_to_dicts()
        pruned_dicts = self.context_pruner.prune(msg_dicts)
        self.messages = self._dicts_to_messages(pruned_dicts)

        # ─── Agentic Loop ───
        iterations = 0
        tool_definitions = self._get_tool_definitions()

        while iterations < self.max_iterations:
            iterations += 1

            # Check if compaction needed
            if len(self.messages) > 50 and iterations % 10 == 0:
                try:
                    msg_dicts = self._messages_to_dicts()
                    summary, compacted_dicts = await self.context_compactor.compact(
                        msg_dicts
                    )
                    self.messages = self._dicts_to_messages(compacted_dicts)
                    console.print("[dim]Context compacted[/dim]")
                except Exception:
                    pass  # Compaction is best-effort

            # LLM call
            console.print("[dim]Thinking...[/dim]")
            try:
                response = await self.provider.chat(
                    messages=self.messages,
                    tools=tool_definitions,
                )

                # Audit: LLM call
                if self.audit_log:
                    self.audit_log.log(AuditEvent(
                        event_type=AuditEventType.LLM_REQUEST,
                        session_id=self.conversation_id,
                        data={
                            "model": routing_decision.model_id,
                            "tier": routing_decision.tier.value,
                            "usage": response.usage,
                        },
                    ))

            except Exception as e:
                error_msg = str(e)
                console.print(f"[red]LLM Error: {error_msg[:200]}[/red]")

                # Try fallback models from routing decision
                for fallback in routing_decision.fallback_models:
                    try:
                        console.print(
                            f"[yellow]Trying fallback: {fallback}[/yellow]")
                        fallback_provider = Provider()
                        response = await fallback_provider.chat(
                            messages=self.messages,
                            tools=tool_definitions,
                        )
                        break
                    except Exception:
                        continue
                else:
                    # All fallbacks failed
                    if "empty" in error_msg.lower():
                        try:
                            response = await self.provider.chat(
                                messages=self.messages,
                                tools=None,
                            )
                        except Exception:
                            return f"Error: {error_msg}. Please try rephrasing."
                    else:
                        return f"Error: {error_msg}. Please try again."

            # ─── No Tool Calls → Final Response ───
            if not response.tool_calls:
                if response.content:
                    self.messages.append(
                        Message(role="assistant", content=response.content)
                    )
                    self._persist_message("assistant", response.content)

                    # Store response in hierarchical memory
                    if self.enable_memory and self.hierarchical_memory:
                        self.hierarchical_memory.store(
                            content=response.content[:500],
                            layer=MemoryLayer.RESOURCE,
                            importance=MemoryImportance.LOW,
                            tags=["response"],
                            project_path=str(self.project_path),
                        )

                # Flush audit buffer on conversation end
                if self.audit_log:
                    self.audit_log.flush()

                return response.content or "I'm not sure how to respond to that."

            # ─── Execute Tool Calls ───
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

            all_failed = True
            any_progress = False
            for call in response.tool_calls:
                # Track for stuck detection
                self._track_tool_call(call.name, call.arguments)

                result = await self._execute_tool(call)

                if result.success:
                    output = (
                        result.output[:500] + "..."
                        if len(result.output) > 500
                        else result.output
                    )
                    console.print(
                        f"[green]✓[/green] {call.name}: {output[:100]}...")
                    self._failure_tracker[call.name] = 0
                    all_failed = False
                    any_progress = True

                    # Store successful tool results in memory
                    if self.enable_memory and self.hierarchical_memory:
                        if call.name in ("file_write", "file_edit", "bash_execute"):
                            self.hierarchical_memory.store(
                                content=f"Tool {call.name}: {json.dumps(call.arguments)[:300]}",
                                layer=MemoryLayer.RESOURCE,
                                importance=MemoryImportance.MEDIUM,
                                tags=[call.name, "tool_result"],
                                project_path=str(self.project_path),
                            )
                else:
                    console.print(f"[red]✗[/red] {call.name}: {result.error}")
                    is_bash_exit = call.name == "bash_execute" and "Exit code" in (
                        result.error or ""
                    )

                    if not is_bash_exit:
                        self._failure_tracker[call.name] = (
                            self._failure_tracker.get(call.name, 0) + 1
                        )

                    if (
                        not is_bash_exit
                        and self._failure_tracker.get(call.name, 0) >= 3
                    ):
                        console.print(
                            f"[yellow]⚠ Tool {call.name} failed "
                            f"{self._failure_tracker[call.name]} times[/yellow]"
                        )
                        result = ToolResult(
                            success=False,
                            output="",
                            error=(
                                f"{result.error}\n\nNOTE: This tool has failed "
                                f"multiple times. Try a different approach."
                            ),
                        )

                self.messages.append(
                    Message(
                        role="tool",
                        content=(
                            result.output
                            if result.success
                            else f"Error: {result.error}"
                        ),
                        tool_call_id=call.id,
                        name=call.name,
                    )
                )

            # Break on repeated failures
            has_failures = any(v > 0 for v in self._failure_tracker.values())
            if (
                all_failed
                and has_failures
                and all(
                    v >= 5 for v in self._failure_tracker.values() if v > 0
                )
            ):
                console.print("[red]Breaking out - repeated failures[/red]")
                return (
                    "I encountered repeated errors. Please check the error "
                    "messages and try a different approach."
                )

            # ─── Smart Stuck Detection ───
            if any_progress:
                self._iterations_without_progress = 0
            else:
                self._iterations_without_progress += 1

            stuck_signal = self._detect_stuck(iterations)
            if stuck_signal == "BAIL":
                console.print(
                    "[yellow]⚠ Agent is stuck in a loop — "
                    "auto-concluding[/yellow]"
                )
                # Give the agent one last chance to summarize
                self.messages.append(
                    Message(
                        role="user",
                        content=(
                            "[SYSTEM] You have been going in circles and "
                            "multiple warnings were ignored. You MUST stop "
                            "using tools and provide your final answer NOW "
                            "with whatever you have found so far."
                        ),
                    )
                )
                try:
                    final = await self.provider.chat(
                        messages=self.messages, tools=None,
                    )
                    return final.content or (
                        "I was unable to complete this task — I got stuck "
                        "in a loop. Please try rephrasing or breaking it "
                        "into smaller steps."
                    )
                except Exception:
                    return (
                        "I was unable to complete this task — I got stuck "
                        "in a loop. Please try rephrasing or breaking it "
                        "into smaller steps."
                    )
            elif stuck_signal:
                console.print(
                    f"[yellow]⚠ Stuck detected (warning "
                    f"{self._stuck_warnings_given})[/yellow]"
                )
                # Inject the warning as a user message so the LLM sees it
                self.messages.append(
                    Message(role="user", content=stuck_signal)
                )

        # Flush audit on max iterations
        if self.audit_log:
            self.audit_log.flush()
        return "Maximum iterations reached. Please try a simpler request."

    async def start_heartbeat(self) -> None:
        """Start the heartbeat system for proactive tasks."""
        if self.heartbeat and self.enable_heartbeat:
            await self.heartbeat.start()

    async def stop_heartbeat(self) -> None:
        """Stop the heartbeat system."""
        if self.heartbeat:
            await self.heartbeat.stop()

    def get_session_summary(self) -> dict[str, Any]:
        """Get a summary of the current session."""
        summary: dict[str, Any] = {
            "session_id": self.conversation_id,
            "security_profile": self.security_profile,
            "routing_profile": self.routing_profile.value,
            "messages": len(self.messages),
            "routing_stats": self.router.stats,
        }

        if self.audit_log:
            summary["audit"] = self.audit_log.get_session_summary(
                self.conversation_id
            )

        if self.hierarchical_memory:
            summary["memory"] = self.hierarchical_memory.get_stats()

        return summary

    def reset(self) -> None:
        """Reset the conversation."""
        self.messages = []
        self._failure_tracker = {}
        self._auto_approve_all = False
        self._auto_approve_tools = set()

        # Audit session end
        if self.audit_log:
            self.audit_log.log(AuditEvent(
                event_type=AuditEventType.SESSION_END,
                session_id=self.conversation_id,
                data={},
            ))
            self.audit_log.flush()
