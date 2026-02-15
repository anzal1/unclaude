"""CLI interface for UnClaude.

Simplified CLI — enhanced mode is the default. Settings come from
~/.unclaude/config.yaml so you don't need CLI flags for every run.

Quick start:
    unclaude setup                         # First-time setup (one command)
    unclaude "fix the login bug"           # One-shot task
    unclaude                               # Interactive chat
    unclaude agent start                   # Start 24/7 daemon
    unclaude agent task "refactor auth"    # Submit task to daemon
    unclaude agent soul                    # View proactive behaviors
"""

from unclaude.providers import Provider
from unclaude.config import get_settings, save_config, ProviderConfig, load_config
from unclaude.agent import AgentLoop, EnhancedAgentLoop
from unclaude import __version__
from rich.table import Table
from rich.prompt import Prompt
from rich.panel import Panel
from rich.markdown import Markdown
from rich.console import Console
import typer
import asyncio
import signal
import os
import warnings
from pathlib import Path

# Suppress noisy warnings from LiteLLM
warnings.filterwarnings("ignore", message="Pydantic serializer warnings")
warnings.filterwarnings("ignore", message="coroutine.*was never awaited")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="litellm")
warnings.filterwarnings("ignore", message="Enable tracemalloc")


app = typer.Typer(
    name="unclaude",
    help="Open Source AI Coding Agent — autonomous, swarming, zero-config",
    no_args_is_help=False,
    invoke_without_command=True,
)

# Sub-command groups
agent_app = typer.Typer(help="Manage the autonomous 24/7 agent daemon")
app.add_typer(agent_app, name="agent")

usage_app = typer.Typer(help="Token usage tracking and budget management")
app.add_typer(usage_app, name="usage")

messaging_app = typer.Typer(
    help="Messaging integrations (Telegram, WhatsApp, webhooks)")
app.add_typer(messaging_app, name="messaging")

console = Console()


def _setup_provider(headless: bool = False, provider_override: str | None = None, model_override: str | None = None):
    """Common provider setup — load config, API key, return provider.

    Reads defaults from ~/.unclaude/config.yaml so users don't
    need to pass --provider and --model every time.
    """
    from unclaude.onboarding import ensure_configured, get_provider_api_key, PROVIDERS, load_config as onb_load_config

    if headless:
        settings = get_settings()
        config = {
            "default_provider": settings.default_provider,
            "providers": {k: {"model": v.model} for k, v in settings.providers.items()},
        }
    else:
        config = ensure_configured()

    use_provider = provider_override or config.get(
        "default_provider", "gemini")
    provider_config = config.get("providers", {}).get(use_provider, {})
    use_model = model_override or provider_config.get("model")

    # Load API key
    if headless:
        api_key = os.environ.get(f"{use_provider.upper()}_API_KEY")
    else:
        api_key = get_provider_api_key(use_provider)

    if api_key:
        provider_info = PROVIDERS.get(use_provider, {})
        env_var = provider_info.get("env_var")
        if env_var:
            os.environ[env_var] = api_key

    from unclaude.providers.llm import Provider as LLMProvider
    llm_provider = LLMProvider(use_provider)
    if use_model:
        llm_provider.config.model = use_model

    return llm_provider, use_provider, use_model, config


def print_banner() -> None:
    """Print the UnClaude banner."""
    # Quick budget check
    budget_line = ""
    try:
        from unclaude.usage import get_usage_tracker
        tracker = get_usage_tracker()
        status = tracker.check_budget()
        if status.get("budget_set"):
            pct = status["percentage"]
            color = "green" if pct < 50 else ("yellow" if pct < 80 else "red")
            budget_line = f"\n[{color}]Budget: ${status['current_spend']:.4f} / ${status['limit']:.2f} ({pct:.0f}%)[/{color}]"
    except Exception:
        pass

    console.print(
        Panel(
            "[bold cyan]UnClaude[/bold cyan] - Autonomous AI Coding Agent\n"
            f"Version {__version__} | Swarming | Self-Discovering | Zero-Config"
            f"{budget_line}",
            title="🤖",
            border_style="cyan",
        )
    )


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    provider: str = typer.Option(
        None, "--provider", "-p", help="Override LLM provider"),
    model: str = typer.Option(None, "--model", "-m", help="Override model"),
    classic: bool = typer.Option(
        False, "--classic", help="Use classic agent (no v2 modules)"),
) -> None:
    """Open Source AI Coding Agent — autonomous, swarming, zero-config.

    Run with no arguments to start interactive chat.
    Use subcommands for specific features.

    Quick start:
        unclaude setup                   # Full guided setup
        unclaude                         # Interactive chat
        unclaude chat "fix the bug"      # One-shot task
        unclaude agent start             # 24/7 daemon
        unclaude agent soul              # View proactive behaviors
    """
    if ctx.invoked_subcommand is not None:
        return

    # No subcommand → start interactive chat
    _run_chat(
        message=None,
        provider_override=provider,
        model_override=model,
        headless=False,
        json_output=False,
        classic=classic,
    )


def _run_chat(
    message: str | None = None,
    provider_override: str | None = None,
    model_override: str | None = None,
    headless: bool = False,
    json_output: bool = False,
    classic: bool = False,
) -> None:
    """Core chat logic — used by both the default callback and the chat subcommand."""
    import json as json_lib

    try:
        llm_provider, use_provider, use_model, config = _setup_provider(
            headless=headless, provider_override=provider_override, model_override=model_override
        )
    except Exception as e:
        if json_output:
            print(json_lib.dumps({"error": str(e), "success": False}))
        else:
            console.print(f"[red]Error creating provider: {e}[/red]")
        raise typer.Exit(1)

    if not headless:
        print_banner()
        console.print(
            f"[dim]Provider: {use_provider} | Model: {use_model or 'default'}[/dim]")
        console.print(f"[dim]Working directory: {os.getcwd()}[/dim]")

    # Read security/routing from config (no CLI flags needed)
    settings = get_settings()
    security_profile = settings.security.profile
    routing_profile_str = settings.routing.profile

    if not classic:
        from unclaude.routing import RoutingProfile as RP
        rp = RP(routing_profile_str)
        agent = EnhancedAgentLoop(
            provider=llm_provider,
            security_profile=security_profile,
            routing_profile=rp,
            preferred_provider=use_provider,
        )
        if not headless:
            console.print(
                f"[dim]Security: {security_profile} | Routing: {routing_profile_str}[/dim]")
    else:
        agent = AgentLoop(provider=llm_provider)
        if not headless:
            console.print("[dim]Mode: Classic[/dim]")

    if not headless:
        console.print("[dim]Type 'exit' to end, '/help' for commands[/dim]\n")

    async def run_chat_async() -> None:
        if message:
            if not headless:
                console.print(f"[bold]You:[/bold] {message}\n")
            response = await agent.run(message)

            if json_output:
                print(json_lib.dumps({"response": response, "success": True}))
            elif not headless:
                console.print(Panel(Markdown(response),
                              title="UnClaude", border_style="green"))
                console.print()
            else:
                print(response)

        if headless and message:
            return
        if headless:
            return

        while True:
            try:
                user_input = Prompt.ask("[bold]You[/bold]")
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Goodbye![/dim]")
                break

            if not user_input.strip():
                continue

            if user_input.lower() in ("exit", "quit"):
                console.print("[dim]Goodbye![/dim]")
                break

            if user_input.lower() == "/clear":
                agent.reset()
                console.print("[dim]Context cleared.[/dim]")
                continue

            if user_input.lower() == "/help":
                help_text = (
                    "**Commands:**\n"
                    "- `/clear` - Clear conversation history\n"
                    "- `/status` - Show session status\n"
                    "- `/help` - Show this help\n"
                    "- `exit` / `quit` - End session\n"
                    "\n**Tips:**\n"
                    "- Ask to read files before editing\n"
                    "- Be specific about what you want\n"
                )
                console.print(Panel(help_text, title="Help"))
                continue

            if user_input.lower() in ("/status", "/session") and not classic:
                import json as json_mod
                summary = agent.get_session_summary()
                console.print(Panel(
                    json_mod.dumps(summary, indent=2, default=str),
                    title="Session Status",
                    border_style="blue",
                ))
                continue

            console.print()
            try:
                response = await agent.run(user_input)
                if response:
                    console.print(Panel(Markdown(response),
                                  title="UnClaude", border_style="green"))
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
            console.print()

    asyncio.run(run_chat_async())


