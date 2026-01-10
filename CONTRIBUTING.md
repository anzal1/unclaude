# Contributing to UnClaude

We are building the open source coding agent ecosystem! 🚀

## Development Setup

1.  **Fork & Clone**:
    ```bash
    git clone https://github.com/YOUR_USERNAME/unclaude.git
    cd unclaude
    ```
2.  **Environment**:
    UnClaude uses `uv` for dependency management, but `pip` works too.
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    uv pip install -e .
    uv pip install -r requirements-dev.txt
    ```
3.  **Tests**:
    We use `pytest`.
    ```bash
    pytest
    ```

## Adding Features

*   **Tools**: Add new tools in `src/unclaude/tools/`. Inherit from `Tool`.
*   **Prompting**: Prompts are in `src/unclaude/prompts.py`.
*   **Architecture**: `AgentLoop` manages the lifecycle.

## Pull Request Process

1.  Ensure all tests pass.
2.  Update `README.md` if changing user-facing features.
3.  Submit PR with a description of changes.

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
