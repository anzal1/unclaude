"""CLI interface for UnClaude."""

import asyncio
import os
import warnings
from pathlib import Path

# Suppress noisy warnings from LiteLLM
warnings.filterwarnings("ignore", message="Pydantic serializer warnings")
warnings.filterwarnings("ignore", message="coroutine.*was never awaited")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="litellm")
warnings.filterwarnings("ignore", message="Enable tracemalloc")

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from unclaude import __version__
from unclaude.agent import AgentLoop
from unclaude.config import get_settings, save_config, ProviderConfig
from unclaude.providers import Provider


app = typer.Typer(
    name="unclaude",
    help="Open Source Model-Independent Claude Code Alternative",
    no_args_is_help=True,
)
console = Console()


def print_banner() -> None:
    """Print the UnClaude banner."""
    console.print(
        Panel(
            "[bold cyan]UnClaude[/bold cyan] - Open Source AI Coding Assistant\n"
            f"Version {__version__} | Model-Independent | Your Data, Your Choice",
            title="🤖",
            border_style="cyan",
        )
    )


@app.command()
def chat(
    message: str = typer.Argument(None, help="Initial message to send"),
    provider: str = typer.Option(None, "--provider", "-p", help="LLM provider to use"),
    model: str = typer.Option(None, "--model", "-m", help="Model to use"),
    headless: bool = typer.Option(False, "--headless", "-H", help="Run in headless mode (no interactive prompts, for CI/CD)"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output response as JSON"),
) -> None:
    """Start an interactive chat session with UnClaude."""
    import json as json_lib
    from unclaude.onboarding import ensure_configured, get_provider_api_key, PROVIDERS
    
    # Ensure configured (run onboarding if first time) - skip in headless mode
    if not headless:
        config = ensure_configured()
    else:
        # In headless mode, load config without interactive prompts
        from unclaude.config import get_settings
        settings = get_settings()
        config = {
            "default_provider": settings.default_provider,
            "providers": {k: {"model": v.model} for k, v in settings.providers.items()},
        }
    
    if not headless:
        print_banner()
    
    # Determine provider and model
    use_provider = provider or config.get("default_provider", "gemini")
    provider_config = config.get("providers", {}).get(use_provider, {})
    use_model = model or provider_config.get("model")
    
    # Load API key and set environment variable
    api_key = get_provider_api_key(use_provider) if not headless else os.environ.get(f"{use_provider.upper()}_API_KEY")
    if api_key:
        provider_info = PROVIDERS.get(use_provider, {})
        env_var = provider_info.get("env_var")
        if env_var:
            os.environ[env_var] = api_key
    
    # Create provider
    try:
        from unclaude.providers.llm import Provider as LLMProvider
        llm_provider = LLMProvider(use_provider)
        if use_model:
            llm_provider.config.model = use_model
    except Exception as e:
        if json_output:
            print(json_lib.dumps({"error": str(e), "success": False}))
        else:
            console.print(f"[red]Error creating provider: {e}[/red]")
        raise typer.Exit(1)

    if not headless:
        console.print(f"[dim]Provider: {use_provider} | Model: {use_model or 'default'}[/dim]")
        console.print(f"[dim]Working directory: {os.getcwd()}[/dim]")
        console.print("[dim]Type 'exit' or 'quit' to end, '/clear' to reset, '/help' for commands[/dim]\n")

    agent = AgentLoop(provider=llm_provider)

    async def run_chat() -> None:
        # Handle initial message if provided
        if message:
            if not headless:
                console.print(f"[bold]You:[/bold] {message}\n")
            response = await agent.run(message)
            
            if json_output:
                print(json_lib.dumps({"response": response, "success": True}))
            elif not headless:
                console.print(Panel(Markdown(response), title="UnClaude", border_style="green"))
                console.print()
            else:
                print(response)
        
        # In headless mode with a message, exit after response
        if headless and message:
            return

        # Interactive loop (only in non-headless mode)
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
                console.print(
                    Panel(
                        "**Commands:**\n"
                        "- `/clear` - Clear conversation history\n"
                        "- `/help` - Show this help message\n"
                        "- `exit` or `quit` - End the session\n\n"
                        "**Tips:**\n"
                        "- Ask UnClaude to read files before editing\n"
                        "- Be specific about what you want to accomplish\n"
                        "- Use natural language to describe coding tasks",
                        title="Help",
                    )
                )
                continue

            console.print()
            try:
                response = await agent.run(user_input)
                if response:
                    console.print(Panel(Markdown(response), title="UnClaude", border_style="green"))
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
            console.print()

    asyncio.run(run_chat())


@app.command()
def config(
    set_provider: str = typer.Option(None, "--set-provider", help="Set the default provider"),
    show: bool = typer.Option(False, "--show", help="Show current configuration"),
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
        console.print(f"[green]Default provider set to: {set_provider}[/green]")
        return

    # Interactive config
    console.print("[yellow]Interactive configuration not yet implemented.[/yellow]")
    console.print("Use environment variables or edit ~/.unclaude/config.yaml directly.")


@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Directory to initialize"),
) -> None:
    """Initialize UnClaude in a project directory."""
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
    console.print("Edit this file to customize UnClaude's behavior for your project.")


@app.command()
def version() -> None:
    """Show the UnClaude version."""
    console.print(f"UnClaude version {__version__}")


@app.command()
def login() -> None:
    """Re-run the onboarding setup to change provider or API key."""
    from unclaude.onboarding import run_onboarding
    run_onboarding()


@app.command()
def ralph(
    task: str = typer.Argument(..., help="The task to complete autonomously"),
    max_iterations: int = typer.Option(50, "--max-iterations", "-i", help="Maximum iterations"),
    max_cost: float = typer.Option(10.0, "--max-cost", "-c", help="Maximum cost in USD"),
    feedback: list[str] = typer.Option(["npm test"], "--feedback", "-f", help="Feedback commands"),
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
    console.print("[bold cyan]Ralph Wiggum Mode[/bold cyan] - Autonomous Iteration\n")
    
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
        
    console.print(f"[dim]Provider: {use_provider} | Model: {use_model or 'default'}[/dim]")

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
            console.print(Panel("[bold yellow]No TASK.md found. Invoking Planner Agent...[/bold yellow]", title="Orchestrator"))
            from unclaude.agent.planner import PlannerAgent
            planner = PlannerAgent(provider=llm_provider)
            # Run planner
            await planner.run(f"Create a detailed execution plan for: {task}")
            console.print("[bold green]✓ Plan created![/bold green]")
            
        result = await ralph_mode.run(task)

        console.print("\n" + "=" * 50)
        if result.success:
            console.print("[bold green]✓ Task completed successfully![/bold green]")
        else:
            console.print(f"[bold red]✗ Task did not complete: {result.error}[/bold red]")

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
        
    console.print(Panel(f"[bold cyan]Planning Task:[/bold cyan] {task}", title="Planner Agent"))
    
    planner = PlannerAgent(provider=llm_provider)
    
    async def run_plan():
        response = await planner.run(f"Create a plan for: {task}")
        console.print(Panel(Markdown(response), title="Plan Generated", border_style="green"))
        
    asyncio.run(run_plan())


@app.command()
def plugins(
    list_plugins: bool = typer.Option(False, "--list", "-l", help="List installed plugins"),
    create: str = typer.Option(None, "--create", "-c", help="Create a new plugin template"),
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
            console.print(f"  📦 [cyan]{plugin.name}[/cyan] v{plugin.manifest.version}")
            console.print(f"     {plugin.manifest.description}")
            console.print(f"     Tools: {len(plugin.tools)}, Hooks: {len(plugin.hooks)}")
        return

    if create:
        plugin_path = plugin_manager.plugins_dir / create
        if plugin_path.exists():
            console.print(f"[red]Plugin '{create}' already exists.[/red]")
            return

        create_plugin_template(create, plugin_path)
        console.print(f"[green]Created plugin template at {plugin_path}[/green]")
        return

    console.print("Use --list to see plugins or --create to create a new one.")


@app.command()
def skills(
    list_skills: bool = typer.Option(False, "--list", "-l", help="List available skills"),
    run_skill: str = typer.Option(None, "--run", "-r", help="Run a skill by name"),
    create: str = typer.Option(None, "--create", "-c", help="Create a new skill template"),
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
        console.print(f"[dim]Provider: {use_provider} | Model: {use_model or 'default'}[/dim]\n")

        agent = AgentLoop(provider=llm_provider)

        async def run_skill_async() -> None:
            response = await agent.run(prompt)
            console.print(Panel(response, title=f"Skill: {run_skill}", border_style="green"))

        asyncio.run(run_skill_async())
        return

    console.print("Use --list to see skills, --run to execute one, or --create to make a new one.")


@app.command()
def mcp(
    list_servers: bool = typer.Option(False, "--list", "-l", help="List configured MCP servers"),
    init_config: bool = typer.Option(False, "--init", help="Create MCP config template"),
) -> None:
    """Manage MCP (Model Context Protocol) servers."""
    from unclaude.mcp import MCPClient, create_mcp_config_template

    client = MCPClient()

    if init_config:
        if client.config_path.exists():
            console.print(f"[yellow]MCP config already exists at {client.config_path}[/yellow]")
            return

        client.config_path.parent.mkdir(parents=True, exist_ok=True)
        client.config_path.write_text(create_mcp_config_template())
        console.print(f"[green]Created MCP config at {client.config_path}[/green]")
        return

    if list_servers:
        configs = client._load_config()
        if not configs:
            console.print("[yellow]No MCP servers configured.[/yellow]")
            console.print(f"Config file: {client.config_path}")
            console.print("Run 'unclaude mcp --init' to create a config template.")
            return

        console.print("[bold]Configured MCP Servers:[/bold]\n")
        for name, config in configs.items():
            console.print(f"  🔌 [cyan]{name}[/cyan]")
            console.print(f"     Command: {config.command} {' '.join(config.args)}")
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
            console.print(f"  [{status_color}]{job.job_id}[/{status_color}] - {job.task[:50]}... ({job.status})")


@app.command()
def web(
    port: int = typer.Option(8765, "--port", "-p", help="Port to run the dashboard on"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open browser automatically"),
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


if __name__ == "__main__":
    app()
