# UnClaude 🤖

> **The Open Source, Model-Independent AI Engineer.** > _Your Data. Your Models. Your Rules._

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](pyproject.toml)
[![Status](https://img.shields.io/badge/status-Production%20Ready-green.svg)](TASK.md)

UnClaude is a powerful **Agentic Coding Assistant** that runs entirely on your local machine. It connects to **any LLM provider** (Gemini, OpenAI, Anthropic, DeepSeek, Ollama) to give you a fully autonomous, model-agnostic pair programmer.

---

## 🚀 Key Features

### 🌟 Model Independence

Don't be locked into a single provider. UnClaude uses `LiteLLM` to support over 100+ models. Switch between cheap, fast models for planning and reasoning models for coding instantly.

### 🧠 Infinite Memory (The Brain)

UnClaude implements a local Vector Database (Chroma/LanceDB) to remember your project context, architecture decisions, and secrets across sessions. It doesn't just read files; it _remembers_.

### 🏗️ Ralph Wiggum Mode (Autonomous Engineer)

The `ralph` command launches a **Multi-Agent Swarm** designed for autonomy:

- **Plans**: Creates a `TASK.md` blueprint before coding.
- **Codes**: Implements complex multi-file projects.
- **Verifies**: Runs tests/commands (`pytest`, `npm test`) in a TDD loop.
- **Self-Heals**: If tests fail, it autonomously analyzes the error and fixes the code.

### 🌐 Browser Automation (The Eyes)

UnClaude includes native **Browser Integration** (via Playwright). It can:

- Open URLs and verify web applications.
- Click, type, and interact with UIs.
- Take screenshots for visual verification.

### 🛠️ Full System Access (The Hands)

A true agent needs tools. UnClaude provides:

- **File Operations**: Read, Write, Edit, Glob, Grep.
- **Terminal**: Execute Bash commands with permission handling.
- **Web**: Search and Fetch capabilities.

---

## 📦 Installation

### Option 1: uv (Recommended)

The fastest way to install Python CLI tools:

```bash
uv tool install unclaude
```

### Option 2: pipx

Another great option for Python CLIs:

```bash
pipx install unclaude
```

### Option 3: pip

```bash
pip install unclaude
```

> **Note:** If `unclaude` command is not found after pip install, ensure `~/.local/bin` is in your PATH.

### Option 4: Development (from source)

If you want to modify the code:

```bash
git clone https://github.com/anzal1/unclaude.git
cd unclaude
pip install -e .
```

### Browser Support

To use the browser tool, you need the Playwright browsers:

```bash
playwright install chromium
```

## ⚙️ Configuration

UnClaude has a built-in onboarding flow.

```bash
# Run the interactive setup wizard
unclaude login
```

This will guide you through:

1.  Selecting your default LLM provider (Gemini, OpenAI, Anthropic, etc.).
2.  Entering your API Key (stored securely in `~/.unclaude/config.toml`).
3.  configuring optional settings.

**No environment variables required!** (Though they are still supported for CI/CD).

## 🎮 Usage

### 💬 Interactive Chat

Just talk to code.

```bash
unclaude chat
> "Refactor utils.py to use async/await."
```

### 🏎️ Create Projects (Ralph Mode)

Give it a job and a way to verify it.

```bash
# The "One Prompt Project"
unclaude ralph "Build a Snake Game in Python with a GUI" -f "python3 snake.py"
```

### 🧠 Managing Memory

UnClaude automatically indexes your conversation for future recall.

```bash
unclaude chat "Remember that the deployment port is 8080."
```

---

## 🏗️ Architecture

UnClaude uses a **Loop-based Agent Architecture**:

1.  **Orchestrator Agent**: Decides if a plan is needed.
2.  **Planner Agent**: Writes `TASK.md`.
3.  **Coder Agent**: Executes tool calls (Edit, Bash, Browser).
4.  **Feedback Loop**: Parses `ToolResult`, `Bash Exit Codes`, and `Memory Retrieval`.

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details.

1.  Fork the repo.
2.  Create a feature branch.
3.  Submit a Pull Request.

## 📄 License

Apache 2.0. Open Source forever.

---

_Built with ❤️ by Anzal & The Community._
