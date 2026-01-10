# UnClaude 🤖

> **The Open Source, Model-Independent AI Engineer**  
> _Your Data. Your Models. Your Rules._

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](pyproject.toml)
[![Version](https://img.shields.io/badge/version-0.2.0-green.svg)](pyproject.toml)

UnClaude is a powerful **Agentic Coding Assistant** that runs entirely on your machine. It connects to **any LLM** (Gemini, OpenAI, Anthropic, DeepSeek, Ollama) and provides a fully autonomous pair programmer with memory, browser automation, and multi-agent capabilities.

---

## 🚀 Quick Start

```bash
# Install
pipx install unclaude

# Configure (one-time setup)
unclaude login

# Start coding
unclaude chat "Build me a REST API in FastAPI"
```

---

## ✨ Features

### 🌟 Model Independence
Use **any LLM provider** without lock-in. Switch between models instantly:

```bash
unclaude chat --provider gemini "Fast draft this code"
unclaude chat --provider openai "Review and optimize it"
unclaude chat --provider ollama "Run locally, offline"
```

Supports: **Gemini, GPT-4o, Claude, DeepSeek, Llama, Mistral, Ollama, and 100+ more via LiteLLM**

---

### 🧠 Infinite Memory
UnClaude remembers **everything** across sessions using a local SQLite database:

```bash
# Explicitly save important facts
unclaude chat "Remember: production API key is in .env.prod"

# Query your history
unclaude chat "What tasks have I done this week?"
```

Memory is **project-scoped** for speed: it prioritizes context from your current directory.

---

### 🤖 Ralph Mode (Autonomous Engineering)
Give it a task. Walk away. Come back to working code.

```bash
unclaude ralph "Build a Snake game in Python with pygame" --feedback "python3 snake.py"
```

**Ralph Mode does:**
1. 📝 **Plans**: Generates a `TASK.md` blueprint
2. 💻 **Codes**: Writes multi-file implementations
3. ✅ **Tests**: Runs your feedback command (tests, linters)
4. 🔧 **Self-Heals**: Analyzes failures and fixes bugs automatically

---

### 🌐 Browser Automation
UnClaude has **eyes**. It can see and interact with web applications:

```bash
unclaude chat "Open localhost:3000, click the login button, and take a screenshot"
```

**Capabilities:**
- Open URLs and navigate
- Click, type, and interact with elements
- Take screenshots for visual verification
- Read page content and extract data

*Powered by Playwright*

---

### 🔀 Git Integration
Full version control from within the agent:

```bash
unclaude chat "Show me the git diff and commit with message 'Fix auth bug'"
```

**Supported actions:** `status`, `diff`, `add`, `commit`, `push`, `branch`, `checkout`, `log`

---

### 👥 Subagents
Spawn specialized agents for focused tasks:

```bash
unclaude chat "Use the reviewer subagent to analyze my authentication code"
```

**Built-in templates:**
| Template | Purpose |
|----------|---------|
| `reviewer` | Code review for bugs and style |
| `tester` | Write comprehensive tests |
| `documenter` | Generate documentation |
| `debugger` | Investigate and fix bugs |

---

### ⚡ Background Agents
Run long tasks without blocking your terminal:

```bash
# Start a background task
unclaude background "Refactor all Python files to use type hints"

# Check status later
unclaude jobs
```

---

### 🔌 Hooks System
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

### 🖥️ Headless Mode (CI/CD)
Run UnClaude in non-interactive pipelines:

```bash
# For scripts and automation
unclaude chat "Generate unit tests for api.py" --headless --json
```

Output is clean JSON:
```json
{"response": "I've created tests in test_api.py...", "success": true}
```

---

### 🎯 Skills (Reusable Workflows)
Define repeatable AI workflows as YAML:

```bash
# Create a new skill
unclaude skills --create deploy-prod

# List available skills  
unclaude skills --list

# Run a skill
unclaude skills --run deploy-prod
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

You can also define skills inline in your `UNCLAUDE.md`:
```markdown
## Skills

skill: format-code
description: Format all code files
1. Run prettier on TypeScript files `npx prettier --write "**/*.ts"`
2. Run black on Python files `black .`
3. Run gofmt on Go files `gofmt -w .`
```

---

### 🔌 Plugins
Extend UnClaude with custom plugins:

```bash
# Create a plugin
unclaude plugins --create my-plugin

# List plugins
unclaude plugins --list
```

Plugins can add new tools, modify behavior, or integrate with external services.

---

### 🌐 MCP (Model Context Protocol)
Connect to external MCP servers for extended capabilities:

```bash
# Create MCP config template
unclaude mcp --init

# List configured servers
unclaude mcp --list
```

**MCP config** (`~/.unclaude/mcp.json`):
```json
{
  "servers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {"GITHUB_TOKEN": "your-token"}
    }
  }
}
```

---

### 📁 Project Configuration
Create an `UNCLAUDE.md` in your project root:

```markdown
# Project: My App

## Commands
- `npm run dev` - Start development server
- `npm test` - Run tests

## Architecture
- Frontend: React + TypeScript
- Backend: FastAPI
```

UnClaude automatically reads this for project context.

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

### Browser Support
```bash
playwright install chromium
```

---

## ⚙️ Configuration

```bash
# Interactive setup
unclaude login
```

Or use environment variables:
```bash
export GEMINI_API_KEY="your-key"
export OPENAI_API_KEY="your-key"
```

---

## 🛠️ All Commands

| Command | Description |
|---------|-------------|
| `unclaude chat` | Interactive chat session |
| `unclaude ralph` | Autonomous task completion |
| `unclaude plan` | Generate execution plan only |
| `unclaude background` | Run task in background |
| `unclaude jobs` | Check background job status |
| `unclaude login` | Configure API keys |
| `unclaude init` | Create UNCLAUDE.md template |
| `unclaude plugins` | Manage plugins |
| `unclaude skills` | Manage reusable workflows |
| `unclaude mcp` | Configure MCP servers |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────┐
│              UnClaude CLI               │
├─────────────────────────────────────────┤
│  AgentLoop (Orchestrator)               │
│  ├── ContextLoader (UNCLAUDE.md)        │
│  ├── MemoryStore (SQLite)               │
│  ├── HooksEngine (pre/post automation)  │
│  └── Tool Registry                      │
├─────────────────────────────────────────┤
│  Tools                                  │
│  ├── File (read, write, edit, grep)     │
│  ├── Bash (terminal execution)          │
│  ├── Git (version control)              │
│  ├── Browser (Playwright)               │
│  ├── Memory (search, save)              │
│  ├── Subagent (spawn specialists)       │
│  └── Web (fetch, search)                │
├─────────────────────────────────────────┤
│  LiteLLM (100+ Model Providers)         │
└─────────────────────────────────────────┘
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