@app.command()
def chat(
    message: str = typer.Argument(None, help="Message to send"),
    provider: str = typer.Option(
        None, "--provider", "-p", help="Override LLM provider"),
    model: str = typer.Option(None, "--model", "-m", help="Override model"),
    headless: bool = typer.Option(
        False, "--headless", "-H", help="Non-interactive mode (for CI/CD)"),
    json_output: bool = typer.Option(
        False, "--json", "-j", help="JSON output"),
    classic: bool = typer.Option(
        False, "--classic", help="Use classic agent (no v2 modules)"),
) -> None:
    """Chat with UnClaude or run a one-shot task.

    Examples:
        unclaude chat "what is 2+2"        # One-shot
        unclaude chat                      # Interactive
        unclaude chat "fix bug" -H         # Headless / CI
    """
    _run_chat(
        message=message,
        provider_override=provider,
        model_override=model,
        headless=headless,
        json_output=json_output,
        classic=classic,
    )


@app.command()
def config(
    set_provider: str = typer.Option(
        None, "--set-provider", help="Set the default provider"),
    show: bool = typer.Option(
        False, "--show", help="Show current configuration"),
) -> None:
    """Manage UnClaude configuration."""
    settings = get_settings()

    if show:
        console.print(Panel(
            f"**Default Provider:** {settings.default_provider}\n"
            f"**Config Directory:** {settings.config_dir}\n"
            f"**Configured Providers:** {list(settings.providers.keys()) or 'None'}",
            title="Configuration",
        ))
        return

    if set_provider:
        settings.default_provider = set_provider
        save_config(settings)
        console.print(
            f"[green]Default provider set to: {set_provider}[/green]")
        return

    # Interactive config
    console.print(
        "[yellow]Interactive configuration not yet implemented.[/yellow]")
    console.print(
        "Use environment variables or edit ~/.unclaude/config.yaml directly.")


@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Directory to initialize"),
) -> None:
    """Initialize UnClaude in a project directory.

    Creates an UNCLAUDE.md file that customizes behavior per-project.
    For global setup (provider, messaging, soul), use: unclaude setup
    """
    unclaude_md = path / "UNCLAUDE.md"

    if unclaude_md.exists():
        console.print(f"[yellow]UNCLAUDE.md already exists in {path}[/yellow]")
        return

    template = """# Project Configuration for UnClaude

## Commands
- `npm run dev` - Start development server
- `npm test` - Run tests
- `npm run build` - Build for production

## Code Style
- Follow the existing code style in the project
- Use meaningful variable and function names
- Add comments for complex logic

## Architecture
- Describe your project structure here
- List important directories and their purposes

## Skills
<!-- Define reusable workflows here -->
"""

    unclaude_md.write_text(template)
    console.print(f"[green]Created UNCLAUDE.md in {path}[/green]")
    console.print(
        "Edit this file to customize UnClaude's behavior for your project.")


@app.command()
def version() -> None:
    """Show the UnClaude version."""
    console.print(f"UnClaude version {__version__}")


@app.command()
def login() -> None:
    """Re-run provider setup (API key + model only)."""
    from unclaude.onboarding import _run_provider_setup
    _run_provider_setup()


@app.command()
def setup() -> None:
    """Full guided setup — provider, messaging, soul, daemon.

    Takes you from zero to fully autonomous agent. Run this once
    after installing, or anytime to reconfigure.

    Examples:
        unclaude setup
    """
    from unclaude.onboarding import run_full_setup
    run_full_setup()


@app.command()
def ralph(
    task: str = typer.Argument(..., help="The task to complete autonomously"),
    max_iterations: int = typer.Option(
        50, "--max-iterations", "-i", help="Maximum iterations"),
    max_cost: float = typer.Option(
        10.0, "--max-cost", "-c", help="Maximum cost in USD"),
    feedback: list[str] = typer.Option(
        ["npm test"], "--feedback", "-f", help="Feedback commands"),
) -> None:
    """Run Ralph Wiggum mode for autonomous task completion.

    Ralph Wiggum mode runs the agent in a loop, using test/lint feedback
    to iterate until the task is complete or limits are reached.
    """
    from unclaude.agent import AgentLoop, RalphWiggumMode
    from unclaude.onboarding import ensure_configured, get_provider_api_key, PROVIDERS

    # Ensure configured
    config = ensure_configured()

    print_banner()
    console.print(
        "[bold cyan]Ralph Wiggum Mode[/bold cyan] - Autonomous Iteration\n")

    # Load settings from config
    use_provider = config.get("default_provider", "gemini")
    provider_config = config.get("providers", {}).get(use_provider, {})
    use_model = provider_config.get("model")

    # Load API key and set environment variable
    api_key = get_provider_api_key(use_provider)
    if api_key:
        provider_info = PROVIDERS.get(use_provider, {})
        env_var = provider_info.get("env_var")
        if env_var:
            os.environ[env_var] = api_key

    # Create provider
    from unclaude.providers.llm import Provider as LLMProvider
    llm_provider = LLMProvider(use_provider)
    if use_model:
        llm_provider.config.model = use_model

    console.print(
        f"[dim]Provider: {use_provider} | Model: {use_model or 'default'}[/dim]")

    agent = AgentLoop(provider=llm_provider)

    ralph_mode = RalphWiggumMode(
        agent_loop=agent,
        feedback_commands=feedback,
        max_iterations=max_iterations,
        max_cost=max_cost,
    )

    async def run_ralph() -> None:
        # Check for plan and invoke planner if missing
        task_file = Path.cwd() / "TASK.md"
        if not task_file.exists():
            console.print(Panel(
                "[bold yellow]No TASK.md found. Invoking Planner Agent...[/bold yellow]", title="Orchestrator"))
            from unclaude.agent.planner import PlannerAgent
            planner = PlannerAgent(provider=llm_provider)
            # Run planner
            await planner.run(f"Create a detailed execution plan for: {task}")
            console.print("[bold green]✓ Plan created![/bold green]")

        result = await ralph_mode.run(task)

        console.print("\n" + "=" * 50)
        if result.success:
            console.print(
                "[bold green]✓ Task completed successfully![/bold green]")
        else:
            console.print(
                f"[bold red]✗ Task did not complete: {result.error}[/bold red]")

        console.print(f"Iterations: {result.iterations}")
        console.print(f"Estimated cost: ${result.total_cost:.2f}")

    asyncio.run(run_ralph())


