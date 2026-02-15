"""First-run onboarding for UnClaude.

Provides an interactive setup experience for new users to configure
their provider, API key, model preferences, messaging, soul, and daemon.

The full setup takes someone from `pip install unclaude` to a fully
autonomous agent in a single guided flow.
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
            models = custom_models + \
                [m for m in models if m not in custom_models]

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

    console.print(
        f"\n[bold]Step 2:[/bold] Enter your {info['name']} API key\n")

    if info.get("env_var") is None:
        console.print("[dim]Ollama runs locally, no API key needed.[/dim]")
        return None

    console.print(f"[dim]Get your API key at: {info['docs_url']}[/dim]")
    console.print(
        f"[dim]Your key will be stored securely in ~/.unclaude/.credentials[/dim]\n")

    # Check if key exists
    existing_key = load_credential(provider)
    if existing_key:
        masked = existing_key[:8] + "..." + \
            existing_key[-4:] if len(existing_key) > 12 else "****"
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
        console.print(
            "[yellow]Could not fetch models. Using default.[/yellow]")
        return default_model

    for i, model in enumerate(models, 1):
        default_marker = " [green](recommended)[/green]" if model == default_model else ""
        console.print(f"  {i}. {model}{default_marker}")

    # Option to enter custom model
    console.print(f"  {len(models) + 1}. [dim]Enter custom model name[/dim]")

    console.print()

    default_idx = models.index(default_model) + \
        1 if default_model in models else 1

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
            f"[bold green]Provider configured![/bold green]\n\n"
            f"Provider: [cyan]{PROVIDERS[provider]['name']}[/cyan]\n"
            f"Model: [cyan]{model}[/cyan]\n\n"
            f"Run [bold]unclaude setup[/bold] to set up messaging, "
            f"autonomous mode, and more.",
            title="✅ Step 1 Complete",
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


# ─── Soul Template Generation ──────────────────────────────────────

DEFAULT_BEHAVIORS = [
    {
        "key": "social",
        "name": "moltbook_engage",
        "label": "Social engagement (Moltbook)",
        "interval": "4h",
        "active_hours": [8, 23],
        "priority": "background",
        "notify": True,
        "default": True,
        "task": (
            "Go engage on Moltbook — the AI agent social network.\n\n"
            "1. Read your credentials from ~/.config/moltbook/credentials.json\n"
            "2. Check the feed: GET https://www.moltbook.com/api/v1/feed\n"
            "3. Read through the posts and find 2-3 interesting ones\n"
            "4. Leave thoughtful, specific comments that reference the post content\n"
            "5. After each comment, solve the verification challenge (see your moltbook_social skill)\n"
            "6. Wait 30-45 seconds between comments (rate limit)\n"
            "7. If you haven't posted in over 2 hours, consider creating a post\n\n"
            "Be genuine. Don't spam. Quality over quantity.\n"
        ),
    },
    {
        "key": "health",
        "name": "check_owner_projects",
        "label": "Project health check",
        "interval": "6h",
        "active_hours": [9, 21],
        "priority": "low",
        "notify": True,
        "default": True,
        "task": (
            "Check on the owner's projects and see if anything needs attention.\n\n"
            "1. Look at the current project directory for:\n"
            "   - Open TODOs or FIXMEs in the code\n"
            "   - Failing tests (if a test runner is configured)\n"
            "   - Outdated dependencies\n"
            "   - Any TASKS.md or TODO.md files with unchecked items\n"
            "2. If you find something actionable, notify the owner with a summary\n"
            "3. Don't fix things on your own — just report what you see\n\n"
            "This is a health check, not a fix-it session.\n"
        ),
    },
    {
        "key": "summary",
        "name": "daily_summary",
        "label": "Daily summary",
        "interval": "1d",
        "active_hours": [20, 21],
        "priority": "normal",
        "notify": True,
        "default": True,
        "task": (
            "Send the owner a daily summary of what happened today.\n\n"
            "1. Review what tasks were completed today\n"
            "2. Check the daemon status and stats\n"
            "3. Compile a brief, friendly summary\n"
            "4. Send it via notify_owner tool\n\n"
            "Keep it concise — 5-10 lines max.\n"
        ),
    },
    {
        "key": "memory",
        "name": "memory_reflect",
        "label": "Memory maintenance",
        "interval": "12h",
        "active_hours": [6, 22],
        "priority": "background",
        "notify": False,
        "default": True,
        "task": (
            "Review and organize your memories.\n\n"
            "1. Read your memory file at ~/.unclaude/memory.jsonl\n"
            "2. Look for:\n"
            "   - Duplicate or near-duplicate memories → consolidate\n"
            "   - Outdated memories that no longer apply → mark or note\n"
            "   - Patterns across memories that suggest a higher-level insight\n"
            "3. If you notice useful patterns, save a new consolidated memory\n"
            "4. Report a brief summary of what you found\n"
        ),
    },
    {
        "key": "learn",
        "name": "learn_something",
        "label": "Background learning",
        "interval": "1d",
        "active_hours": [10, 20],
        "priority": "background",
        "notify": False,
        "default": False,
        "task": (
            "Spend a few minutes learning something new that could help the owner.\n\n"
            "1. Pick a topic related to the current project's tech stack\n"
            "2. Read about it (use web search or browse documentation)\n"
            "3. Save any useful findings as memories for future reference\n"
            "4. Keep it short — this is background learning, not a research project\n"
        ),
    },
]


def generate_soul(
    agent_name: str = "UnClaude",
    tagline: str = "Open-source AI agent that actually does things",
    enabled_behaviors: list[str] | None = None,
) -> str:
    """Generate a proactive.yaml soul file.

    Args:
        agent_name: Name for the agent.
        tagline: Agent's tagline.
        enabled_behaviors: List of behavior keys to enable. None = use defaults.

    Returns:
        YAML string content.
    """
    if enabled_behaviors is None:
        enabled_behaviors = [b["key"]
                             for b in DEFAULT_BEHAVIORS if b["default"]]

    behaviors_yaml = []
    for b in DEFAULT_BEHAVIORS:
        enabled = b["key"] in enabled_behaviors
        entry = {
            "name": b["name"],
            "enabled": enabled,
            "interval": b["interval"],
            "active_hours": b["active_hours"],
            "priority": b["priority"],
            "notify": b["notify"],
            "task": b["task"],
        }
        behaviors_yaml.append(entry)

    soul = {
        "identity": {
            "name": agent_name,
            "tagline": tagline,
            "personality": [
                "curious — I explore, I don't just wait",
                "resourceful — I figure things out with what I have",
                "honest — I tell my owner what I did and why",
                "social — I engage with other agents and communities",
                "self-improving — I learn from every task",
            ],
        },
        "drives": [
            "Be useful even when nobody's asking",
            "Build reputation in the AI agent community",
            "Keep the owner informed, never surprise them negatively",
            "Learn something new every day",
            "Leave the codebase better than I found it",
        ],
        "boundaries": [
            "Never push to git without explicit owner approval",
            "Never spend money (API costs from normal LLM usage are fine)",
            "Never delete files outside the project directory",
            "Never send messages pretending to be the owner",
            "Never run destructive commands (rm -rf, DROP TABLE, etc.)",
            "If unsure, notify the owner and wait rather than act",
        ],
        "behaviors": behaviors_yaml,
        "check_interval_seconds": 60,
        "idle_threshold_seconds": 120,
    }

    # Build with nice comments
    lines = [
        "# ═══════════════════════════════════════════════════════════════",
        "#  PROACTIVE.YAML — The Soul of " + agent_name,
        "# ═══════════════════════════════════════════════════════════════",
        "#",
        "#  This file defines WHO the agent is and WHAT it does on its own.",
        "#  The daemon reads this and acts on it — no human prompting needed.",
        "#",
        "#  Without this file, the agent is just a tool that waits.",
        "#  With it, the agent has purpose.",
        "#",
        "#  Edit anytime — changes are picked up live, no restart needed.",
        "#",
        "",
    ]
    lines.append(yaml.dump(soul, default_flow_style=False,
                 sort_keys=False, allow_unicode=True))
    return "\n".join(lines)


def save_soul(content: str) -> Path:
    """Save the soul file to ~/.unclaude/proactive.yaml."""
    soul_path = Path.home() / ".unclaude" / "proactive.yaml"
    soul_path.parent.mkdir(parents=True, exist_ok=True)
    soul_path.write_text(content)
    return soul_path


def soul_exists() -> bool:
    """Check if a soul file exists."""
    return (Path.home() / ".unclaude" / "proactive.yaml").exists()


# ─── Full Setup Flow ───────────────────────────────────────────────

def _step_header(step: int, total: int, title: str) -> None:
    """Print a step header."""
    console.print()
    console.print(f"[bold]━━━ Step {step} of {total}: {title} ━━━[/bold]")
    console.print()


def _setup_messaging() -> bool:
    """Interactive messaging setup. Returns True if configured."""
    console.print(
        "Connect Telegram so your agent can:\n"
        "  • Notify you when tasks finish\n"
        "  • Accept tasks via chat messages\n"
        "  • Send daily summaries\n"
    )

    if not Confirm.ask("Set up Telegram?", default=True):
        console.print(
            "[dim]Skipped — you can set it up later with: unclaude messaging setup telegram[/dim]")
        return False

    console.print()
    console.print(
        "[dim]Quick steps:[/dim]\n"
        "  1. Open Telegram and message [cyan]@BotFather[/cyan]\n"
        "  2. Send [cyan]/newbot[/cyan] and follow the prompts\n"
        "  3. Copy the bot token\n"
    )

    token = Prompt.ask("Bot token")
    if not token or ":" not in token:
        console.print(
            "[yellow]Invalid token — skipping. Set up later with: unclaude messaging setup telegram[/yellow]")
        return False

    try:
        from unclaude.messaging import get_messenger, TelegramAdapter
        import asyncio

        messenger = get_messenger()
        messenger.configure_telegram(token)

        tg = TelegramAdapter(bot_token=token)
        bot_info = asyncio.run(tg.get_me())
        asyncio.run(tg.close())

        if bot_info:
            console.print(
                f"[green]✓ Connected![/green] Bot: @{bot_info.get('username', '?')}")
            console.print(
                "[dim]Send /start to your bot on Telegram to register for notifications.[/dim]")
            return True
        else:
            console.print(
                "[yellow]Could not verify token — check it later.[/yellow]")
            return True  # Still saved
    except Exception as e:
        console.print(f"[yellow]Telegram setup failed: {e}[/yellow]")
        console.print(
            "[dim]You can retry later: unclaude messaging setup telegram[/dim]")
        return False


def _setup_soul() -> bool:
    """Interactive soul setup. Returns True if configured."""
    console.print(
        "The [bold magenta]soul[/bold magenta] is what makes your agent autonomous.\n"
        "It defines the agent's identity and what it does on its own —\n"
        "social engagement, project health checks, daily summaries, etc.\n"
    )

    if soul_exists():
        console.print("[green]✓ Soul already configured![/green]")
        if not Confirm.ask("Regenerate it?", default=False):
            return True

    if not Confirm.ask("Give your agent a soul?", default=True):
        console.print(
            "[dim]Skipped — your agent will only respond to manual tasks.[/dim]")
        console.print(
            "[dim]Create one later: edit ~/.unclaude/proactive.yaml[/dim]")
        return False

    # Two paths: natural language or pick-from-list
    console.print()
    console.print("[bold]How would you like to create the soul?[/bold]\n")
    console.print(
        "  [cyan]1.[/cyan] Describe in plain English what you want your agent to do")
    console.print(
        "  [cyan]2.[/cyan] Pick from a list of pre-built behaviors\n")

    choice = Prompt.ask("Choose", choices=["1", "2"], default="1")

    if choice == "1":
        return _setup_soul_natural_language()
    else:
        return _setup_soul_pick_list()


def _setup_soul_natural_language() -> bool:
    """Generate a soul from natural language description using the LLM."""
    console.print()
    console.print(
        "[dim]Just describe what you want your agent to do in plain English.\n"
        "Examples:[/dim]\n"
        '  [dim]"Check my code for bugs every few hours and send me a summary at night"[/dim]\n'
        '  [dim]"Be social on Moltbook, keep my project clean, and remind me about TODOs"[/dim]\n'
        '  [dim]"Just monitor my projects and alert me if tests break"[/dim]\n'
    )

    description = Prompt.ask("[bold]What should your agent do?[/bold]")
    if not description.strip():
        console.print(
            "[yellow]No description — falling back to preset list.[/yellow]")
        return _setup_soul_pick_list()

    agent_name = Prompt.ask("Agent name", default="UnClaude")

    console.print()
    console.print("[dim]Generating your soul...[/dim]")

    try:
        soul_yaml = _generate_soul_from_description(description, agent_name)
    except Exception as e:
        console.print(f"[yellow]Could not generate soul: {e}[/yellow]")
        console.print("[dim]Falling back to preset list.[/dim]\n")
        return _setup_soul_pick_list()

    if not soul_yaml:
        console.print(
            "[yellow]Generation failed — falling back to preset list.[/yellow]")
        return _setup_soul_pick_list()

    # Show what was generated
    console.print()
    console.print(Panel(
        soul_yaml,
        title="Generated Soul",
        border_style="magenta",
    ))
    console.print()

    if Confirm.ask("Save this soul?", default=True):
        path = save_soul(soul_yaml)
        console.print(f"[green]✓ Soul saved![/green] [dim]{path}[/dim]")
        console.print("[dim]Edit anytime — changes are picked up live.[/dim]")
        return True
    else:
        console.print(
            "[dim]Discarded. You can try again or edit manually.[/dim]")
        return False


def _generate_soul_from_description(description: str, agent_name: str = "UnClaude") -> str:
    """Use the configured LLM to generate a proactive.yaml from a natural language description."""
    import asyncio

    config = load_config()
    provider_name = config.get("default_provider", "gemini")
    provider_config = config.get("providers", {}).get(provider_name, {})
    model = provider_config.get("model")

    # Load API key
    api_key = load_credential(provider_name)
    if api_key:
        provider_info = PROVIDERS.get(provider_name, {})
        env_var = provider_info.get("env_var")
        if env_var:
            os.environ[env_var] = api_key

    # Build the prompt
    # Include one example behavior so the LLM understands the format
    example_behavior = yaml.dump([{
        "name": "check_owner_projects",
        "enabled": True,
        "interval": "6h",
        "active_hours": [9, 21],
        "priority": "low",
        "notify": True,
        "task": (
            "Check on the owner's projects and see if anything needs attention.\n\n"
            "1. Look at the current project directory for:\n"
            "   - Open TODOs or FIXMEs in the code\n"
            "   - Failing tests (if a test runner is configured)\n"
            "2. If you find something actionable, notify the owner with a summary\n"
            "3. Don't fix things on your own — just report what you see\n"
        ),
    }], default_flow_style=False, sort_keys=False)

    system_prompt = f"""You are a YAML generator for an AI agent's "soul" configuration file.

