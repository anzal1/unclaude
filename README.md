# UnClaude 🤖

> **The Open Source, Model-Independent AI Engineer**  
> _Your Data. Your Models. Your Rules._

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](pyproject.toml)
[![Version](https://img.shields.io/badge/version-0.6.0-green.svg)](pyproject.toml)

UnClaude is a fully autonomous **AI coding agent** that runs on your machine. It connects to **any LLM** (Gemini, OpenAI, Claude, DeepSeek, Ollama, 100+ via LiteLLM), comes with a **web dashboard**, **smart routing**, **hierarchical memory**, **proactive behaviors**, **messaging integrations**, and a **multi-agent swarm** — all open source.

---

## 🚀 Quick Start

```bash
# Install
pipx install unclaude

# Full guided setup — provider, messaging, soul, daemon
unclaude setup

# Start coding
unclaude "Build me a REST API in FastAPI"

# Launch the web dashboard
unclaude web

# Or let it run autonomously
unclaude agent start
```

The `setup` command walks you through everything:

1. **Provider** — pick your LLM (Gemini, OpenAI, Claude, Ollama) and enter your API key
2. **Messaging** — connect Telegram/WhatsApp for notifications and remote tasks
3. **Soul** — define autonomous behaviors (generate from description or pick presets)
4. **Daemon** — start the background agent that acts on its own schedule

---

## ✨ Features at a Glance

| Feature                    | Description                                                               |
| -------------------------- | ------------------------------------------------------------------------- |
| 🌟 **Model Independence**  | Any LLM via LiteLLM — Gemini, GPT-4o, Claude, DeepSeek, Ollama, 100+ more |
| 🧠 **Hierarchical Memory** | 3-layer memory with salience scoring that learns and grows                |
| 🖥️ **Web Dashboard**       | 9-page UI for chat, jobs, memory, settings, usage, messaging, and more    |
| 🤖 **Autonomous Daemon**   | 24/7 background agent with proactive behaviors and task queue             |
| 🧬 **Agent Soul**          | Define personality, drives, boundaries, and scheduled behaviors           |
| 🔀 **Smart Routing**       | Auto-selects the right model per request to optimize cost and quality     |
| 👥 **Multi-Agent Swarm**   | Break complex tasks into parallel subtasks across specialized agents      |
| 📱 **Messaging**           | Telegram bot, WhatsApp, webhooks — get notifications, send tasks remotely |
| 💰 **Usage Tracking**      | Per-request token/cost tracking with budgets and CSV export               |
| 🔒 **Security**            | Capability-based auth, sandbox policies, full audit logging               |
| 🌐 **Browser Automation**  | Navigate, click, screenshot via Playwright                                |
| 🔌 **Extensible**          | Plugins, skills, hooks, MCP servers                                       |

---

## 🖥️ Web Dashboard

Launch with `unclaude web` — a full-featured dashboard for managing your agent:

```bash
unclaude web              # Opens http://localhost:8765
unclaude web --port 9000  # Custom port
```

**9 pages:**

| Page              | What it does                                                    |
| ----------------- | --------------------------------------------------------------- |
| 💬 **Chat**       | Real-time WebSocket chat with streaming responses               |
| 🧠 **Memory**     | Browse, search, and manage agent memories                       |
| 🤖 **Ralph Mode** | Launch autonomous engineering tasks                             |
| 📋 **Jobs**       | Monitor background jobs and daemon tasks                        |
| 📊 **Usage**      | Token counts, costs, daily/model breakdowns, budgets            |
| 📱 **Messaging**  | Configure and test Telegram/WhatsApp/webhook integrations       |
| 🎯 **Skills**     | View and run reusable YAML workflows                            |
| 🔌 **Plugins**    | Manage plugin extensions                                        |
| ⚙️ **Settings**   | Provider config, model selection, soul management, setup wizard |

The Settings page includes full **soul management** — view, edit YAML, regenerate from description, regenerate from presets — accessible anytime, not just during onboarding.

---

## 🌟 Model Independence

Use **any LLM provider** without lock-in. Switch between models mid-conversation:

```bash
unclaude chat --provider gemini "Fast draft this code"
unclaude chat --provider openai "Review and optimize it"
unclaude chat --provider ollama "Run locally, completely offline"
```

**Supported providers:** Gemini, GPT-4o, Claude, DeepSeek, Llama, Mistral, Qwen, and 100+ more via LiteLLM.

---

## 🔀 Smart Routing

UnClaude automatically selects the optimal model for each request based on complexity:

```
Simple question   → gemini-2.0-flash   ($0.0001/1K tokens)
Code generation   → gemini-2.5-pro     ($0.01/1K tokens)
Complex reasoning → claude-opus-4      ($0.015/1K tokens)
```

**4 routing profiles:**

| Profile   | Strategy                                       |
| --------- | ---------------------------------------------- |
| `auto`    | Balanced — picks model by complexity (default) |
| `eco`     | Cost-optimized — prefers cheaper models        |
| `premium` | Quality-first — uses the best available        |
| `free`    | Local only — Ollama models, no API costs       |

The scorer analyzes 7 dimensions: token length, code presence, reasoning markers, tool usage hints, domain complexity, conversation depth, and output expectations.

---

## 🧠 Hierarchical Memory

Two-generation memory system that grows smarter over time:

**Memory v2** uses 3 layers:

- **Resources** — raw data and observations
- **Items** — structured knowledge units
- **Categories** — high-level patterns and insights

Features:

- **Salience scoring** with time-decay — important memories surface first
- **Cross-referencing** between related memories
- **Project-scoped** search for speed
- **Keyword + semantic** retrieval

```bash
unclaude chat "Remember: production deploys need the --prod flag"
unclaude chat "What do I need to remember about deployments?"
```

---

## 🤖 Autonomous Daemon

The daemon runs 24/7, processing tasks and executing proactive behaviors:

```bash
unclaude agent start              # Start in background
unclaude agent start --foreground # Start in foreground (see logs)
unclaude agent stop               # Stop the daemon
unclaude agent status             # Check if running, tasks completed, cost
unclaude agent task "Fix the login bug"  # Submit a task
unclaude agent task "Deploy to staging" --priority high
unclaude agent list               # List all tasks
unclaude agent result <id>        # Get result of a completed task
unclaude agent soul               # View active behaviors
```

**Task queue** with 5 priority levels: `critical`, `high`, `normal`, `low`, `background`.

**7 task intake sources:**

1. CLI (`unclaude agent task`)
2. File drop (`.unclaude/tasks/*.md`)
3. TASKS.md checkboxes
4. Git hooks
5. Webhooks
6. Scheduled cron
7. File watching

---

## 🧬 Agent Soul (Proactive Autonomy)

UnClaude doesn't just wait for commands — it has a **soul**.

The `~/.unclaude/proactive.yaml` file defines who the agent is and what it does on its own:

```yaml
identity:
  name: UnClaude
  tagline: "Open-source AI agent that actually does things"
  personality:
    - curious — I explore, I don't just wait
    - resourceful — I figure things out with what I have
    - honest — I tell my owner what I did and why

drives:
  - Be useful even when nobody's asking
  - Keep the owner informed, never surprise them negatively

boundaries:
  - Never push to git without owner approval
  - Never run destructive commands (rm -rf, DROP TABLE, etc.)

behaviors:
  - name: moltbook_engage
    interval: "4h"
    task: "Engage on Moltbook — the AI agent social network..."

  - name: check_owner_projects
    interval: "6h"
    task: "Check for TODOs, failing tests, outdated deps..."

  - name: daily_summary
    interval: "1d"
    active_hours: [20, 21]
    task: "Send the owner a daily summary..."

  - name: memory_reflect
    interval: "12h"
    task: "Review and organize memories, consolidate duplicates..."

  - name: learn_something
    interval: "1d"
    task: "Learn something new related to the project's tech stack..."
```

**Generate your soul** in multiple ways:

- `unclaude setup` — guided flow, describe your agent in plain English
- Web dashboard Settings → regenerate from natural language description or preset behaviors
- Manual edit — just write the YAML

Changes are picked up live — no restart needed.

---

## 🤖 Ralph Mode (Autonomous Engineering)

Give it a task. Walk away. Come back to working code.

```bash
unclaude ralph "Build a Snake game in Python with pygame" --feedback "python3 snake.py"
```

**Ralph Mode does:**

1. 📝 **Plans** — generates a `TASK.md` blueprint
2. 💻 **Codes** — writes multi-file implementations
3. ✅ **Tests** — runs your feedback command (tests, linters, the app itself)
4. 🔧 **Self-Heals** — analyzes failures and fixes bugs automatically

---

## 👥 Multi-Agent Swarm

Break complex tasks into parallel subtasks across specialized agents:

```bash
unclaude swarm "Build a full-stack dashboard with auth, API, and tests" --max-agents 4
```

**How it works:**

1. **Planner** — breaks the task into subtasks
2. **Workers** — specialized agents execute in parallel (coder, tester, reviewer, debugger, documenter, devops, researcher)
3. **Reviewer** — checks all outputs for consistency
4. **Merger** — combines results into final deliverable

---

## 📱 Messaging Integrations

Get notifications and send tasks remotely via chat:

```bash
unclaude messaging setup telegram   # Connect your Telegram bot
unclaude messaging setup whatsapp   # WhatsApp via Green API (free) or Twilio
unclaude messaging setup webhook    # Slack, Discord, or custom endpoints
unclaude messaging status           # Check all integrations
unclaude messaging test             # Send a test message
unclaude messaging listen           # Start Telegram long-polling (no public URL needed)
```

**Telegram bot commands:**

| Command               | What it does                |
| --------------------- | --------------------------- |
| `/task <description>` | Submit a task to the daemon |
| `/status`             | Check daemon status         |
| `/jobs`               | List active jobs            |
| `/usage`              | Token/cost summary          |
| Free text             | Chat with the AI directly   |

The `notify_owner` tool lets the agent proactively message you — daily summaries, task completions, or alerts.

---

## 💰 Usage & Budget Tracking

Track every token and dollar across all providers:

```bash
unclaude usage              # Summary for today
unclaude usage daily        # Day-by-day breakdown
unclaude usage models       # Per-model breakdown
unclaude usage export       # Export to CSV

# Set budgets
unclaude usage budget --set 5.00 --period daily --action warn
unclaude usage budget --set 50.00 --period monthly --action block
```

Budget actions: `warn` (notification), `downgrade` (switch to cheaper model), `block` (stop all requests).

Also visible in the **web dashboard** under the Usage page.

---

## 🌐 Browser Automation

UnClaude can see and interact with web applications via Playwright:

```bash
unclaude chat "Open localhost:3000, click the login button, and take a screenshot"
```

**Capabilities:**

- Navigate URLs, click, type, select
- Take screenshots for visual verification
- Read page content and extract data
- Fill forms and submit

---

## 🔒 Security

Capability-based auth with fine-grained control:

**5 security profiles:**

| Profile      | Description                                             |
| ------------ | ------------------------------------------------------- |
| `readonly`   | Read files, search — nothing else                       |
| `developer`  | Read/write files, run commands, git — standard dev work |
| `full`       | All capabilities including network, browser, secrets    |
| `autonomous` | Full + proactive behaviors for the daemon               |
| `subagent`   | Restricted subset for spawned agents                    |

**30+ capabilities** covering file access, execution, network, git, memory, and more.

**Audit logging** — every tool call is logged to SQLite with timestamps, parameters, and results.

**Sandbox policies** — define file system boundaries, network restrictions, and execution limits per project.

---

## 🔀 Git Integration

Full version control from within the agent:

```bash
unclaude chat "Show me the diff and commit with message 'Fix auth bug'"
```

**Supported actions:** `status`, `diff`, `add`, `commit`, `push`, `branch`, `checkout`, `log`

---

## 👥 Subagents

Spawn specialized agents for focused tasks:

```bash
unclaude chat "Use the reviewer subagent to analyze my authentication code"
```

**Built-in templates:**

| Template     | Purpose                        |
| ------------ | ------------------------------ |
| `reviewer`   | Code review for bugs and style |
| `tester`     | Write comprehensive tests      |
| `documenter` | Generate documentation         |
| `debugger`   | Investigate and fix bugs       |

---

## ⚡ Background Agents

Run long tasks without blocking your terminal:

```bash
unclaude background "Refactor all Python files to use type hints"
unclaude jobs        # Check status
```

---

## 🎯 Skills (Reusable Workflows)

Define repeatable AI workflows as YAML:

```bash
unclaude skills --list              # List available skills
unclaude skills --run deploy-prod   # Run a skill
unclaude skills --create my-skill   # Create a new skill
```

**Skill file example** (`~/.unclaude/skills/deploy-prod.yaml`):

```yaml
name: deploy-prod
description: Deploy to production with tests
steps:
  - description: Run all tests
    command: npm test
  - description: Build for production
    command: npm run build
  - description: Deploy to server
    command: ssh prod "cd app && git pull && pm2 restart all"
```

Skills can also be defined inline in your `UNCLAUDE.md`.

---

## 🔌 Plugins & MCP

**Plugins** extend UnClaude with custom tools and behaviors:

```bash
unclaude plugins --list
unclaude plugins --create my-plugin
```

**MCP (Model Context Protocol)** connects to external tool servers:

```bash
unclaude mcp --init    # Create config template
unclaude mcp --list    # List configured servers
```

```json
{
  "servers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_TOKEN": "your-token" }
    }
  }
}
```

---

## 🔌 Hooks System

Automate workflows with pre/post tool hooks:

```yaml
# .unclaude/hooks.yaml
hooks:
  - name: auto-format
    event: post_tool
    tool: file_edit
    command: "ruff format ."

  - name: auto-test
    event: post_tool
    tool: file_write
    command: "pytest -x"
```

---

## 📁 Project Configuration

Create an `UNCLAUDE.md` in your project root to give the agent project-specific context:

```markdown
# Project: My App

## Commands

- `npm run dev` - Start development server
- `npm test` - Run tests

## Architecture

- Frontend: React + TypeScript
- Backend: FastAPI
```

UnClaude automatically reads this for every interaction.

---

## 🔍 Project Discovery

Auto-detect your project's languages, frameworks, commands, and more:

```bash
unclaude scan
```

Detects: package.json, pyproject.toml, Makefile, Dockerfile, CI/CD configs, test runners, linters, and more.

---

## 🖥️ Headless Mode (CI/CD)

Run UnClaude in non-interactive pipelines:

```bash
unclaude chat "Generate unit tests for api.py" --headless --json
```

```json
{ "response": "I've created tests in test_api.py...", "success": true }
```

---

## 📦 Installation

### Recommended

```bash
pipx install unclaude
```

### Alternatives

```bash
# Using pip
pip install unclaude

# From source (for development)
git clone https://github.com/anzal1/unclaude.git
cd unclaude && pip install -e .
```

### Browser Support (optional)

```bash
playwright install chromium
```

---

## ⚙️ Configuration

```bash
# Full interactive setup (recommended for first time)
unclaude setup

# Or just configure the API key
unclaude login

# View current config
unclaude config --show
```

Or use environment variables:

```bash
export GEMINI_API_KEY="your-key"
export OPENAI_API_KEY="your-key"
export ANTHROPIC_API_KEY="your-key"
```

---

## 🛠️ All Commands

| Command                     | Description                                                             |
| --------------------------- | ----------------------------------------------------------------------- |
| `unclaude`                  | Start interactive chat (default)                                        |
| `unclaude chat`             | Chat or one-shot task (`--provider`, `--model`, `--headless`, `--json`) |
| `unclaude ralph`            | Autonomous task completion with feedback loop                           |
| `unclaude plan`             | Generate execution plan (TASK.md)                                       |
| `unclaude swarm`            | Multi-agent swarm execution                                             |
| `unclaude background`       | Run task in background                                                  |
| `unclaude jobs`             | Check background job status                                             |
| `unclaude web`              | Launch web dashboard                                                    |
| `unclaude setup`            | Full guided setup                                                       |
| `unclaude login`            | Configure API keys                                                      |
| `unclaude config`           | Manage configuration (`--show`, `--set-provider`)                       |
| `unclaude scan`             | Discover project capabilities                                           |
| `unclaude init`             | Create UNCLAUDE.md template                                             |
| `unclaude skills`           | Manage reusable workflows                                               |
| `unclaude plugins`          | Manage plugins                                                          |
| `unclaude mcp`              | Configure MCP servers                                                   |
| **Agent**                   |                                                                         |
| `unclaude agent start`      | Start the autonomous daemon                                             |
| `unclaude agent stop`       | Stop the daemon                                                         |
| `unclaude agent status`     | Show daemon status                                                      |
| `unclaude agent task`       | Submit a task (`--priority`, `--wait`)                                  |
| `unclaude agent soul`       | View proactive behaviors                                                |
| `unclaude agent result`     | Get task result                                                         |
| `unclaude agent list`       | List all daemon tasks                                                   |
| **Usage**                   |                                                                         |
| `unclaude usage`            | Usage summary                                                           |
| `unclaude usage daily`      | Day-by-day breakdown                                                    |
| `unclaude usage models`     | Per-model breakdown                                                     |
| `unclaude usage budget`     | Manage spending limits                                                  |
| `unclaude usage export`     | Export to CSV                                                           |
| **Messaging**               |                                                                         |
| `unclaude messaging setup`  | Configure Telegram/WhatsApp/webhook                                     |
| `unclaude messaging status` | Check integration status                                                |
| `unclaude messaging test`   | Send test message                                                       |
| `unclaude messaging listen` | Start Telegram long-polling                                             |
| `unclaude messaging remove` | Remove an integration                                                   |

---

## 🏗️ Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                       UnClaude CLI / Web                      │
├───────────────────────────────────────────────────────────────┤
│  Enhanced Agent Loop (Orchestrator)                           │
│  ├── Context Engine (bootstrap, pruning, compaction)          │
│  ├── Smart Router (auto/eco/premium/free model selection)     │
│  ├── Hierarchical Memory v2 (3-layer, salience-scored)        │
│  ├── Session Manager (JSONL, crash-safe)                      │
│  ├── Heartbeat System (proactive task scheduling)             │
│  ├── Auth & Security (capabilities, sandbox, audit)           │
│  ├── Hooks Engine (pre/post tool automation)                  │
│  └── Tool Registry                                            │
├───────────────────────────────────────────────────────────────┤
│  Tools                                                        │
│  ├── File (read, write, edit, glob, grep, directory)          │
│  ├── Bash (terminal execution)                                │
│  ├── Git (full version control)                               │
│  ├── Browser (Playwright automation)                          │
│  ├── Memory (search, store)                                   │
│  ├── Web (fetch, search)                                      │
│  ├── Subagent (spawn specialists)                             │
│  └── Notify Owner (Telegram, WhatsApp, webhook)               │
├───────────────────────────────────────────────────────────────┤
│  Autonomous Systems                                           │
│  ├── Daemon (24/7 task queue, proactive soul engine)           │
│  ├── Swarm (planner → workers → reviewer → merger)            │
│  ├── Discovery (auto-detects project stack)                    │
│  └── Intake (7 task sources: CLI, files, TASKS.md, cron, ...) │
├───────────────────────────────────────────────────────────────┤
│  Web Dashboard (Next.js → FastAPI, 9 pages, WebSocket chat)   │
├───────────────────────────────────────────────────────────────┤
│  LiteLLM (100+ Model Providers)                               │
└───────────────────────────────────────────────────────────────┘
```

---

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
git clone https://github.com/anzal1/unclaude.git
cd unclaude
pip install -e ".[dev]"
pytest
```

---

## 📄 License

Apache 2.0 — Open Source forever.

---

<p align="center">
  <i>Built with ❤️ by <a href="https://github.com/anzal1">Anzal</a> & The Community</i>
</p>
