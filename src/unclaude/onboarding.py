"""First-run onboarding for UnClaude.

Provides an interactive setup experience for new users to configure
their provider, API key, and model preferences.
"""

import os
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

console = Console()


# Provider configurations (models fetched dynamically)
PROVIDERS = {
    "gemini": {
        "name": "Google Gemini",
        "env_var": "GEMINI_API_KEY",
        "prefix": "gemini/",
        "default_model": "gemini-2.0-flash",
        "docs_url": "https://ai.google.dev/",
    },
    "openai": {
        "name": "OpenAI",
        "env_var": "OPENAI_API_KEY",
        "prefix": "",
        "default_model": "gpt-4o",
        "docs_url": "https://platform.openai.com/",
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "env_var": "ANTHROPIC_API_KEY",
        "prefix": "",
        "default_model": "claude-sonnet-4-20250514",
        "docs_url": "https://console.anthropic.com/",
    },
    "ollama": {
        "name": "Ollama (Local)",
        "env_var": None,
        "prefix": "ollama/",
        "default_model": "llama3.2",
        "docs_url": "https://ollama.ai/",
    },
}


def get_models_for_provider(provider: str, include_custom: bool = True) -> list[str]:
    """Fetch available models for a provider from LiteLLM.
    
    Args:
        provider: Provider name (gemini, openai, anthropic, ollama).
        include_custom: Whether to include custom models from config.
        
    Returns:
        List of model names.
    """
    models = []
    
    try:
        # Use model_cost dict which is more comprehensive and up-to-date
        from litellm import model_cost
        
        # Provider prefix mapping
        prefix_map = {
            "gemini": "gemini/",
            "openai": "",  # OpenAI models don't have prefix
            "anthropic": "",  # Anthropic models don't have prefix
            "ollama": "ollama/",
        }
        
        prefix = prefix_map.get(provider, f"{provider}/")
        
        # Filter models by provider
        for model_name in model_cost.keys():
            # Handle different provider patterns
            if provider == "openai":
                # OpenAI models: gpt-4, gpt-4o, gpt-3.5-turbo, etc.
                if model_name.startswith(("gpt-", "o1-", "o3-", "chatgpt-")):
                    if not any(x in model_name.lower() for x in ['embed', 'whisper', 'tts', 'image', 'dall', 'moderation']):
                        models.append(model_name)
            elif provider == "anthropic":
                # Anthropic models: claude-3, claude-2, etc.
                if model_name.startswith("claude"):
                    if not any(x in model_name.lower() for x in ['embed', 'image']):
                        models.append(model_name)
            elif prefix and model_name.startswith(prefix):
                # For prefixed providers (gemini/, ollama/)
                short_name = model_name[len(prefix):]
                if not any(x in short_name.lower() for x in ['embed', 'whisper', 'tts', 'image', 'vision', 'moderation']):
                    models.append(short_name)
        
        # Sort and limit
        models = sorted(set(models))[:15]
        
    except Exception:
        pass
    
    # Fallback to curated list if dynamic fetching fails
    if not models:
        fallback_models = {
            "gemini": ["gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-pro", "gemini-1.5-flash"],
            "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo", "o1", "o1-mini"],
            "anthropic": ["claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"],
            "ollama": ["llama3.2", "codellama", "mistral", "deepseek-coder", "qwen2.5"],
        }
        models = fallback_models.get(provider, [])
    
    # Include custom models from config
    if include_custom:
        config = load_config()
        custom_models = config.get("custom_models", {}).get(provider, [])
        if custom_models:
            # Add custom models at the beginning
            models = custom_models + [m for m in models if m not in custom_models]
    
    return models


def get_all_custom_models() -> dict[str, list[str]]:
    """Get all custom models from config."""
    config = load_config()
    return config.get("custom_models", {})


def add_custom_model(provider: str, model: str) -> bool:
    """Add a custom model for a provider."""
    config = load_config()
    if "custom_models" not in config:
        config["custom_models"] = {}
    if provider not in config["custom_models"]:
        config["custom_models"][provider] = []
    if model not in config["custom_models"][provider]:
        config["custom_models"][provider].append(model)
        save_config(config)
        return True
    return False


def remove_custom_model(provider: str, model: str) -> bool:
    """Remove a custom model for a provider."""
    config = load_config()
    if "custom_models" in config and provider in config["custom_models"]:
        if model in config["custom_models"][provider]:
            config["custom_models"][provider].remove(model)
            save_config(config)
            return True
    return False


def get_config_dir() -> Path:
    """Get the UnClaude config directory."""
    config_dir = Path.home() / ".unclaude"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_path() -> Path:
    """Get the config file path."""
    return get_config_dir() / "config.yaml"


def get_credentials_path() -> Path:
    """Get the credentials file path."""
    return get_config_dir() / ".credentials"


def load_config() -> dict[str, Any]:
    """Load existing configuration."""
    config_path = get_config_path()
    if config_path.exists():
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def save_config(config: dict[str, Any]) -> None:
    """Save configuration to file."""
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


def save_credential(provider: str, api_key: str) -> None:
    """Save API key to credentials file securely."""
    creds_path = get_credentials_path()
    
    # Load existing credentials
    creds = {}
    if creds_path.exists():
        with open(creds_path) as f:
            creds = yaml.safe_load(f) or {}
    
    # Save new credential
    creds[provider] = api_key
    
    with open(creds_path, "w") as f:
        yaml.dump(creds, f, default_flow_style=False)
    
    # Set restrictive permissions
    creds_path.chmod(0o600)


