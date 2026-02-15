#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  UnClaude Installer — One-line setup for non-technical users
# ═══════════════════════════════════════════════════════════════
#
#  curl -sSL https://raw.githubusercontent.com/anthropics/unclaude/main/scripts/install.sh | bash
#
#  This script:
#   1. Checks for Python 3.10+
#   2. Installs pipx if needed
#   3. Installs unclaude via pipx
#   4. Launches the web setup wizard
#

set -euo pipefail

# ── Colors ──────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

print_banner() {
    echo ""
    echo -e "${CYAN}  ╔═══════════════════════════════════════╗${NC}"
    echo -e "${CYAN}  ║${NC}  ${BOLD}🤖 UnClaude Installer${NC}                ${CYAN}║${NC}"
    echo -e "${CYAN}  ║${NC}  ${DIM}Open-source AI coding assistant${NC}      ${CYAN}║${NC}"
    echo -e "${CYAN}  ╚═══════════════════════════════════════╝${NC}"
    echo ""
}

info()    { echo -e "  ${BLUE}ℹ${NC}  $1"; }
success() { echo -e "  ${GREEN}✓${NC}  $1"; }
warn()    { echo -e "  ${YELLOW}⚠${NC}  $1"; }
error()   { echo -e "  ${RED}✗${NC}  $1"; }
step()    { echo -e "\n  ${PURPLE}▸${NC}  ${BOLD}$1${NC}"; }

# ── Detect OS ──────────────────────────────────────────
detect_os() {
    case "$(uname -s)" in
        Darwin*)  OS="macos" ;;
        Linux*)   OS="linux" ;;
        MINGW*|MSYS*|CYGWIN*) OS="windows" ;;
        *)        OS="unknown" ;;
    esac
}

# ── Check Python ───────────────────────────────────────
check_python() {
    step "Checking Python..."

    # Try python3 first, then python
    if command -v python3 &>/dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &>/dev/null; then
        PYTHON_CMD="python"
    else
        PYTHON_CMD=""
    fi

    if [ -z "$PYTHON_CMD" ]; then
        error "Python not found"
        echo ""
        if [ "$OS" = "macos" ]; then
            info "Install Python with:"
            echo -e "    ${CYAN}brew install python3${NC}"
            echo -e "    ${DIM}or download from https://www.python.org/downloads/${NC}"
        elif [ "$OS" = "linux" ]; then
            info "Install Python with:"
            echo -e "    ${CYAN}sudo apt install python3 python3-pip python3-venv${NC}"
            echo -e "    ${DIM}or: sudo dnf install python3 python3-pip${NC}"
        else
            info "Download Python from: https://www.python.org/downloads/"
        fi
        echo ""
        exit 1
    fi

    # Check version (need 3.10+)
    PY_VERSION=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PY_MAJOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info.major)')
    PY_MINOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info.minor)')

    if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
        error "Python $PY_VERSION found, but 3.10+ is required"
        echo ""
        if [ "$OS" = "macos" ]; then
            info "Upgrade with: ${CYAN}brew upgrade python3${NC}"
        elif [ "$OS" = "linux" ]; then
            info "Install a newer version: ${CYAN}sudo apt install python3.12${NC}"
        fi
        exit 1
    fi

    success "Python $PY_VERSION"
}

# ── Check/Install pipx ────────────────────────────────
check_pipx() {
    step "Checking pipx..."

    if command -v pipx &>/dev/null; then
        success "pipx already installed"
        return
    fi

    info "Installing pipx..."

    if [ "$OS" = "macos" ]; then
        if command -v brew &>/dev/null; then
            brew install pipx 2>/dev/null || $PYTHON_CMD -m pip install --user pipx
        else
            $PYTHON_CMD -m pip install --user pipx
        fi
    elif [ "$OS" = "linux" ]; then
        if command -v apt &>/dev/null; then
            sudo apt install -y pipx 2>/dev/null || $PYTHON_CMD -m pip install --user pipx
        elif command -v dnf &>/dev/null; then
            sudo dnf install -y pipx 2>/dev/null || $PYTHON_CMD -m pip install --user pipx
        else
            $PYTHON_CMD -m pip install --user pipx
        fi
    else
        $PYTHON_CMD -m pip install --user pipx
    fi

    # Ensure pipx is on PATH
    if ! command -v pipx &>/dev/null; then
        $PYTHON_CMD -m pipx ensurepath 2>/dev/null || true
        export PATH="$HOME/.local/bin:$PATH"
    fi

    if command -v pipx &>/dev/null; then
        success "pipx installed"
    else
        error "Could not install pipx"
        info "Try manually: ${CYAN}$PYTHON_CMD -m pip install --user pipx${NC}"
        exit 1
    fi
}

# ── Install UnClaude ───────────────────────────────────
install_unclaude() {
    step "Installing UnClaude..."

    if command -v unclaude &>/dev/null; then
        CURRENT_VERSION=$(unclaude --version 2>/dev/null || echo "unknown")
        warn "UnClaude already installed ($CURRENT_VERSION)"
        info "Upgrading..."
        pipx upgrade unclaude 2>/dev/null || pipx install unclaude --force
    else
        pipx install "unclaude[web]"
    fi

    if command -v unclaude &>/dev/null; then
        VERSION=$(unclaude --version 2>/dev/null || echo "installed")
        success "UnClaude $VERSION"
    else
        # Try adding to PATH
        export PATH="$HOME/.local/bin:$PATH"
        if command -v unclaude &>/dev/null; then
            success "UnClaude installed (restart terminal to use globally)"
        else
            error "Installation failed"
            info "Try manually: ${CYAN}pipx install unclaude[web]${NC}"
            exit 1
        fi
    fi
}

# ── Launch Web Setup ───────────────────────────────────
launch_setup() {
    step "Launching setup wizard..."
    echo ""
    info "Opening UnClaude in your browser..."
    info "${DIM}Complete the setup in the web interface.${NC}"
    echo ""

    # Launch web server (it will auto-open browser)
    unclaude web
}

# ── Main ───────────────────────────────────────────────
main() {
    print_banner
    detect_os

    check_python
    check_pipx
    install_unclaude

    echo ""
    echo -e "  ${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    success "${BOLD}Installation complete!${NC}"
    echo -e "  ${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    info "Quick commands:"
    echo -e "    ${CYAN}unclaude${NC}              Chat with your agent"
    echo -e "    ${CYAN}unclaude setup${NC}        Run guided setup"
    echo -e "    ${CYAN}unclaude web${NC}          Open web dashboard"
    echo -e "    ${CYAN}unclaude agent start${NC}  Start autonomous daemon"
    echo ""

    # Auto-launch web setup if not yet configured
    if ! unclaude --check-config 2>/dev/null; then
        launch_setup
    else
        success "Already configured — run ${CYAN}unclaude${NC} to start!"
    fi
}

main "$@"