@app.command()
def plan(
    task: str = typer.Argument(..., help="The task to plan"),
) -> None:
    """Generate a detailed execution plan (TASK.md) for a task."""
    from unclaude.agent.planner import PlannerAgent
    from unclaude.onboarding import ensure_configured, get_provider_api_key, PROVIDERS

    # Ensure configured
    config = ensure_configured()

    # Load settings from config
    use_provider = config.get("default_provider", "gemini")
    provider_config = config.get("providers", {}).get(use_provider, {})
    use_model = provider_config.get("model")

    # Load API key
    api_key = get_provider_api_key(use_provider)
    if api_key:
        provider_info = PROVIDERS.get(use_provider, {})
        env_var = provider_info.get("env_var")
        if env_var:
            os.environ[env_var] = api_key

    try:
        from unclaude.providers.llm import Provider as LLMProvider
        llm_provider = LLMProvider(use_provider)
        if use_model:
            llm_provider.config.model = use_model
    except Exception as e:
        console.print(f"[red]Error creating provider: {e}[/red]")
        raise typer.Exit(1)

    console.print(
        Panel(f"[bold cyan]Planning Task:[/bold cyan] {task}", title="Planner Agent"))

    planner = PlannerAgent(provider=llm_provider)

    async def run_plan():
        response = await planner.run(f"Create a plan for: {task}")
        console.print(Panel(Markdown(response),
                      title="Plan Generated", border_style="green"))

    asyncio.run(run_plan())


@app.command()
def plugins(
    list_plugins: bool = typer.Option(
        False, "--list", "-l", help="List installed plugins"),
    create: str = typer.Option(
        None, "--create", "-c", help="Create a new plugin template"),
) -> None:
    """Manage UnClaude plugins."""
    from unclaude.plugins import PluginManager, create_plugin_template

    plugin_manager = PluginManager()

    if list_plugins:
        plugins_loaded = plugin_manager.load_all_plugins()
        if not plugins_loaded:
            console.print("[yellow]No plugins installed.[/yellow]")
            console.print(f"Plugin directory: {plugin_manager.plugins_dir}")
            return

        console.print("[bold]Installed Plugins:[/bold]\n")
        for plugin in plugins_loaded:
            console.print(
                f"  📦 [cyan]{plugin.name}[/cyan] v{plugin.manifest.version}")
            console.print(f"     {plugin.manifest.description}")
            console.print(
                f"     Tools: {len(plugin.tools)}, Hooks: {len(plugin.hooks)}")
        return

    if create:
        plugin_path = plugin_manager.plugins_dir / create
        if plugin_path.exists():
            console.print(f"[red]Plugin '{create}' already exists.[/red]")
            return

        create_plugin_template(create, plugin_path)
        console.print(
            f"[green]Created plugin template at {plugin_path}[/green]")
        return

    console.print("Use --list to see plugins or --create to create a new one.")


@app.command()
def skills(
    list_skills: bool = typer.Option(
        False, "--list", "-l", help="List available skills"),
    run_skill: str = typer.Option(
        None, "--run", "-r", help="Run a skill by name"),
    create: str = typer.Option(
        None, "--create", "-c", help="Create a new skill template"),
) -> None:
    """Manage and run UnClaude skills."""
    from unclaude.skills import SkillsEngine, create_skill_template

    engine = SkillsEngine()

    if list_skills:
        skill_names = engine.list_skills()
        if not skill_names:
            console.print("[yellow]No skills found.[/yellow]")
            console.print("Add skills to UNCLAUDE.md or ~/.unclaude/skills/")
            return

        console.print("[bold]Available Skills:[/bold]\n")
        for name in skill_names:
            skill = engine.get_skill(name)
            if skill:
                console.print(f"  🔧 [cyan]{name}[/cyan]")
                console.print(f"     {skill.description}")
                console.print(f"     Steps: {len(skill.steps)}")
        return

    if create:
        skill_path = Path.home() / ".unclaude" / "skills" / f"{create}.yaml"
        if skill_path.exists():
            console.print(f"[red]Skill '{create}' already exists.[/red]")
            return

        create_skill_template(create, skill_path)
        console.print(f"[green]Created skill template at {skill_path}[/green]")
        return

    if run_skill:
        skill = engine.get_skill(run_skill)
        if not skill:
            console.print(f"[red]Skill '{run_skill}' not found.[/red]")
            return

        # Load configuration and API key
        from unclaude.onboarding import ensure_configured, get_provider_api_key, PROVIDERS
        config = ensure_configured()
        use_provider = config.get("default_provider", "gemini")
        provider_config = config.get("providers", {}).get(use_provider, {})
        use_model = provider_config.get("model")

        # Load and set API key
        api_key = get_provider_api_key(use_provider)
        if api_key:
            provider_info = PROVIDERS.get(use_provider, {})
            env_var = provider_info.get("env_var")
            if env_var:
                os.environ[env_var] = api_key

        # Create provider
        from unclaude.providers.llm import Provider as LLMProvider
        try:
            llm_provider = LLMProvider(use_provider)
            if use_model:
                llm_provider.config.model = use_model
        except Exception as e:
            console.print(f"[red]Error creating provider: {e}[/red]")
            return

        # Generate prompt and run with agent
        from unclaude.agent import AgentLoop

        prompt = engine.generate_skill_prompt(skill)
        console.print(f"[dim]Running skill: {run_skill}[/dim]")
        console.print(
            f"[dim]Provider: {use_provider} | Model: {use_model or 'default'}[/dim]\n")

        agent = AgentLoop(provider=llm_provider)

        async def run_skill_async() -> None:
            response = await agent.run(prompt)
            console.print(
                Panel(response, title=f"Skill: {run_skill}", border_style="green"))

        asyncio.run(run_skill_async())
        return

    console.print(
        "Use --list to see skills, --run to execute one, or --create to make a new one.")


@app.command()
def mcp(
    list_servers: bool = typer.Option(
        False, "--list", "-l", help="List configured MCP servers"),
    init_config: bool = typer.Option(
        False, "--init", help="Create MCP config template"),
) -> None:
    """Manage MCP (Model Context Protocol) servers."""
    from unclaude.mcp import MCPClient, create_mcp_config_template

    client = MCPClient()

    if init_config:
        if client.config_path.exists():
            console.print(
                f"[yellow]MCP config already exists at {client.config_path}[/yellow]")
            return

        client.config_path.parent.mkdir(parents=True, exist_ok=True)
        client.config_path.write_text(create_mcp_config_template())
        console.print(
            f"[green]Created MCP config at {client.config_path}[/green]")
        return

    if list_servers:
        configs = client._load_config()
        if not configs:
            console.print("[yellow]No MCP servers configured.[/yellow]")
            console.print(f"Config file: {client.config_path}")
            console.print(
                "Run 'unclaude mcp --init' to create a config template.")
            return

        console.print("[bold]Configured MCP Servers:[/bold]\n")
        for name, config in configs.items():
            console.print(f"  🔌 [cyan]{name}[/cyan]")
            console.print(
                f"     Command: {config.command} {' '.join(config.args)}")
        return

    console.print("Use --list to see servers or --init to create config.")


@app.command()
def background(
    task: str = typer.Argument(..., help="Task to run in background"),
) -> None:
    """Run a task in the background without blocking."""
    from unclaude.agent.background import BackgroundAgentManager

    manager = BackgroundAgentManager()
    job_id = manager.start_background_task(task)
    console.print(f"[green]Started background job:[/green] {job_id}")
    console.print(f"[dim]Check status with: unclaude jobs {job_id}[/dim]")


