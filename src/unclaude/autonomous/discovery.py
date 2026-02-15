"""Self-skill discovery engine.

Scans a project to understand what tools, languages, frameworks,
and capabilities are available. This allows the agent to autonomously
discover what it can do without being told.

Discovery sources:
    - package.json          → npm scripts, dependencies
    - pyproject.toml        → Python tools, dependencies
    - Makefile / Justfile   → build/test/lint targets
    - Dockerfile            → container capabilities
    - docker-compose.yml    → service topology
    - .github/workflows/    → CI/CD capabilities
    - tsconfig.json         → TypeScript config
    - README.md             → project description
    - Directory structure   → conventional patterns

Usage:
    discovery = SkillDiscovery(Path("."))
    profile = await discovery.scan()
    print(profile.summary())
    # "Python 3.13 project with pytest, FastAPI, Docker.
    #  Available: test, lint, build, deploy, format"
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProjectSkill:
    """A discovered capability of the project."""
    name: str                    # e.g. "test", "lint", "build"
    command: str                 # e.g. "pytest", "npm run test"
    source: str                  # Where we found it
    confidence: float = 1.0     # How sure we are (0-1)
    description: str = ""       # What it does
    category: str = "general"   # test, build, lint, deploy, format, etc.


@dataclass
class DetectedFramework:
    """A detected framework or library."""
    name: str
    version: str = ""
    category: str = ""    # web, test, orm, cli, etc.


@dataclass
class ProjectProfile:
    """Complete profile of a project's capabilities."""
    path: Path = field(default_factory=Path)

    # Languages
    languages: list[str] = field(default_factory=list)
    primary_language: str = ""

    # Frameworks and libraries
    frameworks: list[DetectedFramework] = field(default_factory=list)

    # Available skills/commands
    skills: list[ProjectSkill] = field(default_factory=list)

    # Project structure
    has_docker: bool = False
    has_ci: bool = False
    has_tests: bool = False
    has_docs: bool = False
    has_monorepo: bool = False

    # File counts
    file_counts: dict[str, int] = field(default_factory=dict)

    # Raw metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> str:
        """Human-readable project summary."""
        parts = []

        if self.primary_language:
            parts.append(f"{self.primary_language} project")

        if self.frameworks:
            fw_names = [f.name for f in self.frameworks[:5]]
            parts.append(f"using {', '.join(fw_names)}")

        features = []
        if self.has_docker:
            features.append("Docker")
        if self.has_ci:
            features.append("CI/CD")
        if self.has_tests:
            features.append("tests")
        if self.has_docs:
            features.append("docs")
        if features:
            parts.append(f"with {', '.join(features)}")

        summary = " ".join(parts) + "."

        if self.skills:
            skill_names = [s.name for s in self.skills]
            summary += f"\nAvailable commands: {', '.join(skill_names)}"

        return summary

    def skills_by_category(self) -> dict[str, list[ProjectSkill]]:
        """Group skills by category."""
        groups: dict[str, list[ProjectSkill]] = {}
        for skill in self.skills:
            groups.setdefault(skill.category, []).append(skill)
        return groups

    def to_context_prompt(self) -> str:
        """Generate context for the agent system prompt."""
        lines = [
            "# Project Capabilities (auto-discovered)",
            f"Project: {self.path.name}",
            f"Language: {self.primary_language or 'Unknown'}",
        ]

        if self.frameworks:
            lines.append(
                f"Frameworks: {', '.join(f.name for f in self.frameworks)}")

        if self.skills:
            lines.append("\n## Available Commands:")
            for skill in self.skills:
                desc = f" — {skill.description}" if skill.description else ""
                lines.append(f"  - `{skill.command}`{desc}")

        features = []
        if self.has_docker:
            features.append("Docker containerization available")
        if self.has_ci:
            features.append("CI/CD pipeline configured")
        if self.has_tests:
            features.append("Test suite available")
        if features:
            lines.append("\n## Features:")
            for f in features:
                lines.append(f"  - {f}")

        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "primary_language": self.primary_language,
            "languages": self.languages,
            "frameworks": [
                {"name": f.name, "version": f.version, "category": f.category}
                for f in self.frameworks
            ],
            "skills": [
                {"name": s.name, "command": s.command, "category": s.category,
                 "source": s.source, "description": s.description}
                for s in self.skills
            ],
            "has_docker": self.has_docker,
            "has_ci": self.has_ci,
            "has_tests": self.has_tests,
            "has_docs": self.has_docs,
            "has_monorepo": self.has_monorepo,
            "file_counts": self.file_counts,
        }