def load_credential(provider: str) -> str | None:
    """Load API key for a provider."""
    # First check environment variable
    provider_info = PROVIDERS.get(provider, {})
    env_var = provider_info.get("env_var")
    if env_var:
        env_value = os.environ.get(env_var)
        if env_value:
            return env_value
    
    # Then check credentials file
    creds_path = get_credentials_path()
    if creds_path.exists():
        with open(creds_path) as f:
            creds = yaml.safe_load(f) or {}
            return creds.get(provider)
    
    return None


def is_configured() -> bool:
    """Check if UnClaude has been configured."""
    config = load_config()
    return bool(config.get("default_provider"))


def print_welcome() -> None:
    """Print the welcome banner."""
    console.print()
    console.print(
        Panel(
            "[bold cyan]Welcome to UnClaude![/bold cyan]\n\n"
            "The open-source, model-independent AI coding assistant.\n"
            "Let's get you set up in just a few steps.",
            title="🚀 First-Time Setup",
            border_style="cyan",
        )
    )
    console.print()


def select_provider() -> str:
    """Prompt user to select a provider."""
    console.print("[bold]Step 1:[/bold] Choose your AI provider\n")
    
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", style="dim")
    table.add_column("Provider")
    table.add_column("Description")
    
    provider_list = list(PROVIDERS.keys())
    for i, key in enumerate(provider_list, 1):
        info = PROVIDERS[key]
        table.add_row(str(i), info["name"], info.get("docs_url", ""))
    
    console.print(table)
    console.print()
    
    while True:
        choice = Prompt.ask(
            "Select provider",
            choices=[str(i) for i in range(1, len(provider_list) + 1)],
            default="1",
        )
        return provider_list[int(choice) - 1]


def get_api_key(provider: str) -> str | None:
    """Prompt user for API key."""
    info = PROVIDERS[provider]
    
    console.print(f"\n[bold]Step 2:[/bold] Enter your {info['name']} API key\n")
    
    if info.get("env_var") is None:
        console.print("[dim]Ollama runs locally, no API key needed.[/dim]")
        return None
    
    console.print(f"[dim]Get your API key at: {info['docs_url']}[/dim]")
    console.print(f"[dim]Your key will be stored securely in ~/.unclaude/.credentials[/dim]\n")
    
    # Check if key exists
    existing_key = load_credential(provider)
    if existing_key:
        masked = existing_key[:8] + "..." + existing_key[-4:] if len(existing_key) > 12 else "****"
        console.print(f"[green]Found existing key: {masked}[/green]")
        if Confirm.ask("Use existing key?", default=True):
            return existing_key
    
    api_key = Prompt.ask("API Key", password=True)
    
    if not api_key:
        console.print("[red]API key is required.[/red]")
        return get_api_key(provider)
    
    return api_key


def select_model(provider: str) -> str:
    """Prompt user to select a model."""
    info = PROVIDERS[provider]
    
    console.print(f"\n[bold]Step 3:[/bold] Choose your default model\n")
    console.print("[dim]Fetching available models...[/dim]\n")
    
    # Dynamically fetch models from LiteLLM
    models = get_models_for_provider(provider)
    default_model = info["default_model"]
    
    if not models:
        console.print("[yellow]Could not fetch models. Using default.[/yellow]")
        return default_model
    
    for i, model in enumerate(models, 1):
        default_marker = " [green](recommended)[/green]" if model == default_model else ""
        console.print(f"  {i}. {model}{default_marker}")
    
    # Option to enter custom model
    console.print(f"  {len(models) + 1}. [dim]Enter custom model name[/dim]")
    
    console.print()
    
    default_idx = models.index(default_model) + 1 if default_model in models else 1
    
    choice = Prompt.ask(
        "Select model",
        choices=[str(i) for i in range(1, len(models) + 2)],
        default=str(default_idx),
    )
    
    choice_idx = int(choice)
    if choice_idx == len(models) + 1:
        # Custom model
        custom = Prompt.ask("Enter model name")
        return custom if custom else default_model
    
    return models[choice_idx - 1]


def run_onboarding() -> dict[str, Any]:
    """Run the full onboarding flow.
    
    Returns:
        Configuration dictionary.
    """
    print_welcome()
    
    # Step 1: Select provider
    provider = select_provider()
    
    # Step 2: Get API key
    api_key = get_api_key(provider)
    if api_key:
        save_credential(provider, api_key)
    
    # Step 3: Select model
    model = select_model(provider)
    
    # Save configuration
    config = {
        "default_provider": provider,
        "providers": {
            provider: {
                "model": model,
            }
        }
    }
    save_config(config)
    
    # Success message
    console.print()
    console.print(
        Panel(
            f"[bold green]Setup complete![/bold green]\n\n"
            f"Provider: [cyan]{PROVIDERS[provider]['name']}[/cyan]\n"
            f"Model: [cyan]{model}[/cyan]\n\n"
            f"You're ready to use UnClaude!\n"
            f"Run [bold]unclaude chat[/bold] to start.",
            title="✅ Configuration Saved",
            border_style="green",
        )
    )
    console.print()
    
    return config


def ensure_configured() -> dict[str, Any]:
    """Ensure UnClaude is configured, running onboarding if needed.
    
    Returns:
        Configuration dictionary.
    """
    if is_configured():
        return load_config()
    
    return run_onboarding()


def get_provider_api_key(provider: str) -> str | None:
    """Get the API key for a provider, loading from credentials."""
    return load_credential(provider)