@app.command()
def jobs(
    job_id: str = typer.Argument(None, help="Specific job ID to check"),
) -> None:
    """List or check status of background jobs."""
    from unclaude.agent.background import BackgroundAgentManager

    manager = BackgroundAgentManager()

    if job_id:
        job = manager.get_job_status(job_id)
        if not job:
            console.print(f"[red]Job not found: {job_id}[/red]")
            return

        console.print(f"\n[bold]Job {job.job_id}[/bold]")
        console.print(f"Task: {job.task}")
        console.print(f"Status: {job.status}")
        console.print(f"Started: {job.started_at}")
        if job.completed_at:
            console.print(f"Completed: {job.completed_at}")
        if job.result:
            console.print(f"Result:\n{job.result[:500]}...")
        if job.error:
            console.print(f"[red]Error: {job.error}[/red]")
    else:
        jobs_list = manager.list_jobs()
        if not jobs_list:
            console.print("[yellow]No background jobs found.[/yellow]")
            return

        console.print("\n[bold]Recent Background Jobs:[/bold]\n")
        for job in jobs_list:
            status_color = "green" if job.status == "completed" else "yellow" if job.status == "running" else "red"
            console.print(
                f"  [{status_color}]{job.job_id}[/{status_color}] - {job.task[:50]}... ({job.status})")


@app.command()
def web(
    port: int = typer.Option(8765, "--port", "-p",
                             help="Port to run the dashboard on"),
    no_browser: bool = typer.Option(
        False, "--no-browser", help="Don't open browser automatically"),
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
) -> None:
    """Launch the UnClaude web dashboard.

    Opens a beautiful local web interface for:
    - Chat with real-time streaming
    - Memory browser and management
    - Background job monitoring
    - Settings and configuration
    """
    try:
        import uvicorn
    except ImportError:
        console.print("[red]Error: uvicorn not installed.[/red]")
        console.print("Install with: pip install unclaude[web]")
        console.print("Or: pip install uvicorn fastapi websockets")
        raise typer.Exit(1)

    from unclaude.web.server import create_app

    url = f"http://{host}:{port}"

    console.print(Panel(
        f"[bold cyan]UnClaude Dashboard[/bold cyan]\n\n"
        f"🌐 URL: [link={url}]{url}[/link]\n"
        f"📡 API: {url}/api/\n\n"
        "[dim]Press Ctrl+C to stop[/dim]",
        title="🚀 Starting Web Server",
        border_style="cyan",
    ))

    if not no_browser:
        import webbrowser
        webbrowser.open(url)

    # Create and run the app
    web_app = create_app()
    uvicorn.run(web_app, host=host, port=port, log_level="warning")


# ─── Agent Daemon Commands ─────────────────────────────────────────

@agent_app.command("start")
def agent_start(
    foreground: bool = typer.Option(
        False, "--foreground", "-f", help="Run in foreground (default: background daemon)"),
) -> None:
    """Start the autonomous agent daemon.

    The daemon runs 24/7, watching for tasks from:
    - .unclaude/tasks/*.md files
    - TASKS.md checkboxes
    - Direct submission via `unclaude agent task`
    """
    from unclaude.autonomous.daemon import AgentDaemon

    daemon = AgentDaemon(project_path=Path.cwd())

    if daemon.is_running():
        console.print("[yellow]Agent daemon is already running.[/yellow]")
        console.print(
            "[dim]Use 'unclaude agent status' to check, 'unclaude agent stop' to halt.[/dim]")
        return

    if foreground:
        # Show soul status in the panel
        soul_line = ""
        try:
            soul = daemon._load_soul()
            if soul:
                behaviors = soul.get("behaviors", [])
                active = sum(1 for b in behaviors if isinstance(
                    b, dict) and b.get("enabled"))
                soul_line = f"\n  🧠 Soul: {active} proactive behaviors active\n"
            else:
                soul_line = "\n  [dim]No soul — run 'unclaude setup' to add proactive behaviors[/dim]\n"
        except Exception:
            pass

        console.print(Panel(
            "[bold cyan]Agent Daemon[/bold cyan] — Foreground Mode\n\n"
            "Watching for tasks from:\n"
            f"  📁 .unclaude/tasks/*.md\n"
            f"  📋 TASKS.md\n"
            f"  💬 unclaude agent task \"...\"\n"
            f"{soul_line}\n"
            "[dim]Press Ctrl+C to stop[/dim]",
            title="🤖 Autonomous Agent",
            border_style="cyan",
        ))
        asyncio.run(daemon.run())
    else:
        daemon.start_background()
        console.print("[green]Agent daemon started in background.[/green]")
        console.print(
            "[dim]Submit tasks:  unclaude agent task \"fix the bug\"[/dim]")
        console.print("[dim]Check status:  unclaude agent status[/dim]")
        console.print("[dim]View soul:     unclaude agent soul[/dim]")
        console.print("[dim]Stop daemon:   unclaude agent stop[/dim]")


@agent_app.command("stop")
def agent_stop() -> None:
    """Stop the autonomous agent daemon."""
    from unclaude.autonomous.daemon import AgentDaemon

    daemon = AgentDaemon(project_path=Path.cwd())

    if not daemon.is_running():
        console.print("[yellow]No agent daemon is running.[/yellow]")
        return

    daemon.stop_daemon()
    console.print("[green]Agent daemon stopped.[/green]")


@agent_app.command("status")
def agent_status() -> None:
    """Show the status of the autonomous agent daemon."""
    from unclaude.autonomous.daemon import AgentDaemon

    daemon = AgentDaemon(project_path=Path.cwd())

    if not daemon.is_running():
        console.print("[dim]Agent daemon is not running.[/dim]")
        console.print("[dim]Start with: unclaude agent start[/dim]")
        return

    import json as json_mod

    data = AgentDaemon.read_status()
    if data:
        table = Table(title="Agent Daemon Status")
        table.add_column("Property", style="cyan")
        table.add_column("Value")
        table.add_row(
            "Status", f"[green]{data.get('status', 'unknown')}[/green]")
        table.add_row("PID", str(data.get("pid", "?")))
        table.add_row("Tasks Completed", str(data.get("tasks_completed", 0)))
        table.add_row("Tasks Failed", str(data.get("tasks_failed", 0)))
        table.add_row("Queue Pending", str(data.get("queue_pending", 0)))
        console.print(table)
    else:
        console.print("[green]Agent daemon is running.[/green]")


@agent_app.command("task")
def agent_task(
    description: str = typer.Argument(..., help="Task description"),
    priority: str = typer.Option("normal", "--priority", "-p",
                                 help="Priority: critical, high, normal, low, background"),
    wait: bool = typer.Option(False, "--wait", "-w",
                              help="Wait for task completion and show result"),
) -> None:
    """Submit a task to the running agent daemon.

    Examples:
        unclaude agent task "fix the login bug"
        unclaude agent task "add unit tests for auth" -p high
        unclaude agent task "update README" -p background
        unclaude agent task "explain the codebase" -w  # wait for result
    """
    from unclaude.autonomous.daemon import AgentDaemon, TaskPriority

    daemon = AgentDaemon(project_path=Path.cwd())

    # Map string to priority
    priority_map = {
        "critical": TaskPriority.CRITICAL,
        "high": TaskPriority.HIGH,
        "normal": TaskPriority.NORMAL,
        "low": TaskPriority.LOW,
        "background": TaskPriority.BACKGROUND,
    }
    task_priority = priority_map.get(priority, TaskPriority.NORMAL)

    task_id = daemon.submit_task(description, priority=task_priority)
    console.print(f"[green]Task submitted:[/green] {task_id}")
    console.print(f"[dim]{description}[/dim]")

    if not daemon.is_running():
        console.print("\n[yellow]Note: Agent daemon is not running.[/yellow]")
        console.print("[dim]Start it with: unclaude agent start[/dim]")
        return

    if wait:
        import time as time_mod
        console.print("[dim]Waiting for task to complete...[/dim]")
        with console.status("[cyan]Processing...", spinner="dots"):
            while True:
                time_mod.sleep(2)
                # Reload queue to check status
                from unclaude.autonomous.daemon import TaskQueue
                queue = TaskQueue()
                task = queue.get(task_id)
                if task and task.status.value in ("completed", "failed"):
                    break
        if task and task.status.value == "completed":
            console.print(
                f"\n[bold green]Task {task_id} completed![/bold green]")
            if task.result:
                console.print(
                    Panel(task.result, title="Result", border_style="green"))
        elif task and task.status.value == "failed":
            console.print(f"\n[bold red]Task {task_id} failed![/bold red]")
            if task.error:
                console.print(
                    Panel(task.error, title="Error", border_style="red"))