class SkillDiscovery:
    """Scans a project directory and discovers capabilities."""

    def __init__(self, project_path: Path | None = None):
        self.project_path = (project_path or Path.cwd()).resolve()

    async def scan(self) -> ProjectProfile:
        """Full project scan. Returns a ProjectProfile."""
        profile = ProjectProfile(path=self.project_path)

        # Run all scanners
        self._scan_file_structure(profile)
        self._scan_pyproject(profile)
        self._scan_package_json(profile)
        self._scan_makefile(profile)
        self._scan_dockerfile(profile)
        self._scan_ci(profile)
        self._scan_cargo(profile)
        self._scan_go(profile)
        self._scan_conventions(profile)

        # Determine primary language
        if profile.languages:
            profile.primary_language = profile.languages[0]

        # Deduplicate skills
        seen = set()
        unique_skills = []
        for skill in profile.skills:
            key = (skill.name, skill.command)
            if key not in seen:
                seen.add(key)
                unique_skills.append(skill)
        profile.skills = unique_skills

        return profile

    def _scan_file_structure(self, profile: ProjectProfile):
        """Scan directory structure for patterns."""
        counts: dict[str, int] = {}
        try:
            for f in self.project_path.rglob("*"):
                if f.is_file() and not any(
                    skip in f.parts for skip in (
                        ".git", "node_modules", "__pycache__", ".venv",
                        "dist", "build", "_next", "static", ".next",
                    )
                ):
                    ext = f.suffix.lower()
                    if ext:
                        counts[ext] = counts.get(ext, 0) + 1
        except PermissionError:
            pass

        profile.file_counts = counts

        # Determine languages from extensions
        lang_map = {
            ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
            ".jsx": "JavaScript", ".tsx": "TypeScript", ".rs": "Rust",
            ".go": "Go", ".java": "Java", ".rb": "Ruby", ".php": "PHP",
            ".c": "C", ".cpp": "C++", ".cs": "C#", ".swift": "Swift",
            ".kt": "Kotlin", ".scala": "Scala", ".zig": "Zig",
        }

        lang_counts: dict[str, int] = {}
        for ext, count in counts.items():
            if ext in lang_map:
                lang = lang_map[ext]
                lang_counts[lang] = lang_counts.get(lang, 0) + count

        profile.languages = sorted(
            lang_counts, key=lang_counts.get, reverse=True)

        # Check for common directories
        dirs = {d.name for d in self.project_path.iterdir() if d.is_dir()}
        if "tests" in dirs or "test" in dirs or "__tests__" in dirs:
            profile.has_tests = True
        if "docs" in dirs or "doc" in dirs or "documentation" in dirs:
            profile.has_docs = True
        if any(d in dirs for d in ["packages", "apps", "libs", "modules"]):
            profile.has_monorepo = True

    def _scan_pyproject(self, profile: ProjectProfile):
        """Scan pyproject.toml for Python project info."""
        pyproject = self.project_path / "pyproject.toml"
        if not pyproject.exists():
            # Also check setup.py / setup.cfg
            if (self.project_path / "setup.py").exists():
                profile.skills.append(ProjectSkill(
                    name="install", command="pip install -e .", source="setup.py",
                    category="build", description="Install in dev mode",
                ))
            return

        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                return

        try:
            content = pyproject.read_text()
            data = tomllib.loads(content)
        except Exception:
            return

        # Project metadata
        project = data.get("project", {})
        profile.metadata["project_name"] = project.get("name", "")
        profile.metadata["python_requires"] = project.get(
            "requires-python", "")

        # Dependencies → framework detection
        deps = project.get("dependencies", [])
        optional = project.get("optional-dependencies", {})
        all_deps = list(deps)
        for group_deps in optional.values():
            all_deps.extend(group_deps)

        framework_patterns = {
            "fastapi": ("FastAPI", "web"),
            "flask": ("Flask", "web"),
            "django": ("Django", "web"),
            "starlette": ("Starlette", "web"),
            "aiohttp": ("aiohttp", "web"),
            "sqlalchemy": ("SQLAlchemy", "orm"),
            "pydantic": ("Pydantic", "validation"),
            "typer": ("Typer", "cli"),
            "click": ("Click", "cli"),
            "pytest": ("Pytest", "test"),
            "rich": ("Rich", "cli"),
            "httpx": ("httpx", "http"),
            "celery": ("Celery", "task-queue"),
            "redis": ("Redis", "cache"),
            "litellm": ("LiteLLM", "llm"),
        }

        for dep in all_deps:
            dep_name = re.split(r"[>=<\[!~]", dep.strip())[0].lower()
            if dep_name in framework_patterns:
                name, cat = framework_patterns[dep_name]
                # Try to extract version
                version_match = re.search(r"[>=<~!]+(.+?)(?:,|$|\])", dep)
                version = version_match.group(
                    1).strip() if version_match else ""
                profile.frameworks.append(DetectedFramework(
                    name=name, version=version, category=cat
                ))

        # Build system
        build_sys = data.get("build-system", {})
        if build_sys:
            profile.skills.append(ProjectSkill(
                name="install", command="pip install -e .", source="pyproject.toml",
                category="build", description="Install in dev mode",
            ))

        # Scripts
        scripts = data.get("project", {}).get("scripts", {})
        for name, entry in scripts.items():
            profile.skills.append(ProjectSkill(
                name=name, command=name, source="pyproject.toml",
                category="run", description=f"Entry point: {entry}",
            ))

        # Tool configs (pytest, ruff, mypy, black, etc.)
        tools = data.get("tool", {})
        if "pytest" in tools:
            profile.has_tests = True
            profile.skills.append(ProjectSkill(
                name="test", command="pytest", source="pyproject.toml",
                category="test", description="Run tests with pytest",
            ))
        if "ruff" in tools:
            profile.skills.append(ProjectSkill(
                name="lint", command="ruff check .", source="pyproject.toml",
                category="lint", description="Lint with ruff",
            ))
            profile.skills.append(ProjectSkill(
                name="format", command="ruff format .", source="pyproject.toml",
                category="format", description="Format with ruff",
            ))
        if "mypy" in tools:
            profile.skills.append(ProjectSkill(
                name="typecheck", command="mypy .", source="pyproject.toml",
                category="lint", description="Type check with mypy",
            ))
        if "black" in tools:
            profile.skills.append(ProjectSkill(
                name="format", command="black .", source="pyproject.toml",
                category="format", description="Format with black",
            ))

    def _scan_package_json(self, profile: ProjectProfile):
        """Scan package.json for Node.js project info."""
        pkg_json = self.project_path / "package.json"
        if not pkg_json.exists():
            return

        try:
            data = json.loads(pkg_json.read_text())
        except Exception:
            return

        profile.metadata["package_name"] = data.get("name", "")

        # Scripts
        scripts = data.get("scripts", {})
        category_map = {
            "test": "test", "build": "build", "dev": "run",
            "start": "run", "lint": "lint", "format": "format",
            "deploy": "deploy", "check": "lint", "preview": "run",
            "typecheck": "lint", "e2e": "test", "storybook": "run",
        }

        for name, cmd in scripts.items():
            cat = "general"
            for key, c in category_map.items():
                if key in name.lower():
                    cat = c
                    break

            profile.skills.append(ProjectSkill(
                name=name, command=f"npm run {name}", source="package.json",
                category=cat, description=cmd[:80],
            ))

        # Dependencies → frameworks
        all_deps = {**data.get("dependencies", {}), **
                    data.get("devDependencies", {})}
        node_frameworks = {
            "react": ("React", "web"),
            "next": ("Next.js", "web"),
            "vue": ("Vue.js", "web"),
            "svelte": ("Svelte", "web"),
            "express": ("Express", "web"),
            "fastify": ("Fastify", "web"),
            "nest": ("NestJS", "web"),
            "@nestjs/core": ("NestJS", "web"),
            "tailwindcss": ("Tailwind CSS", "css"),
            "typescript": ("TypeScript", "language"),
            "prisma": ("Prisma", "orm"),
            "jest": ("Jest", "test"),
            "vitest": ("Vitest", "test"),
            "playwright": ("Playwright", "test"),
            "cypress": ("Cypress", "test"),
            "eslint": ("ESLint", "lint"),
            "prettier": ("Prettier", "format"),
            "vite": ("Vite", "build"),
            "webpack": ("Webpack", "build"),
            "esbuild": ("esbuild", "build"),
        }

        for pkg, (name, cat) in node_frameworks.items():
            if pkg in all_deps:
                version = all_deps[pkg]
                profile.frameworks.append(DetectedFramework(
                    name=name, version=str(version).lstrip("^~"), category=cat
                ))

        if "test" in scripts:
            profile.has_tests = True

    def _scan_makefile(self, profile: ProjectProfile):
        """Scan Makefile for targets."""
        for makefile_name in ["Makefile", "makefile", "GNUmakefile", "Justfile"]:
            makefile = self.project_path / makefile_name
            if not makefile.exists():
                continue

            is_just = makefile_name == "Justfile"
            cmd_prefix = "just" if is_just else "make"

            try:
                content = makefile.read_text()
            except Exception:
                continue

            # Find targets
            if is_just:
                # Justfile syntax: target_name:
                targets = re.findall(r"^(\w[\w-]*)\s*:", content, re.MULTILINE)
            else:
                # Makefile syntax: target:
                targets = re.findall(
                    r"^([a-zA-Z][\w-]*)\s*:", content, re.MULTILINE)

            category_map = {
                "test": "test", "build": "build", "run": "run",
                "lint": "lint", "format": "format", "deploy": "deploy",
                "clean": "build", "install": "build", "dev": "run",
                "check": "lint", "docker": "deploy",
            }

            for target in targets:
                if target.startswith(".") or target in ("all", "default"):
                    continue

                cat = "general"
                for key, c in category_map.items():
                    if key in target.lower():
                        cat = c
                        break

                profile.skills.append(ProjectSkill(
                    name=target,
                    command=f"{cmd_prefix} {target}",
                    source=makefile_name,
                    category=cat,
                ))

    def _scan_dockerfile(self, profile: ProjectProfile):
        """Check for Docker support."""
        has_dockerfile = (self.project_path / "Dockerfile").exists()
        has_compose = any(
            (self.project_path / name).exists()
            for name in ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]
        )

        if has_dockerfile or has_compose:
            profile.has_docker = True

        if has_dockerfile:
            profile.skills.append(ProjectSkill(
                name="docker-build",
                command="docker build -t app .",
                source="Dockerfile",
                category="deploy",
                description="Build Docker image",
            ))

        if has_compose:
            profile.skills.append(ProjectSkill(
                name="docker-up",
                command="docker compose up -d",
                source="docker-compose.yml",
                category="deploy",
                description="Start services with Docker Compose",
            ))

    def _scan_ci(self, profile: ProjectProfile):
        """Check for CI/CD configuration."""
        ci_paths = [
            ".github/workflows",
            ".gitlab-ci.yml",
            ".circleci",
            "Jenkinsfile",
            ".travis.yml",
            "bitbucket-pipelines.yml",
        ]

        for ci_path in ci_paths:
            full_path = self.project_path / ci_path
            if full_path.exists():
                profile.has_ci = True
                break

    def _scan_cargo(self, profile: ProjectProfile):
        """Scan Cargo.toml for Rust project info."""
        cargo = self.project_path / "Cargo.toml"
        if not cargo.exists():
            return

        profile.skills.append(ProjectSkill(
            name="build", command="cargo build", source="Cargo.toml",
            category="build", description="Build Rust project",
        ))
        profile.skills.append(ProjectSkill(
            name="test", command="cargo test", source="Cargo.toml",
            category="test", description="Run Rust tests",
        ))
        profile.skills.append(ProjectSkill(
            name="check", command="cargo clippy", source="Cargo.toml",
            category="lint", description="Lint with clippy",
        ))
        profile.has_tests = True

    def _scan_go(self, profile: ProjectProfile):
        """Scan go.mod for Go project info."""
        gomod = self.project_path / "go.mod"
        if not gomod.exists():
            return

        profile.skills.append(ProjectSkill(
            name="build", command="go build ./...", source="go.mod",
            category="build", description="Build Go project",
        ))
        profile.skills.append(ProjectSkill(
            name="test", command="go test ./...", source="go.mod",
            category="test", description="Run Go tests",
        ))
        profile.skills.append(ProjectSkill(
            name="lint", command="golangci-lint run", source="go.mod",
            category="lint", description="Lint with golangci-lint",
            confidence=0.7,
        ))
        profile.has_tests = True

    def _scan_conventions(self, profile: ProjectProfile):
        """Detect common conventions from file presence."""
        # EditorConfig
        if (self.project_path / ".editorconfig").exists():
            profile.metadata["has_editorconfig"] = True

        # Pre-commit hooks
        if (self.project_path / ".pre-commit-config.yaml").exists():
            profile.skills.append(ProjectSkill(
                name="pre-commit",
                command="pre-commit run --all-files",
                source=".pre-commit-config.yaml",
                category="lint",
                description="Run pre-commit hooks",
            ))

        # README
        for readme_name in ["README.md", "README.rst", "README.txt", "README"]:
            if (self.project_path / readme_name).exists():
                profile.has_docs = True
                break

        # License
        for license_name in ["LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"]:
            if (self.project_path / license_name).exists():
                profile.metadata["has_license"] = True
                break
