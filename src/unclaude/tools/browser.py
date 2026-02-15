"""Browser automation tool using Playwright.

Supports:
- Headless mode (default, for testing/scraping)
- Headed mode with persistent profile (for apps needing login like WhatsApp Web)
- Connecting to user's existing Chrome via CDP (Chrome DevTools Protocol)
"""

import asyncio
import base64
import logging
import os
from pathlib import Path
from typing import Any, Optional

from unclaude.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import (
        async_playwright,
        Playwright,
        Browser,
        BrowserContext,
        Page,
    )
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Persistent browser profile for sessions (WhatsApp, etc.)
BROWSER_DATA_DIR = Path.home() / ".unclaude" / "browser-data"


class BrowserTool(Tool):
    """Control a browser for web automation, verification, and real-world tasks.

    Modes:
    - headless (default): invisible browser for scraping/testing
    - headed: visible browser with persistent profile (WhatsApp Web, etc.)
    - connect: attach to user's already-running Chrome via CDP

    For WhatsApp Web / apps needing login:
    1. Use 'open' with headed=true to launch a visible browser
    2. The profile persists at ~/.unclaude/browser-data/ so logins survive restarts
    3. Or use 'connect' to attach to user's existing browser
    """

    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._lock = asyncio.Lock()
        self._headed = False
        self._connected = False  # True when connected via CDP

    @property
    def name(self) -> str:
        return "browser_tool"

    @property
    def description(self) -> str:
        return (
            "Control a web browser to navigate pages, click elements, type text, "
            "press keys, wait for elements, and take screenshots. "
            "Auto-connects to user's Chrome via CDP (port 9222) if available.\n\n"
            "Actions: 'open', 'connect', 'click', 'type', 'press_key', 'wait', "
            "'screenshot', 'read', 'scroll', 'select_tab', 'close'.\n\n"
            "For WhatsApp Web workflow:\n"
            "1. Use 'connect' (or 'open' which auto-detects CDP)\n"
            "2. Use 'read' to see the page state\n"
            "3. Use 'click' with selector='div[contenteditable=true][data-tab=3]' for search box\n"
            "4. Use 'type' to search for a contact name\n"
            "5. Wait for results, then 'click' the contact\n"
            "6. Use 'click' on the message input (div[contenteditable=true][data-tab=10])\n"
            "7. Use 'type' to write the message, then 'press_key' Enter to send\n"
            "8. Use 'read' to verify the message was sent"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "open", "connect", "click", "type", "press_key",
                        "wait", "screenshot", "read", "scroll",
                        "select_tab", "close",
                    ],
                    "description": "Action to perform",
                },
                "url": {
                    "type": "string",
                    "description": "URL to navigate to (for 'open' action)",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector or text selector like 'text=Search'. For 'click', 'type', 'wait'",
                },
                "text": {
                    "type": "string",
                    "description": "Text to type (for 'type' action) or key to press (for 'press_key')",
                },
                "headed": {
                    "type": "boolean",
                    "description": "Launch visible browser with persistent profile (for 'open'). Default false.",
                },
                "cdp_url": {
                    "type": "string",
                    "description": "Chrome DevTools Protocol URL to connect to (for 'connect'). Default: http://localhost:9222",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in milliseconds for waits. Default 10000 (10s).",
                },
                "path": {
                    "type": "string",
                    "description": "File path for screenshot",
                },
                "tab_index": {
                    "type": "integer",
                    "description": "Tab index to switch to (for 'select_tab'). 0-based.",
                },
                "direction": {
                    "type": "string",
                    "enum": ["up", "down"],
                    "description": "Scroll direction (for 'scroll'). Default 'down'.",
                },
            },
            "required": ["action"],
        }

    @property
    def requires_permission(self) -> bool:
        return True

    async def _ensure_playwright(self):
        """Start Playwright if needed."""
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError(
                "Playwright is not installed. Run: "
                "pip install playwright && playwright install chromium"
            )
        if not self._playwright:
            self._playwright = await async_playwright().start()

    async def _launch_headless(self):
        """Launch a headless browser."""
        await self._ensure_playwright()
        if not self._browser or not self._browser.is_connected():
            self._browser = await self._playwright.chromium.launch(headless=True)
            self._context = await self._browser.new_context(
                viewport={"width": 1280, "height": 720},
            )
            self._page = await self._context.new_page()
            self._headed = False

    async def _launch_headed(self):
        """Launch a visible browser with persistent profile.

        The profile at ~/.unclaude/browser-data/ keeps logins (WhatsApp, etc.)
        alive across sessions.
        """
        await self._ensure_playwright()
        BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)

        if not self._context or self._context.pages == []:
            # launch_persistent_context gives us a context tied to a user data dir
            self._context = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(BROWSER_DATA_DIR),
                headless=False,
                viewport={"width": 1280, "height": 900},
                args=[
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            # Persistent context gives us pages directly
            if self._context.pages:
                self._page = self._context.pages[0]
            else:
                self._page = await self._context.new_page()
            self._headed = True
            self._browser = None  # persistent context doesn't use a separate browser

    async def _connect_cdp(self, cdp_url: str = "http://localhost:9222"):
        """Connect to an existing Chrome instance via CDP.

        User must have Chrome running with:
          /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222
        """
        await self._ensure_playwright()
        if not self._browser or not self._browser.is_connected():
            self._browser = await self._playwright.chromium.connect_over_cdp(cdp_url)
            contexts = self._browser.contexts
            if contexts:
                self._context = contexts[0]
                pages = self._context.pages
                if pages:
                    self._page = pages[0]
                else:
                    self._page = await self._context.new_page()
            else:
                self._context = await self._browser.new_context()
                self._page = await self._context.new_page()
            self._connected = True
            self._headed = True

    async def _try_cdp_connect(self) -> bool:
        """Try to connect to an existing Chrome with CDP on port 9222.

        Returns True if connected successfully.
        """
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get("http://127.0.0.1:9222/json/version", timeout=2)
                if resp.status_code == 200:
                    await self._connect_cdp("http://127.0.0.1:9222")
                    return True
        except Exception:
            pass
        return False

    async def _ensure_page(self, headed: bool = False):
        """Ensure we have a working page.

        Priority: CDP (port 9222) > headed persistent > headless
        """
        if self._page and not self._page.is_closed():
            return

        # Always try CDP first — it gives us the user's real browser
        if await self._try_cdp_connect():
            return

        if headed or self._headed:
            await self._launch_headed()
        else:
            await self._launch_headless()

    async def execute(self, action: str, **kwargs: Any) -> ToolResult:
        if not PLAYWRIGHT_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Playwright not installed. Run: pip install playwright && playwright install chromium",
            )

        async with self._lock:
            try:
                return await self._do_action(action, **kwargs)
            except Exception as e:
                logger.error(f"Browser error ({action}): {e}")
                return ToolResult(success=False, output="", error=f"Browser Error: {str(e)}")

    async def _do_action(self, action: str, **kwargs: Any) -> ToolResult:
        """Execute a browser action."""
        timeout = kwargs.get("timeout", 10000)

        # ── Open URL ────────────────────────────────
        if action == "open":
            url = kwargs.get("url")
            if not url:
                return ToolResult(success=False, error="URL required for 'open'")

            headed = kwargs.get("headed", False)
            await self._ensure_page(headed=headed)

            await self._page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            title = await self._page.title()
            mode = "headed (persistent profile)" if self._headed else "headless"
            return ToolResult(
                success=True,
                output=f"Opened {url} [{mode}]. Title: {title}",
            )

        # ── Connect to existing Chrome ──────────────
        elif action == "connect":
            cdp_url = kwargs.get("cdp_url", "http://localhost:9222")
            await self._connect_cdp(cdp_url)
            pages = self._context.pages if self._context else []
            page_info = []
            for i, p in enumerate(pages):
                try:
                    t = await p.title()
                    page_info.append(f"  [{i}] {t} — {p.url}")
                except Exception:
                    page_info.append(f"  [{i}] (loading) — {p.url}")

            return ToolResult(
                success=True,
                output=f"Connected to Chrome via CDP ({cdp_url}).\n"
                f"Found {len(pages)} tab(s):\n" + "\n".join(page_info),
            )

        # ── Click element ───────────────────────────
        elif action == "click":
            selector = kwargs.get("selector")
            if not selector:
                return ToolResult(success=False, error="Selector required for 'click'")
            await self._ensure_page()
            await self._page.click(selector, timeout=timeout)
            return ToolResult(success=True, output=f"Clicked: {selector}")

        # ── Type text ───────────────────────────────
        elif action == "type":
            text = kwargs.get("text", "")
            selector = kwargs.get("selector")
            if selector:
                await self._ensure_page()
                # Use fill for input fields (replaces content)
                try:
                    await self._page.fill(selector, text, timeout=timeout)
                except Exception:
                    # Fall back to click + type for contenteditable divs (WhatsApp, etc.)
                    await self._page.click(selector, timeout=timeout)
                    await self._page.keyboard.type(text, delay=30)
                return ToolResult(success=True, output=f"Typed '{text[:50]}' into {selector}")
            else:
                # Type into whatever is focused
                await self._ensure_page()
                await self._page.keyboard.type(text, delay=30)
                return ToolResult(success=True, output=f"Typed '{text[:50]}' (into focused element)")

        # ── Press key ───────────────────────────────
        elif action == "press_key":
            key = kwargs.get("text", "Enter")
            await self._ensure_page()
            await self._page.keyboard.press(key)
            return ToolResult(success=True, output=f"Pressed key: {key}")

        # ── Wait for element ────────────────────────
        elif action == "wait":
            selector = kwargs.get("selector")
            if not selector:
                # Just wait for a duration
                wait_ms = kwargs.get("timeout", 2000)
                await asyncio.sleep(wait_ms / 1000)
                return ToolResult(success=True, output=f"Waited {wait_ms}ms")
            await self._ensure_page()
            await self._page.wait_for_selector(selector, timeout=timeout)
            return ToolResult(success=True, output=f"Element found: {selector}")

        # ── Read page content ───────────────────────
        elif action == "read":
            await self._ensure_page()
            title = await self._page.title()
            url = self._page.url
            text = await self._page.inner_text("body")
            # Truncate to avoid token explosion
            if len(text) > 3000:
                text = text[:3000] + "\n...(truncated)"
            return ToolResult(
                success=True,
                output=f"Page: {title}\nURL: {url}\n\n{text}",
            )

        # ── Screenshot ──────────────────────────────
        elif action == "screenshot":
            path = kwargs.get("path", "/tmp/unclaude_screenshot.png")
            await self._ensure_page()
            screenshot_bytes = await self._page.screenshot(full_page=False)
            with open(path, "wb") as f:
                f.write(screenshot_bytes)
            size_kb = len(screenshot_bytes) / 1024
            return ToolResult(
                success=True,
                output=f"Screenshot saved to {path} ({size_kb:.0f} KB)",
            )

        # ── Scroll ──────────────────────────────────
        elif action == "scroll":
            direction = kwargs.get("direction", "down")
            await self._ensure_page()
            delta = 500 if direction == "down" else -500
            await self._page.mouse.wheel(0, delta)
            return ToolResult(success=True, output=f"Scrolled {direction}")

        # ── Select tab ──────────────────────────────
        elif action == "select_tab":
            tab_index = kwargs.get("tab_index", 0)
            if not self._context:
                return ToolResult(success=False, error="No browser context. Open or connect first.")
            pages = self._context.pages
            if tab_index < 0 or tab_index >= len(pages):
                return ToolResult(
                    success=False,
                    error=f"Tab {tab_index} doesn't exist. {len(pages)} tabs open.",
                )
            self._page = pages[tab_index]
            await self._page.bring_to_front()
            title = await self._page.title()
            return ToolResult(
                success=True,
                output=f"Switched to tab [{tab_index}]: {title} — {self._page.url}",
            )

        # ── Close ───────────────────────────────────
        elif action == "close":
            if self._connected and self._browser:
                # Don't close user's browser, just disconnect
                await self._browser.close()
                self._browser = None
                self._context = None
                self._page = None
                self._connected = False
                return ToolResult(success=True, output="Disconnected from Chrome (browser left open)")

            if self._context and self._headed:
                await self._context.close()
                self._context = None
                self._page = None
            elif self._browser:
                await self._browser.close()
                self._browser = None
                self._context = None
                self._page = None

            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

            self._headed = False
            return ToolResult(success=True, output="Browser closed")

        else:
            return ToolResult(success=False, error=f"Unknown action: {action}")