@agent_app.command("soul")
def agent_soul() -> None:
    """Show the agent's soul — its proactive behaviors and identity.

    The soul is defined in ~/.unclaude/proactive.yaml.
    Edit that file to change what the agent does on its own.

    Examples:
        unclaude agent soul
    """
    from unclaude.autonomous.daemon import AgentDaemon

    daemon = AgentDaemon(project_path=Path.cwd())
    soul = daemon._load_soul()

    if not soul:
        console.print("[yellow]No soul found.[/yellow]")
        console.print(
            "[dim]Create ~/.unclaude/proactive.yaml to give the agent purpose.[/dim]")
        return

    identity = soul.get("identity", {})
    drives = soul.get("drives", [])
    boundaries = soul.get("boundaries", [])
    behaviors = soul.get("behaviors", [])

    # Identity
    console.print(
        f"\n[bold magenta]{identity.get('name', 'UnClaude')}[/bold magenta]")
    console.print(f"[dim]{identity.get('tagline', '')}[/dim]")
    if identity.get("personality"):
        console.print(
            f"[dim]Personality: {', '.join(identity['personality'])}[/dim]")

    # Drives
    if drives:
        console.print(f"\n[bold]Drives:[/bold]")
        for d in drives:
            console.print(f"  [cyan]→[/cyan] {d}")

    # Behaviors
    if behaviors:
        from rich.table import Table
        table = Table(title="\nProactive Behaviors", show_lines=True)
        table.add_column("Name", style="white")
        table.add_column("Interval", style="cyan")
        table.add_column("Active Hours", style="dim")
        table.add_column("Enabled", style="green")
        table.add_column("Last Run", style="dim")

        # Load proactive state
        proactive_state = daemon._load_proactive_state()

        for b in behaviors:
            if not isinstance(b, dict):
                continue
            name = b.get("name", "?")
            interval = b.get("interval", "?")
            hours = b.get("active_hours", "always")
            enabled = "Yes" if b.get("enabled", True) else "[red]No[/red]"
            last_run = proactive_state.get(name, 0)
            if last_run:
                from datetime import datetime as dt
                last_str = dt.fromtimestamp(
                    last_run).strftime("%Y-%m-%d %H:%M")
            else:
                last_str = "Never"
            hours_str = f"{hours[0]:02d}:00-{hours[1]:02d}:00" if isinstance(
                hours, list) else str(hours)
            table.add_row(name, interval, hours_str, enabled, last_str)

        console.print(table)

    # Boundaries
    if boundaries:
        console.print(f"\n[bold red]Boundaries:[/bold red]")
        for b in boundaries:
            console.print(f"  [red]✗[/red] {b}")

    console.print(f"\n[dim]Edit: ~/.unclaude/proactive.yaml[/dim]")


@agent_app.command("result")
def agent_result(
    task_id: str = typer.Argument(
        None, help="Task ID to show result for (default: latest)"),
) -> None:
    """Show the result of a completed task.

    Examples:
        unclaude agent result          # Show latest task result
        unclaude agent result abc123   # Show specific task result
    """
    from unclaude.autonomous.daemon import TaskQueue

    queue = TaskQueue()
    tasks = queue.list_tasks(limit=100)

    if not tasks:
        console.print("[dim]No tasks found.[/dim]")
        return

    if task_id:
        # Find specific task
        task = queue.get(task_id)
        if not task:
            console.print(f"[red]Task {task_id} not found.[/red]")
            return
        _show_task_detail(task)
    else:
        # Show latest completed/failed task
        for t in tasks:
            if t.status.value in ("completed", "failed"):
                _show_task_detail(t)
                return
        console.print("[dim]No completed tasks yet.[/dim]")


@agent_app.command("list")
def agent_list() -> None:
    """List all tasks in the daemon queue."""
    from unclaude.autonomous.daemon import TaskQueue

    queue = TaskQueue()
    tasks = queue.list_tasks(limit=20)

    if not tasks:
        console.print("[dim]No tasks in queue.[/dim]")
        return

    table = Table(title="Task Queue")
    table.add_column("ID", style="cyan", width=10)
    table.add_column("Status", width=12)
    table.add_column("Priority", width=10)
    table.add_column("Description", max_width=50)
    table.add_column("Duration", width=10)

    status_colors = {
        "completed": "green",
        "failed": "red",
        "running": "yellow",
        "queued": "blue",
    }

    for t in tasks:
        status = t.status.value
        color = status_colors.get(status, "white")
        duration = ""
        if t.completed_at and t.started_at:
            duration = f"{t.completed_at - t.started_at:.1f}s"
        elif t.started_at:
            import time as time_mod
            duration = f"{time_mod.time() - t.started_at:.0f}s..."

        table.add_row(
            t.task_id,
            f"[{color}]{status}[/{color}]",
            t.priority.value,
            t.description[:50] + ("..." if len(t.description) > 50 else ""),
            duration,
        )

    console.print(table)


def _show_task_detail(task) -> None:
    """Show detailed info about a single task."""
    from datetime import datetime as dt

    status_colors = {"completed": "green", "failed": "red",
                     "running": "yellow", "queued": "blue"}
    color = status_colors.get(task.status.value, "white")

    console.print(f"\n[bold]Task:[/bold] {task.task_id}")
    console.print(
        f"[bold]Status:[/bold] [{color}]{task.status.value}[/{color}]")
    console.print(f"[bold]Priority:[/bold] {task.priority.value}")
    console.print(f"[bold]Source:[/bold] {task.source}")
    console.print(f"[bold]Description:[/bold] {task.description}")

    if task.started_at:
        console.print(
            f"[bold]Started:[/bold] {dt.fromtimestamp(task.started_at).strftime('%Y-%m-%d %H:%M:%S')}")
    if task.completed_at and task.started_at:
        console.print(
            f"[bold]Duration:[/bold] {task.completed_at - task.started_at:.1f}s")

    if task.result:
        console.print()
        console.print(Panel(task.result, title="Result",
                      border_style="green", expand=False))
    if task.error:
        console.print()
        console.print(Panel(task.error, title="Error",
                      border_style="red", expand=False))


# ─── Usage Commands ─────────────────────────────────────────────

@usage_app.callback(invoke_without_command=True)
def usage_default(ctx: typer.Context) -> None:
    """Show today's usage summary (default when no subcommand given)."""
    if ctx.invoked_subcommand is None:
        usage_show(period="today")


