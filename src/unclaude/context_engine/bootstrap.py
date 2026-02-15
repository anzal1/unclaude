"""Bootstrap file loader for project context.

OpenClaw uses multiple context files to shape agent behavior:
- SOUL.md: Agent personality, values, communication style
- AGENTS.md: Agent coordination rules for multi-agent setups
- TOOLS.md: Tool usage guidelines and best practices
- IDENTITY.md: Agent identity and branding
- USER.md: User preferences and context
- HEARTBEAT.md: Proactive task definitions
- MEMORY.md: Memory guidelines and curation rules
- UNCLAUDE.md: Project-specific config (existing, stays as-is)

Bootstrap files are loaded on-demand:
- Main agent gets ALL files
- Sub-agents only get AGENTS.md + TOOLS.md (minimal context)
- Headless/API mode skips IDENTITY.md

Long files are automatically truncated (head + tail) with a marker.
"""

from pathlib import Path
from typing import Any


# Maximum characters per bootstrap file (prevents context blowout)
MAX_BOOTSTRAP_CHARS = 8000

# Bootstrap file names and their purposes
BOOTSTRAP_FILES = {
    "SOUL.md": {
        "purpose": "Agent personality, values, and communication style",
        "required": False,
        "subagent": False,
    },
    "AGENTS.md": {
        "purpose": "Multi-agent coordination and delegation rules",
        "required": False,
        "subagent": True,
    },
    "TOOLS.md": {
        "purpose": "Tool usage guidelines and best practices",
        "required": False,
        "subagent": True,
    },
    "IDENTITY.md": {
        "purpose": "Agent identity configuration",
        "required": False,
        "subagent": False,
    },
    "USER.md": {
        "purpose": "User preferences and personal context",
        "required": False,
        "subagent": False,
    },
    "HEARTBEAT.md": {
        "purpose": "Proactive task definitions for heartbeat system",
        "required": False,
        "subagent": False,
    },
    "MEMORY.md": {
        "purpose": "Memory curation rules and guidelines",
        "required": False,
        "subagent": False,
    },
    "UNCLAUDE.md": {
        "purpose": "Project-specific configuration (commands, style, architecture)",
        "required": False,
        "subagent": True,
    },
}


