# 🚢 Publishing UnClaude to PyPI

To make commands like `pipx run unclaude` or `pip install unclaude` work for everyone, you need to publish your package to the **Python Package Index (PyPI)**.

## Prerequisites

1.  **Create a PyPI Account**: Go to [pypi.org](https://pypi.org) and register.
2.  **Install Build Tools**:
    ```bash
    pip install build twine
    ```

## Step 1: Prepare Distribution

1.  **Check `pyproject.toml`**: Ensure the `version`, `description`, and `dependencies` are correct.
2.  **Build the Package**:
    ```bash
    # Clean previous builds
    rm -rf dist/
    
    # Build Source & Wheel
    python3 -m build
    ```
    This creates files in `dist/` (e.g., `unclaude-0.1.0.tar.gz` and `.whl`).

## Step 2: Upload to PyPI

1.  **Test Upload** (Optional, uses TestPyPI):
    ```bash
    python3 -m twine upload --repository testpypi dist/*
    ```
2.  **Real Upload**:
    ```bash
    python3 -m twine upload dist/*
    ```
    *You will be prompted for your PyPI username/password (or API token).*

## Step 3: Verify

Once uploaded, you (and anyone else) can run:

```bash
pipx run unclaude chat
# or
pip install unclaude
```

## 🔄 Automated Publishing (Merge to Main)

I've configured a GitHub Action (`.github/workflows/publish.yml`) that automatically releases to PyPI whenever you **push to the `main` branch**.

### How it works:
1.  **Develop**: Make changes in a feature branch.
2.  **Bump Version**: Update `version = "0.x.x"` in `pyproject.toml`.
3.  **Merge**: Merge your PR into `main`.
4.  **Release**: The Action detects the change, builds the package, and uploading usage `skip-existing` (so if you didn't bump the version, it quietly skips instead of failing).

### Setup Required on PyPI
For this to work without passwords, you need **Trusted Publishing**:
1.  Go to PyPI > Manage Project > Publishing.
2.  Add a generic **GitHub Publisher**.
3.  Owner: `your-github-username`, Repo: `unclaude`, Workflow: `publish.yml`.

Now GitHub can verify its identity to PyPI securely! 🪄

### 3. How Users Update
Python packages do not silently auto-update on user machines (for stability).

Users will run:
```bash
pipx upgrade unclaude
# or
pip install --upgrade unclaude
```

If they use `pipx run unclaude@latest chat`, it will stick to the latest ephemeral version.