@usage_app.command("show")
def usage_show(
    period: str = typer.Option("today", "--period", "-p",
                               help="Time period: today|yesterday|week|month|all"),
) -> None:
    """Show usage summary for a time period.

    Examples:
        unclaude usage                    # Today's usage
        unclaude usage show -p week       # This week
        unclaude usage show -p month      # This month
        unclaude usage show -p all        # All time
    """
    from unclaude.usage import get_usage_tracker

    tracker = get_usage_tracker()
    summary = tracker.get_summary(period=period)

    # Budget check
    budget_status = tracker.check_budget()

    console.print()
    console.print(Panel(
        f"[bold]Token Usage — {period.upper()}[/bold]",
        border_style="cyan",
    ))

    # Main stats
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Requests", f"{summary.total_requests:,}")
    table.add_row("Prompt tokens", f"{summary.total_prompt_tokens:,}")
    table.add_row("Completion tokens", f"{summary.total_completion_tokens:,}")
    table.add_row("Total tokens", f"[cyan]{summary.total_tokens:,}[/cyan]")
    table.add_row(
        "Total cost", f"[{'green' if summary.total_cost_usd < 1 else 'yellow'}]${summary.total_cost_usd:.6f}[/]")
    table.add_row("Avg tokens/req", f"{summary.avg_tokens_per_request:,.0f}")
    table.add_row("Avg cost/req", f"${summary.avg_cost_per_request:.6f}")
    console.print(table)

    # Model breakdown
    if summary.models_used:
        console.print()
        model_table = Table(title="Models Used")
        model_table.add_column("Model", style="cyan")
        model_table.add_column("Requests", justify="right")
        for model, count in summary.models_used.items():
            model_table.add_row(model, str(count))
        console.print(model_table)

    # Budget status
    if budget_status.get("budget_set"):
        console.print()
        pct = budget_status["percentage"]
        color = "green" if pct < 50 else ("yellow" if pct < 80 else "red")
        bar_len = 30
        filled = int(bar_len * min(pct, 100) / 100)
        bar = f"[{color}]{'█' * filled}{'░' * (bar_len - filled)}[/{color}]"

        console.print(
            f"  Budget ({budget_status['period']}): {bar} {pct:.1f}%")
        console.print(
            f"  ${budget_status['current_spend']:.4f} / ${budget_status['limit']:.2f}  (${budget_status['remaining']:.4f} remaining)")

        if not budget_status["within_budget"]:
            console.print(
                f"  [bold red]⚠ BUDGET EXCEEDED — Action: {budget_status.get('action', 'warn')}[/bold red]")
        elif budget_status.get("soft_warning"):
            console.print(f"  [yellow]⚠ Approaching budget limit[/yellow]")


