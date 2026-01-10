"""Skills engine for UnClaude.

Skills are reusable AI workflows defined in UNCLAUDE.md files
or separate skill files.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SkillStep:
    """A single step in a skill workflow."""

    description: str
    command: str | None = None
    prompt: str | None = None
    condition: str | None = None


@dataclass
class Skill:
    """A reusable skill definition."""

    name: str
    description: str
    steps: list[SkillStep]
    parameters: dict[str, Any] = None

    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}


class SkillsEngine:
    """Engine for loading and executing skills."""

    def __init__(self, project_path: Path | None = None):
        """Initialize the skills engine.

        Args:
            project_path: Path to the project directory.
        """
        self.project_path = project_path or Path.cwd()
        self.global_skills_dir = Path.home() / ".unclaude" / "skills"
        self.project_skills_dir = self.project_path / ".unclaude" / "skills"
        self.skills: dict[str, Skill] = {}

    def _parse_skill_from_markdown(self, content: str) -> dict[str, Skill]:
        """Parse skills from markdown content.

        Args:
            content: Markdown content with skill definitions.

        Returns:
            Dictionary of skills.
        """
        skills = {}
        current_skill = None
        current_description = ""
        current_steps: list[SkillStep] = []

        for line in content.split("\n"):
            # Detect skill definition
            if line.strip().startswith("skill:"):
                # Save previous skill
                if current_skill:
                    skills[current_skill] = Skill(
                        name=current_skill,
                        description=current_description.strip(),
                        steps=current_steps,
                    )

                current_skill = line.strip()[6:].strip()
                current_description = ""
                current_steps = []
                continue

            if current_skill:
                # Parse description
                if line.strip().startswith("description:"):
                    current_description = line.strip()[12:].strip()
                    continue

                # Parse steps
                step_match = re.match(r"\s*(\d+)\.\s*(.*)", line)
                if step_match:
                    step_text = step_match.group(2)

                    # Check for command in backticks
                    cmd_match = re.search(r"`([^`]+)`", step_text)
                    command = cmd_match.group(1) if cmd_match else None

                    current_steps.append(
                        SkillStep(
                            description=step_text,
                            command=command,
                        )
                    )

        # Save last skill
        if current_skill:
            skills[current_skill] = Skill(
                name=current_skill,
                description=current_description.strip(),
                steps=current_steps,
            )

        return skills

    def _load_skill_file(self, skill_path: Path) -> Skill | None:
        """Load a skill from a YAML or markdown file.

        Args:
            skill_path: Path to the skill file.

        Returns:
            Skill or None.
        """
        if not skill_path.exists():
            return None

        content = skill_path.read_text()

        if skill_path.suffix in (".yaml", ".yml"):
            try:
                data = yaml.safe_load(content)
                steps = [
                    SkillStep(
                        description=s.get("description", ""),
                        command=s.get("command"),
                        prompt=s.get("prompt"),
                        condition=s.get("condition"),
                    )
                    for s in data.get("steps", [])
                ]
                return Skill(
                    name=data.get("name", skill_path.stem),
                    description=data.get("description", ""),
                    steps=steps,
                    parameters=data.get("parameters", {}),
                )
            except Exception:
                return None

        elif skill_path.suffix == ".md":
            skills = self._parse_skill_from_markdown(content)
            if skills:
                # Return first skill found
                return next(iter(skills.values()))

        return None

    def load_skills(self) -> dict[str, Skill]:
        """Load all available skills.

        Returns:
            Dictionary of skills.
        """
        self.skills = {}

        # Load global skills
        if self.global_skills_dir.exists():
            for skill_file in self.global_skills_dir.glob("*.yaml"):
                skill = self._load_skill_file(skill_file)
                if skill:
                    self.skills[skill.name] = skill

            for skill_file in self.global_skills_dir.glob("*.md"):
                skill = self._load_skill_file(skill_file)
                if skill:
                    self.skills[skill.name] = skill

        # Load project skills (override global)
        if self.project_skills_dir.exists():
            for skill_file in self.project_skills_dir.glob("*.yaml"):
                skill = self._load_skill_file(skill_file)
                if skill:
                    self.skills[skill.name] = skill

            for skill_file in self.project_skills_dir.glob("*.md"):
                skill = self._load_skill_file(skill_file)
                if skill:
                    self.skills[skill.name] = skill

        # Load skills from UNCLAUDE.md
        unclaude_md = self.project_path / "UNCLAUDE.md"
        if unclaude_md.exists():
            content = unclaude_md.read_text()
            md_skills = self._parse_skill_from_markdown(content)
            self.skills.update(md_skills)

        return self.skills

    def get_skill(self, name: str) -> Skill | None:
        """Get a skill by name.

        Args:
            name: Skill name.

        Returns:
            Skill or None.
        """
        if not self.skills:
            self.load_skills()
        return self.skills.get(name)

    def list_skills(self) -> list[str]:
        """List all available skill names.

        Returns:
            List of skill names.
        """
        if not self.skills:
            self.load_skills()
        return list(self.skills.keys())

    def generate_skill_prompt(self, skill: Skill, **kwargs: Any) -> str:
        """Generate a prompt for executing a skill.

        Args:
            skill: The skill to execute.
            **kwargs: Skill parameters.

        Returns:
            Prompt string for the agent.
        """
        prompt_parts = [
            f"Execute the '{skill.name}' skill.",
            f"Description: {skill.description}",
            "",
            "Steps to follow:",
        ]

        for i, step in enumerate(skill.steps, 1):
            step_text = f"{i}. {step.description}"
            if step.command:
                step_text += f"\n   Command: {step.command}"
            if step.condition:
                step_text += f"\n   Condition: {step.condition}"
            prompt_parts.append(step_text)

        if kwargs:
            prompt_parts.append("")
            prompt_parts.append("Parameters provided:")
            for key, value in kwargs.items():
                prompt_parts.append(f"  - {key}: {value}")

        return "\n".join(prompt_parts)


def create_skill_template(skill_name: str, skill_path: Path) -> None:
    """Create a skill template file.

    Args:
        skill_name: Name of the skill.
        skill_path: Path to save the skill file.
    """
    template = f"""name: {skill_name}
description: |
  Describe what this skill does.

parameters:
  example_param:
    type: string
    description: An example parameter
    required: false

steps:
  - description: First step description
    command: echo "Step 1"

  - description: Second step - run tests
    command: npm test

  - description: Third step - conditional
    prompt: "Check if everything is working"
    condition: "previous step succeeded"
"""

    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(template)