class BootstrapLoader:
    """Loads and manages bootstrap context files.

    Files are searched in order:
    1. Project root (./)
    2. Project config dir (./.unclaude/)
    3. Global config (~/.unclaude/)
    """

    def __init__(
        self,
        project_path: Path | None = None,
        global_path: Path | None = None,
        max_chars: int = MAX_BOOTSTRAP_CHARS,
    ):
        self.project_path = project_path or Path.cwd()
        self.global_path = global_path or (Path.home() / ".unclaude")
        self.max_chars = max_chars
        self._cache: dict[str, str] = {}

    def _search_paths(self, filename: str) -> list[Path]:
        """Get the search paths for a bootstrap file."""
        return [
            self.project_path / filename,
            self.project_path / ".unclaude" / filename,
            self.global_path / filename,
        ]

    def _load_file(self, filename: str) -> str | None:
        """Load a bootstrap file from the first found location.

        Returns:
            File content (possibly truncated) or None if not found.
        """
        if filename in self._cache:
            return self._cache[filename]

        for path in self._search_paths(filename):
            if path.exists():
                try:
                    content = path.read_text(encoding="utf-8")
                    content = self._truncate(content, filename)
                    self._cache[filename] = content
                    return content
                except (OSError, UnicodeDecodeError):
                    continue

        return None

    def _truncate(self, content: str, filename: str) -> str:
        """Truncate content if too long, keeping head + tail.

        This is critical for managing context window size.
        We keep the first 60% and last 30% of the content,
        inserting a marker in between.
        """
        if len(content) <= self.max_chars:
            return content

        head_size = int(self.max_chars * 0.6)
        tail_size = int(self.max_chars * 0.3)

        head = content[:head_size]
        tail = content[-tail_size:]

        truncated_count = len(content) - head_size - tail_size
        marker = f"\n\n... [{truncated_count} characters truncated from {filename}] ...\n\n"

        return head + marker + tail

    def load_all(self, is_subagent: bool = False) -> dict[str, str]:
        """Load all applicable bootstrap files.

        Args:
            is_subagent: If True, only load files marked for subagent use.

        Returns:
            Dict of filename -> content for found files.
        """
        files = {}

        for filename, config in BOOTSTRAP_FILES.items():
            # Skip files not meant for subagents
            if is_subagent and not config["subagent"]:
                continue

            content = self._load_file(filename)
            if content:
                files[filename] = content

        return files

    def build_context_prompt(
        self,
        is_subagent: bool = False,
        session_key: str | None = None,
    ) -> str:
        """Build the full context prompt from bootstrap files.

        This generates the context injection that goes into the system prompt.

        Args:
            is_subagent: Whether this is for a sub-agent.
            session_key: Optional session key for session-specific context.

        Returns:
            Formatted context string for system prompt injection.
        """
        files = self.load_all(is_subagent=is_subagent)

        if not files:
            return ""

        parts = ["## Project Context\n"]

        # SOUL.md gets special treatment - it defines personality
        if "SOUL.md" in files:
            parts.append(f"### Agent Personality\n{files.pop('SOUL.md')}\n")

        # IDENTITY.md
        if "IDENTITY.md" in files:
            parts.append(f"### Identity\n{files.pop('IDENTITY.md')}\n")

        # USER.md
        if "USER.md" in files:
            parts.append(f"### User Context\n{files.pop('USER.md')}\n")

        # TOOLS.md
        if "TOOLS.md" in files:
            parts.append(f"### Tool Guidelines\n{files.pop('TOOLS.md')}\n")

        # AGENTS.md
        if "AGENTS.md" in files:
            parts.append(f"### Agent Coordination\n{files.pop('AGENTS.md')}\n")

        # MEMORY.md
        if "MEMORY.md" in files:
            parts.append(f"### Memory Guidelines\n{files.pop('MEMORY.md')}\n")

        # UNCLAUDE.md (legacy/existing)
        if "UNCLAUDE.md" in files:
            parts.append(
                f"### Project Configuration\n{files.pop('UNCLAUDE.md')}\n")

        # HEARTBEAT.md handled separately by heartbeat system
        files.pop("HEARTBEAT.md", None)

        # Any remaining files
        for filename, content in files.items():
            parts.append(f"### {filename}\n{content}\n")

        return "\n".join(parts)

    def get_heartbeat_tasks(self) -> list[dict[str, Any]]:
        """Parse HEARTBEAT.md for proactive task definitions.

        Format expected:
        ```
        ## Tasks

        ### task-name
        - interval: 30m
        - condition: always | on_idle | on_change
        - description: What this task does
        - prompt: The prompt to send to the agent
        ```

        Returns:
            List of task definitions.
        """
        content = self._load_file("HEARTBEAT.md")
        if not content:
            return []

        tasks = []
        current_task: dict[str, Any] | None = None

        for line in content.split("\n"):
            stripped = line.strip()

            if stripped.startswith("### "):
                if current_task:
                    tasks.append(current_task)
                current_task = {"name": stripped[4:].strip()}

            elif current_task and stripped.startswith("- "):
                # Parse key: value
                item = stripped[2:]
                if ":" in item:
                    key, value = item.split(":", 1)
                    current_task[key.strip()] = value.strip()

        if current_task:
            tasks.append(current_task)

        return tasks

    def create_template(self, filename: str) -> Path:
        """Create a template bootstrap file in the project.

        Args:
            filename: Which bootstrap file to create.

        Returns:
            Path to the created file.
        """
        templates = {
            "SOUL.md": """# Soul

Define your agent's personality and communication style here.

## Personality
- Be concise and direct
- Prefer showing code over describing it
- Ask clarifying questions when requirements are ambiguous

## Values
- Code quality over speed
- Security-first thinking
- Clear documentation
""",
            "TOOLS.md": """# Tool Guidelines

## File Editing
- Always read files before editing
- Use file_edit for small changes, file_write for new files
- Verify edits with a follow-up read

## Bash Execution
- Prefer non-destructive commands
- Always check exit codes
- Use timeouts for potentially long-running commands

## Git
- Commit frequently with clear messages
- Never force push without permission
""",
            "HEARTBEAT.md": """# Heartbeat Tasks

Define proactive tasks the agent should run periodically.

### check-tests
- interval: 30m
- condition: on_change
- description: Run test suite and report failures
- prompt: Run the test suite. If any tests fail, create a summary of failures.

### code-review
- interval: 1h
- condition: on_idle
- description: Review recent changes for issues
- prompt: Review git diff for the last hour. Flag any security issues or bugs.
""",
            "AGENTS.md": """# Agent Coordination

## Delegation Rules
- Spawn sub-agents for independent research tasks
- Keep sub-agents focused on single objectives
- Sub-agents should not modify files without explicit instruction

## Communication
- Sub-agents report findings, main agent makes decisions
- Share context through memory, not through long prompts
""",
        }

        output_dir = self.project_path / ".unclaude"
        output_dir.mkdir(parents=True, exist_ok=True)

        content = templates.get(
            filename, f"# {filename}\n\nAdd your content here.\n")
        output_path = output_dir / filename
        output_path.write_text(content)

        return output_path

    def clear_cache(self) -> None:
        """Clear the file cache."""
        self._cache.clear()
