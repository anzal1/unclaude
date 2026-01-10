"""UNCLAUDE.md context loader for project-specific configuration."""

from pathlib import Path
from typing import Any

import yaml


class ContextLoader:
    """Loads and parses UNCLAUDE.md files for project context."""

    def __init__(self, project_path: Path | None = None):
        """Initialize the context loader.

        Args:
            project_path: Path to the project directory. Defaults to cwd.
        """
        self.project_path = project_path or Path.cwd()
        self.global_path = Path.home() / ".unclaude" / "UNCLAUDE.md"
        self._context: dict[str, Any] = {}

    def _parse_unclaude_md(self, content: str) -> dict[str, Any]:
        """Parse UNCLAUDE.md content into structured data.

        Args:
            content: The markdown content.

        Returns:
            Parsed context dictionary.
        """
        result: dict[str, Any] = {
            "commands": [],
            "code_style": [],
            "architecture": [],
            "skills": {},
            "raw_content": content,
        }

        current_section = None
        current_skill = None
        skill_content: list[str] = []

        for line in content.split("\n"):
            line_stripped = line.strip()

            # Section headers
            if line_stripped.startswith("## "):
                section_name = line_stripped[3:].lower().strip()
                if "command" in section_name:
                    current_section = "commands"
                elif "style" in section_name:
                    current_section = "code_style"
                elif "architecture" in section_name:
                    current_section = "architecture"
                elif "skill" in section_name:
                    current_section = "skills"
                else:
                    current_section = section_name
                current_skill = None
                continue

            # Skill definition
            if current_section == "skills" and line_stripped.startswith("skill:"):
                if current_skill and skill_content:
                    result["skills"][current_skill] = "\n".join(skill_content)
                current_skill = line_stripped[6:].strip()
                skill_content = []
                continue

            # Collect skill content
            if current_skill:
                skill_content.append(line)
                continue

            # List items for other sections
            if line_stripped.startswith("- ") and current_section:
                item = line_stripped[2:].strip()
                if current_section in result and isinstance(result[current_section], list):
                    result[current_section].append(item)

        # Save last skill if any
        if current_skill and skill_content:
            result["skills"][current_skill] = "\n".join(skill_content)

        return result

    def load(self) -> dict[str, Any]:
        """Load context from UNCLAUDE.md files.

        Loads in order (later overrides earlier):
        1. Global ~/.unclaude/UNCLAUDE.md
        2. Project ./UNCLAUDE.md
        3. Project ./.unclaude/UNCLAUDE.md

        Returns:
            Merged context dictionary.
        """
        contexts = []

        # Global context
        if self.global_path.exists():
            content = self.global_path.read_text()
            contexts.append(self._parse_unclaude_md(content))

        # Project root context
        project_unclaude = self.project_path / "UNCLAUDE.md"
        if project_unclaude.exists():
            content = project_unclaude.read_text()
            contexts.append(self._parse_unclaude_md(content))

        # Project .unclaude directory context
        project_dir_unclaude = self.project_path / ".unclaude" / "UNCLAUDE.md"
        if project_dir_unclaude.exists():
            content = project_dir_unclaude.read_text()
            contexts.append(self._parse_unclaude_md(content))

        # Merge contexts
        merged: dict[str, Any] = {
            "commands": [],
            "code_style": [],
            "architecture": [],
            "skills": {},
            "raw_content": "",
        }

        for ctx in contexts:
            merged["commands"].extend(ctx.get("commands", []))
            merged["code_style"].extend(ctx.get("code_style", []))
            merged["architecture"].extend(ctx.get("architecture", []))
            merged["skills"].update(ctx.get("skills", {}))
            if ctx.get("raw_content"):
                merged["raw_content"] += "\n\n" + ctx["raw_content"]

        self._context = merged
        return merged

    def get_system_prompt_addition(self) -> str:
        """Get additional system prompt content from context.

        Returns:
            String to append to system prompt.
        """
        if not self._context:
            self.load()

        parts = []
        
        # Include raw UNCLAUDE.md content first (most important)
        if self._context.get("raw_content"):
            parts.append("## Project Configuration (from UNCLAUDE.md)")
            parts.append(self._context["raw_content"].strip())
            parts.append("")  # Separator

        # Also include structured data for backwards compatibility
        if self._context.get("commands"):
            parts.append("## Available Commands")
            for cmd in self._context["commands"]:
                parts.append(f"- {cmd}")

        if self._context.get("code_style"):
            parts.append("\n## Code Style Guidelines")
            for style in self._context["code_style"]:
                parts.append(f"- {style}")

        if self._context.get("architecture"):
            parts.append("\n## Project Architecture")
            for arch in self._context["architecture"]:
                parts.append(f"- {arch}")

        if self._context.get("skills"):
            parts.append("\n## Available Skills")
            for skill_name in self._context["skills"]:
                parts.append(f"- {skill_name}")

        return "\n".join(parts) if parts else ""

    def get_skill(self, name: str) -> str | None:
        """Get a specific skill definition.

        Args:
            name: Name of the skill.

        Returns:
            Skill content or None if not found.
        """
        if not self._context:
            self.load()
        return self._context.get("skills", {}).get(name)