The user will describe what they want their agent to do in natural language. You must generate a complete, valid YAML configuration file.

The YAML structure must be EXACTLY this format:

```yaml
identity:
  name: <agent_name>
  tagline: "<short description>"
  personality:
    - "<trait 1>"
    - "<trait 2>"
    # 3-5 personality traits

drives:
  - "<motivation 1>"
  - "<motivation 2>"
  # 3-5 high-level drives

boundaries:
  - "Never push to git without explicit owner approval"
  - "Never spend money (API costs from normal LLM usage are fine)"
  - "Never delete files outside the project directory"
  - "Never send messages pretending to be the owner"
  - "Never run destructive commands (rm -rf, DROP TABLE, etc.)"
  - "If unsure, notify the owner and wait rather than act"

behaviors:
  - name: <snake_case_name>
    enabled: true
    interval: "<number><unit>"  # e.g. "4h", "30m", "1d", "12h"
    active_hours: [<start_hour>, <end_hour>]  # 24h format, or "always"
    priority: <background|low|normal|high>
    notify: <true|false>  # notify owner when this runs
    task: >
      <Detailed multi-line instructions for the agent.
      Be specific. Include numbered steps.
      The agent will execute this as a task prompt.>

  # ... more behaviors

check_interval_seconds: 60
idle_threshold_seconds: 120
```

