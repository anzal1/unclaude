"""Configuration management for UnClaude."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""

    model: str
    api_key: str | None = None
    base_url: str | None = None
    provider: str | None = None  # For custom providers like ollama


class RalphWiggumConfig(BaseModel):
    """Configuration for Ralph Wiggum autonomous mode."""

    enabled: bool = False
    max_iterations: int = 50
    max_cost: float = 10.0  # USD
    feedback_commands: list[str] = Field(default_factory=lambda: ["npm test"])
    stop_on_success: bool = True


class PermissionsConfig(BaseModel):
    """Permission settings for dangerous operations."""

    file_read: str = "auto"  # auto, ask, deny
    file_write: str = "ask"
    file_delete: str = "deny"
    bash_execute: str = "ask"
    web_fetch: str = "auto"
    mcp_tools: str = "ask"


class WhitelistConfig(BaseModel):
    """Whitelisted operations that don't require permission."""

    bash: list[str] = Field(default_factory=list)
    paths: list[str] = Field(default_factory=list)


class Settings(BaseSettings):
    """Main settings for UnClaude."""

    model_config = SettingsConfigDict(
        env_prefix="UNCLAUDE_",
        env_nested_delimiter="__",
    )

    # Provider settings
    default_provider: str = "gemini"
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    custom_models: dict[str, list[str]] = Field(default_factory=dict)  # {provider: [models]}

    # Feature flags
    ralph_wiggum: RalphWiggumConfig = Field(default_factory=RalphWiggumConfig)
    permissions: PermissionsConfig = Field(default_factory=PermissionsConfig)
    whitelist: WhitelistConfig = Field(default_factory=WhitelistConfig)

    # Paths
    config_dir: Path = Field(default_factory=lambda: Path.home() / ".unclaude")
    memory_dir: Path = Field(default_factory=lambda: Path.home() / ".unclaude" / "memory")


def get_config_path() -> Path:
    """Get the path to the config file."""
    return Path.home() / ".unclaude" / "config.yaml"


def load_config() -> Settings:
    """Load configuration from file and environment."""
    config_path = get_config_path()

    if config_path.exists():
        with open(config_path) as f:
            config_data = yaml.safe_load(f) or {}
        return Settings(**config_data)

    return Settings()


def save_config(settings: Settings) -> None:
    """Save configuration to file."""
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict, excluding defaults
    config_data = settings.model_dump(exclude_defaults=True)

    with open(config_path, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False)


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = load_config()
    return _settings