@usage_app.command("daily")
def usage_daily(
    days: int = typer.Option(7, "--days", "-d", help="Number of days to show"),
) -> None:
    """Show day-by-day usage breakdown.

    Example:
        unclaude usage daily -d 14
    """
    from unclaude.usage import get_usage_tracker

    tracker = get_usage_tracker()
    breakdown = tracker.get_daily_breakdown(days=days)

    table = Table(title=f"Daily Usage (last {days} days)")
    table.add_column("Date", style="cyan")
    table.add_column("Requests", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Cost", justify="right", style="green")
    table.add_column("Models")

    for day in breakdown:
        models = ", ".join(day["models"].keys()) if day["models"] else "-"
        table.add_row(
            day["date"],
            str(day["requests"]),
            f"{day['tokens']:,}",
            f"${day['cost_usd']:.6f}",
            models[:40],
        )

    console.print(table)


@usage_app.command("models")
def usage_models(
    period: str = typer.Option("all", "--period", "-p",
                               help="Time period: today|week|month|all"),
) -> None:
    """Show per-model usage breakdown.

    Example:
        unclaude usage models -p week
    """
    from unclaude.usage import get_usage_tracker

    tracker = get_usage_tracker()
    models = tracker.get_model_breakdown(period=period)

    table = Table(title=f"Model Usage ({period})")
    table.add_column("Model", style="cyan")
    table.add_column("Provider")
    table.add_column("Requests", justify="right")
    table.add_column("Prompt", justify="right")
    table.add_column("Completion", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Cost", justify="right", style="green")

    for m in models:
        table.add_row(
            m["model"],
            m["provider"],
            str(m["requests"]),
            f"{m['prompt_tokens']:,}",
            f"{m['completion_tokens']:,}",
            f"{m['total_tokens']:,}",
            f"${m['cost_usd']:.6f}",
        )

    console.print(table)


@usage_app.command("budget")
def usage_budget(
    limit: float = typer.Option(None, "--set", "-s",
                                help="Set budget limit in USD"),
    period: str = typer.Option("daily", "--period", "-p",
                               help="Budget period: daily|weekly|monthly|total"),
    action: str = typer.Option("warn", "--action", "-a",
                               help="Over-budget action: warn|downgrade|block"),
    clear: bool = typer.Option(False, "--clear", help="Remove budget"),
) -> None:
    """Manage usage budget.

    Examples:
        unclaude usage budget --set 5.0            # $5/day budget
        unclaude usage budget --set 20 -p weekly   # $20/week
        unclaude usage budget --set 1 -a block     # Hard $1/day limit
        unclaude usage budget --clear              # Remove budget
        unclaude usage budget                      # Check budget status
    """
    from unclaude.usage import get_usage_tracker, BudgetPeriod, BudgetAction

    tracker = get_usage_tracker()

    if clear:
        tracker.clear_budget()
        console.print("[green]Budget cleared.[/green]")
        return

    if limit is not None:
        try:
            bp = BudgetPeriod(period)
        except ValueError:
            console.print(f"[red]Invalid period: {period}[/red]")
            raise typer.Exit(1)
        try:
            ba = BudgetAction(action)
        except ValueError:
            console.print(f"[red]Invalid action: {action}[/red]")
            raise typer.Exit(1)

        tracker.set_budget(limit_usd=limit, period=bp, action=ba)
        console.print(
            f"[green]Budget set: ${limit:.2f}/{period} (action: {action})[/green]")

    # Always show current status
    status = tracker.check_budget()
    if not status.get("budget_set"):
        console.print(
            "[dim]No budget configured. Use --set to create one.[/dim]")
        return

    pct = status["percentage"]
    color = "green" if pct < 50 else ("yellow" if pct < 80 else "red")
    console.print(f"\n[bold]Budget Status ({status['period']}):[/bold]")
    console.print(f"  Limit:     ${status['limit']:.2f}")
    console.print(
        f"  Spent:     [{color}]${status['current_spend']:.6f}[/{color}]")
    console.print(f"  Remaining: ${status['remaining']:.6f}")
    console.print(f"  Used:      [{color}]{pct:.1f}%[/{color}]")


@usage_app.command("export")
def usage_export() -> None:
    """Export all usage data to CSV."""
    from unclaude.usage import get_usage_tracker

    tracker = get_usage_tracker()
    filepath = tracker.export_csv()
    console.print(f"[green]Usage data exported to {filepath}[/green]")


# ─── Messaging Commands ─────────────────────────────────────────

@messaging_app.callback(invoke_without_command=True)
def messaging_default(ctx: typer.Context) -> None:
    """Show messaging integration status."""
    if ctx.invoked_subcommand is not None:
        return
    from unclaude.messaging import get_messenger

    messenger = get_messenger()
    status = messenger.get_status()

    console.print(Panel(
        "[bold]Messaging Integrations[/bold]\n\n"
        "Connect UnClaude to Telegram & WhatsApp to:\n"
        "• Submit tasks via chat messages\n"
        "• Get notified when tasks complete\n"
        "• Check daemon status on the go",
        title="💬 Messaging",
        border_style="blue",
    ))

    table = Table(show_header=True)
    table.add_column("Platform", style="cyan")
    table.add_column("Status")
    table.add_column("Chats", justify="right")
    table.add_column("Setup Command", style="dim")

    platforms = status.get("platforms", {})
    for name, info in platforms.items():
        configured = info.get("configured", False)
        chats = info.get("registered_chats", 0)
        status_text = "[green]✓ Connected[/green]" if configured else "[dim]Not configured[/dim]"
        table.add_row(
            name.title(),
            status_text,
            str(chats),
            f"unclaude messaging setup {name}",
        )

    console.print(table)


@messaging_app.command("setup")
def messaging_setup(
    platform: str = typer.Argument(...,
                                   help="Platform: telegram, whatsapp, or webhook"),
) -> None:
    """Set up a messaging integration interactively."""
    from unclaude.messaging import get_messenger

    messenger = get_messenger()

    if platform == "telegram":
        console.print(Panel(
            "[bold]Telegram Bot Setup[/bold]\n\n"
            "1. Open Telegram and message [cyan]@BotFather[/cyan]\n"
            "2. Send [cyan]/newbot[/cyan] and follow the prompts\n"
            "3. Copy the bot token (looks like [dim]123456:ABC-DEF...[/dim])",
            title="🤖 Telegram",
            border_style="blue",
        ))
        token = typer.prompt("Bot token")
        if not token or ":" not in token:
            console.print(
                "[red]Invalid token format. It should contain a colon (:)[/red]")
            raise typer.Exit(1)

        messenger.configure_telegram(token)

        # Verify
        import asyncio as _asyncio
        from unclaude.messaging import TelegramAdapter
        tg = TelegramAdapter(bot_token=token)
        bot_info = _asyncio.run(tg.get_me())
        _asyncio.run(tg.close())

        if bot_info:
            console.print(
                f"\n[green]✓ Connected![/green] Bot: @{bot_info.get('username', '?')}")
            console.print(
                "\n[dim]Next steps:[/dim]\n"
                "  1. Message your bot on Telegram\n"
                "  2. Send [cyan]/start[/cyan] to register for notifications\n"
                "  3. Use [cyan]/task <description>[/cyan] to submit tasks\n\n"
                "[dim]If using a public URL, the webhook is set automatically when you run the web server.[/dim]"
            )
        else:
            console.print(
                "[yellow]⚠ Could not verify token — check it and try again.[/yellow]")

    elif platform == "whatsapp":
        # Choose backend
        console.print(Panel(
            "[bold]WhatsApp Setup[/bold]\n\n"
            "Choose your WhatsApp integration:\n\n"
            "  [cyan]1. Green API[/cyan] (recommended)\n"
            "     Free, scan a QR code, done in 2 minutes\n"
            "     Sign up: [cyan]https://green-api.com[/cyan]\n\n"
            "  [cyan]2. Twilio[/cyan]\n"
            "     Paid API, more complex setup\n"
            "     Sign up: [cyan]https://twilio.com[/cyan]",
            title="📱 WhatsApp",
            border_style="green",
        ))
        backend = typer.prompt(
            "Which backend? (1=Green API, 2=Twilio)", default="1")

        if backend.strip() in ("1", "green", "green_api"):
            console.print(Panel(
                "[bold]Green API Setup[/bold]\n\n"
                "1. Go to [cyan]https://green-api.com[/cyan] and sign up (free tier)\n"
                "2. Create an instance and scan the QR code with your phone\n"
                "3. Copy your Instance ID and API Token from the dashboard",
                title="📱 WhatsApp via Green API",
                border_style="green",
            ))
            instance_id = typer.prompt("Instance ID")
            api_token = typer.prompt("API Token")
            owner_phone = typer.prompt(
                "Your phone number (with country code, e.g. +1234567890)",
                default="",
            )

            messenger.configure_whatsapp_green(
                instance_id, api_token, owner_phone)
            console.print(
                f"\n[green]✓ WhatsApp (Green API) configured![/green]")

            # Verify connection
            import asyncio as _asyncio
            from unclaude.messaging import WhatsAppGreenAPIAdapter
            wa = WhatsAppGreenAPIAdapter(
                instance_id=instance_id, api_token=api_token)
            state = _asyncio.run(wa.get_state())
            _asyncio.run(wa.close())

            if state:
                status = state.get("stateInstance", "unknown")
                console.print(f"  Instance state: [cyan]{status}[/cyan]")
                if status == "authorized":
                    console.print("  [green]✓ Phone is connected![/green]")
                else:
                    console.print(
                        "  [yellow]⚠ Scan the QR code in your Green API dashboard[/yellow]")

            console.print(
                "\n[dim]Next steps:[/dim]\n"
                "  1. Make sure your phone is connected (QR scanned)\n"
                "  2. Start the daemon: [cyan]unclaude agent start[/cyan]\n"
                "  3. WhatsApp polling starts automatically!\n"
                "  4. Send a message to your WhatsApp to chat with the AI"
            )
        else:
            console.print(Panel(
                "[bold]WhatsApp (Twilio) Setup[/bold]\n\n"
                "1. Sign up at [cyan]https://twilio.com[/cyan]\n"
                "2. Go to Console → Messaging → WhatsApp Sandbox\n"
                "3. Get your Account SID and Auth Token from the dashboard",
                title="📱 WhatsApp (Twilio)",
                border_style="green",
            ))
            account_sid = typer.prompt("Account SID")
            auth_token = typer.prompt("Auth Token", hide_input=True)
            from_number = typer.prompt(
                "WhatsApp From number",
                default="whatsapp:+14155238886",
            )

            messenger.configure_whatsapp(account_sid, auth_token, from_number)
            console.print(f"\n[green]✓ WhatsApp (Twilio) configured![/green]")
            console.print(
                "\n[dim]Next steps:[/dim]\n"
                "  1. Follow the Twilio sandbox instructions to link your phone\n"
                "  2. Set the Twilio webhook URL to your server's:\n"
                "     [cyan]/api/messaging/whatsapp/webhook[/cyan]\n"
                "  3. Send a message to test the integration"
            )

    elif platform == "webhook":
        console.print(Panel(
            "[bold]Webhook Setup[/bold]\n\n"
            "Send task completions to any webhook URL\n"
            "(Slack, Discord, custom endpoint, etc.)",
            title="🔗 Webhook",
            border_style="yellow",
        ))
        url = typer.prompt("Webhook URL")
        secret = typer.prompt("Webhook secret (optional)", default="")

        messenger.configure_webhook(url, secret)
        console.print(f"\n[green]✓ Webhook configured![/green] → {url}")

    else:
        console.print(f"[red]Unknown platform: {platform}[/red]")
        console.print("Available: telegram, whatsapp, webhook")
        raise typer.Exit(1)


@messaging_app.command("status")
def messaging_status() -> None:
    """Check the status of all messaging integrations."""
    from unclaude.messaging import get_messenger

    messenger = get_messenger()
    status = messenger.get_status()

    for name, info in status.get("platforms", {}).items():
        configured = info.get("configured", False)
        chats = info.get("registered_chats", 0)
        if configured:
            console.print(
                f"[green]✓[/green] {name.title()}: Connected ({chats} chat{'s' if chats != 1 else ''})")
        else:
            console.print(f"[dim]○[/dim] {name.title()}: Not configured")


@messaging_app.command("test")
def messaging_test(
    platform: str = typer.Argument(...,
                                   help="Platform to test: telegram, whatsapp, or webhook"),
    chat_id: str = typer.Argument(...,
                                  help="Chat ID / phone number to send test to"),
) -> None:
    """Send a test message to verify integration works."""
    from unclaude.messaging import get_messenger, Platform, OutgoingMessage
    import asyncio as _asyncio

    messenger = get_messenger()

    try:
        plat = Platform(platform)
    except ValueError:
        console.print(f"[red]Invalid platform: {platform}[/red]")
        raise typer.Exit(1)

    adapter = messenger.adapters.get(plat)
    if not adapter or not adapter.is_configured():
        console.print(
            f"[red]{platform} is not configured. Run: unclaude messaging setup {platform}[/red]")
        raise typer.Exit(1)

    success = _asyncio.run(adapter.send(OutgoingMessage(
        platform=plat,
        chat_id=chat_id,
        text="🤖 *UnClaude Test*\n\nThis is a test message from UnClaude. Your messaging integration is working!",
    )))

    if success:
        console.print(
            f"[green]✓ Test message sent to {chat_id} via {platform}![/green]")
    else:
        console.print(
            f"[red]✗ Failed to send test message. Check your credentials.[/red]")


@messaging_app.command("remove")
def messaging_remove(
    platform: str = typer.Argument(...,
                                   help="Platform to remove: telegram, whatsapp, or webhook"),
) -> None:
    """Remove a messaging integration."""
    from unclaude.messaging import get_messenger, Platform
    import asyncio as _asyncio

    messenger = get_messenger()

    try:
        plat = Platform(platform)
    except ValueError:
        console.print(f"[red]Invalid platform: {platform}[/red]")
        raise typer.Exit(1)

    if plat in messenger.adapters:
        adapter = messenger.adapters.pop(plat)
        if hasattr(adapter, "close"):
            _asyncio.run(adapter.close())
        messenger._registered_chats[plat] = set()
        messenger._save_config()
        console.print(
            f"[green]✓ {platform.title()} integration removed.[/green]")
    else:
        console.print(f"[dim]{platform.title()} was not configured.[/dim]")


@messaging_app.command("listen")
def messaging_listen() -> None:
    """Start listening for Telegram messages (long-polling, no public URL needed).

    This is the easiest way to use UnClaude via Telegram:
      1. Create a bot with @BotFather
      2. Run: unclaude messaging setup telegram
      3. Run: unclaude messaging listen
      4. Message your bot on Telegram — it responds!

    Press Ctrl+C to stop.
    """
    from unclaude.messaging import get_messenger, Platform, TelegramAdapter, create_chat_handler
    import asyncio as _asyncio

    messenger = get_messenger()
    tg = messenger.adapters.get(Platform.TELEGRAM)

    if not tg or not isinstance(tg, TelegramAdapter) or not tg.is_configured():
        console.print("[red]Telegram not configured.[/red]")
        console.print(
            "Run [bold]unclaude messaging setup telegram[/bold] first.")
        raise typer.Exit(1)

    async def _run() -> None:
        # Wire up the LLM chat handler so free-form messages get AI responses
        chat_handler = create_chat_handler()
        messenger.set_handler(chat_handler)

        bot_info = await tg.get_me()
        bot_name = bot_info.get("username", "unknown")
        console.print(f"[bold green]🤖 Listening as @{bot_name}[/bold green]")
        console.print(
            "[dim]AI chat enabled — send any message to talk to the LLM[/dim]")
        console.print(
            "[dim]Commands: /help /task /status /usage /jobs /clear[/dim]")
        console.print(
            "[dim]Press Ctrl+C to stop.[/dim]\n")

        stop = _asyncio.Event()

        def _handle_signal() -> None:
            stop.set()

        loop = _asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _handle_signal)

        await tg.start_polling(messenger, shutdown_event=stop)
        console.print("\n[dim]Stopped.[/dim]")

    _asyncio.run(_run())


# ─── Swarm Command ──────────────────────────────────────────────

@app.command()
def swarm(
    task: str = typer.Argument(...,
                               help="Complex task to execute with multiple agents"),
    max_agents: int = typer.Option(
        3, "--max-agents", "-n", help="Max parallel agents"),
    no_review: bool = typer.Option(
        False, "--no-review", help="Skip the review phase"),
) -> None:
    """Execute a complex task using a swarm of specialized agents.

    The swarm orchestrator:
    1. Plans and breaks down the task into subtasks
    2. Assigns specialized agents (coder, tester, reviewer, etc.)
    3. Executes subtasks in parallel where possible
    4. Reviews the combined result

    Examples:
        unclaude swarm "build user auth with JWT, tests, and docs"
        unclaude swarm "refactor the database layer to use SQLAlchemy"
        unclaude swarm "add CI/CD pipeline with GitHub Actions" -n 4
    """
    from unclaude.autonomous.swarm import SwarmOrchestrator

    orchestrator = SwarmOrchestrator(
        project_path=Path.cwd(),
        max_parallel=max_agents,
        enable_review=not no_review,
    )

    result = asyncio.run(orchestrator.execute(task))

    if result.success:
        console.print(f"\n[green]Swarm completed successfully![/green]")
    else:
        console.print(
            f"\n[yellow]Swarm completed with some failures.[/yellow]")

    console.print(f"[dim]Files modified: {len(result.files_modified)}[/dim]")
    console.print(f"[dim]Total time: {result.total_time:.1f}s[/dim]")


# ─── Scan / Discover Command ────────────────────────────────────

@app.command()
def scan() -> None:
    """Discover project capabilities, frameworks, and available commands.

    Scans your project for:
    - Languages and frameworks (package.json, pyproject.toml, etc.)
    - Available commands (Makefile, npm scripts, etc.)
    - Docker, CI/CD, tests, docs
    - Project structure and conventions

    The discovered profile is used by the autonomous agent to know
    what tools are available without being told.
    """
    from unclaude.autonomous.discovery import SkillDiscovery

    discovery = SkillDiscovery(Path.cwd())
    profile = asyncio.run(discovery.scan())

    # Show results
    console.print(Panel(
        f"[bold]{profile.summary()}[/bold]",
        title="🔍 Project Profile",
        border_style="cyan",
    ))

    # Languages
    if profile.languages:
        table = Table(title="Languages")
        table.add_column("Language")
        table.add_column("Files", justify="right")
        lang_ext = {
            "Python": ".py", "JavaScript": ".js", "TypeScript": ".ts",
            "Rust": ".rs", "Go": ".go", "Java": ".java", "Ruby": ".rb",
        }
        for lang in profile.languages:
            ext = lang_ext.get(lang, "")
            count = profile.file_counts.get(ext, 0)
            table.add_row(lang, str(count))
        console.print(table)

    # Frameworks
    if profile.frameworks:
        table = Table(title="Frameworks & Libraries")
        table.add_column("Name", style="cyan")
        table.add_column("Version")
        table.add_column("Category")
        for fw in profile.frameworks:
            table.add_row(fw.name, fw.version or "-", fw.category)
        console.print(table)

    # Skills
    if profile.skills:
        table = Table(title="Available Commands")
        table.add_column("Name", style="green")
        table.add_column("Command")
        table.add_column("Category")
        table.add_column("Source", style="dim")
        for skill in profile.skills:
            table.add_row(skill.name, skill.command,
                          skill.category, skill.source)
        console.print(table)

    # Features
    features = []
    if profile.has_docker:
        features.append("🐳 Docker")
    if profile.has_ci:
        features.append("⚡ CI/CD")
    if profile.has_tests:
        features.append("🧪 Tests")
    if profile.has_docs:
        features.append("📖 Docs")
    if profile.has_monorepo:
        features.append("📦 Monorepo")
    if features:
        console.print(f"\n[bold]Features:[/bold] {' | '.join(features)}")


if __name__ == "__main__":
    app()