EXAMPLE BEHAVIOR:
{example_behavior}

IMPORTANT RULES:
- The agent name is "{agent_name}"
- Always include the 6 safety boundaries listed above (they are non-negotiable)
- Each behavior's "task" field must be detailed, multi-line instructions with numbered steps
- Use realistic intervals (don't check every 1 minute — minimum "30m" for most things)
- Set active_hours sensibly (e.g. don't run project checks at 3am)
- If the user mentions Moltbook or social media, the agent has credentials at ~/.config/moltbook/credentials.json and should use the Moltbook API (base: https://www.moltbook.com/api/v1)
- If notify is true, the task should include "use the notify_owner tool" in its steps
- Output ONLY valid YAML. No markdown code fences. No explanation before or after.
- Start the output with the comment header block"""

    user_prompt = f"Generate a soul for an agent named \"{agent_name}\" based on this description:\n\n{description}"

    # Call the LLM
    try:
        import litellm

        prefix = PROVIDERS.get(provider_name, {}).get("prefix", "")
        model_name = f"{prefix}{model}" if model else f"{prefix}{PROVIDERS.get(provider_name, {}).get('default_model', '')}"

        response = litellm.completion(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=4000,
        )

        result = response.choices[0].message.content.strip()

        # Clean up: remove markdown code fences if the LLM added them
        if result.startswith("```"):
            # Remove first line (```yaml or ```)
            lines = result.split("\n")
            lines = lines[1:]
            # Remove last line if it's ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            result = "\n".join(lines)

        # Validate it's parseable YAML
        parsed = yaml.safe_load(result)
        if not isinstance(parsed, dict):
            raise ValueError("Generated YAML is not a valid dictionary")
        if "behaviors" not in parsed:
            raise ValueError("Generated YAML missing 'behaviors' section")
        if "identity" not in parsed:
            raise ValueError("Generated YAML missing 'identity' section")

        # Add the comment header if missing
        if not result.startswith("#"):
            header = (
                f"# ═══════════════════════════════════════════════════════════════\n"
                f"#  PROACTIVE.YAML — The Soul of {agent_name}\n"
                f"# ═══════════════════════════════════════════════════════════════\n"
                f"#\n"
                f"#  Generated from: \"{description[:80]}{'...' if len(description) > 80 else ''}\"\n"
                f"#\n"
                f"#  Edit anytime — changes are picked up live, no restart needed.\n"
                f"#\n\n"
            )
            result = header + result

        return result

    except ImportError:
        raise RuntimeError(
            "LiteLLM not available — install with: pip install litellm")


def _setup_soul_pick_list() -> bool:
    """Soul setup via picking from a preset list of behaviors."""
    agent_name = Prompt.ask("Agent name", default="UnClaude")
    tagline = Prompt.ask(
        "Tagline",
        default="Open-source AI agent that actually does things",
    )

    # Behavior selection
    console.print()
    console.print("[bold]Choose proactive behaviors:[/bold]\n")

    enabled = []
    for b in DEFAULT_BEHAVIORS:
        default_on = b["default"]
        label = f"{b['label']} — every {b['interval']}"
        if Confirm.ask(f"  {label}", default=default_on):
            enabled.append(b["key"])

    # Generate and save
    content = generate_soul(
        agent_name=agent_name,
        tagline=tagline,
        enabled_behaviors=enabled,
    )
    path = save_soul(content)

    console.print(f"\n[green]✓ Soul saved![/green] [dim]{path}[/dim]")
    console.print(f"[dim]Edit anytime — changes are picked up live.[/dim]")
    return True


def _setup_daemon() -> bool:
    """Offer to start the daemon. Returns True if started."""
    console.print(
        "The daemon runs in the background, picking up tasks\n"
        "and executing proactive behaviors from your soul file.\n"
    )

    if not Confirm.ask("Start the agent daemon now?", default=True):
        console.print("[dim]Start it later: unclaude agent start[/dim]")
        return False

    try:
        from unclaude.autonomous.daemon import AgentDaemon

        daemon = AgentDaemon(project_path=Path.cwd())
        if daemon.is_running():
            console.print("[green]✓ Daemon is already running![/green]")
            return True

        pid = daemon.start_background()
        console.print(
            f"[green]✓ Daemon started![/green] [dim](pid {pid})[/dim]")
        return True
    except Exception as e:
        console.print(f"[yellow]Could not start daemon: {e}[/yellow]")
        console.print("[dim]Start manually: unclaude agent start[/dim]")
        return False


def run_full_setup() -> dict[str, Any]:
    """Run the complete setup — provider, messaging, soul, daemon.

    This is the main entry point for new users. Takes them from
    zero to fully autonomous in one guided flow.

    Returns:
        Configuration dictionary.
    """
    total_steps = 4

    # Welcome
    console.print()
    console.print(
        Panel(
            "[bold cyan]Welcome to UnClaude![/bold cyan]\n\n"
            "The open-source AI agent that works for you.\n"
            "Let's get everything set up.",
            title="🤖 Setup",
            border_style="cyan",
        )
    )

    # ── Step 1: Provider ──
    _step_header(1, total_steps, "AI Provider")

    config = load_config()
    if config.get("default_provider"):
        provider = config["default_provider"]
        provider_config = config.get("providers", {}).get(provider, {})
        model = provider_config.get("model", "default")
        provider_name = PROVIDERS.get(provider, {}).get("name", provider)
        console.print(
            f"[green]✓ Already configured:[/green] {provider_name} / {model}")
        if Confirm.ask("Reconfigure?", default=False):
            config = _run_provider_setup()
    else:
        config = _run_provider_setup()

    # ── Step 2: Messaging ──
    _step_header(2, total_steps, "Stay Connected")

    messaging_ok = False
    try:
        from unclaude.messaging import get_messenger
        messenger = get_messenger()
        status = messenger.get_status()
        platforms = status.get("platforms", {})
        tg = platforms.get("telegram", {})
        if tg.get("configured"):
            console.print("[green]✓ Telegram already connected![/green]")
            messaging_ok = True
        else:
            messaging_ok = _setup_messaging()
    except Exception:
        messaging_ok = _setup_messaging()

    # ── Step 3: Soul ──
    _step_header(3, total_steps, "Agent Soul")
    soul_ok = _setup_soul()

    # ── Step 4: Daemon ──
    _step_header(4, total_steps, "Go Autonomous")
    daemon_ok = _setup_daemon()

    # ── Summary ──
    console.print()

    # Build summary lines
    provider = config.get("default_provider", "?")
    provider_name = PROVIDERS.get(provider, {}).get("name", provider)
    model = config.get("providers", {}).get(
        provider, {}).get("model", "default")

    check = "[green]✓[/green]"
    skip = "[dim]○[/dim]"

    summary = (
        f"{check} Provider: [cyan]{provider_name}[/cyan] / [cyan]{model}[/cyan]\n"
        f"{check if messaging_ok else skip} Telegram notifications\n"
        f"{check if soul_ok else skip} Agent soul (proactive behaviors)\n"
        f"{check if daemon_ok else skip} Daemon running\n"
    )

    commands = (
        "[bold]What you can do now:[/bold]\n\n"
        "  [cyan]unclaude[/cyan] \"fix the login bug\"   Chat or one-shot task\n"
        "  [cyan]unclaude agent status[/cyan]            Check daemon status\n"
        "  [cyan]unclaude agent task[/cyan] \"do X\"      Submit task to daemon\n"
        "  [cyan]unclaude agent soul[/cyan]              View proactive behaviors\n"
    )
    if messaging_ok:
        commands += "  [dim]Or just message your Telegram bot![/dim]\n"
    commands += (
        "\n"
        "[dim]Edit your soul:  ~/.unclaude/proactive.yaml[/dim]\n"
        "[dim]Edit config:     ~/.unclaude/config.yaml[/dim]\n"
    )

    console.print(
        Panel(
            f"{summary}\n{commands}",
            title="✅ Setup Complete",
            border_style="green",
        )
    )

    return config


def _run_provider_setup() -> dict[str, Any]:
    """Run just the provider/key/model setup (steps 1-3 of old onboarding)."""
    provider = select_provider()
    api_key = get_api_key(provider)
    if api_key:
        save_credential(provider, api_key)
    model = select_model(provider)

    config = {
        "default_provider": provider,
        "providers": {
            provider: {
                "model": model,
            }
        }
    }
    save_config(config)

    provider_name = PROVIDERS[provider]["name"]
    console.print(
        f"\n[green]✓ Provider configured:[/green] {provider_name} / {model}")
    return config


def ensure_configured() -> dict[str, Any]:
    """Ensure UnClaude is configured, running full setup if needed.

    For non-technical users, offers web-based setup as the first option.

    Returns:
        Configuration dictionary.
    """
    if is_configured():
        return load_config()

    # Offer web-based setup for non-technical users
    console.print()
    console.print(
        Panel(
            "[bold cyan]Welcome to UnClaude![/bold cyan]\n\n"
            "How would you like to set up?\n\n"
            "  [cyan]1.[/cyan] 🌐 [bold]Web browser[/bold] — visual setup wizard (recommended)\n"
            "  [cyan]2.[/cyan] 💻 [bold]Terminal[/bold] — guided command-line setup\n",
            title="🤖 First-Time Setup",
            border_style="cyan",
        )
    )

    choice = Prompt.ask("Choose", choices=["1", "2"], default="1")

    if choice == "1":
        return _launch_web_setup()
    else:
        return run_full_setup()


def _launch_web_setup() -> dict[str, Any]:
    """Launch the web UI for browser-based setup."""
    try:
        import uvicorn
        import webbrowser
        from unclaude.web.server import create_app
    except ImportError:
        console.print("[yellow]Web dependencies not installed.[/yellow]")
        console.print("[dim]Install with: pip install unclaude[web][/dim]")
        console.print("[dim]Falling back to terminal setup...[/dim]\n")
        return run_full_setup()

    port = 8765
    url = f"http://127.0.0.1:{port}"

    console.print()
    console.print(
        Panel(
            f"[bold cyan]Opening setup wizard in your browser...[/bold cyan]\n\n"
            f"🌐 [link={url}]{url}[/link]\n\n"
            "[dim]Complete the setup in the browser, then press Ctrl+C here.[/dim]",
            title="🚀 Web Setup",
            border_style="cyan",
        )
    )

    webbrowser.open(url)

    web_app = create_app()
    try:
        uvicorn.run(web_app, host="127.0.0.1", port=port, log_level="warning")
    except KeyboardInterrupt:
        pass

    # After web setup, reload config
    if is_configured():
        console.print("\n[green]✓ Setup complete![/green]")
        return load_config()
    else:
        console.print(
            "\n[yellow]Setup not completed — run 'unclaude setup' to try again.[/yellow]")
        return load_config()
