"""Browser automation tool using Playwright."""

import asyncio
import base64
from typing import Any, Optional

from unclaude.tools.base import Tool, ToolResult

try:
    from playwright.async_api import async_playwright, Playwright, Browser, Page
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class BrowserTool(Tool):
    """Control a browser for verification and automation."""

    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "browser_tool"

    @property
    def description(self) -> str:
        return (
            "Control a web browser to navigate pages, click elements, type text, and take screenshots. "
            "Useful for verifying web applications. "
            "Supported actions: 'open', 'click', 'type', 'screenshot', 'read', 'close'. "
            "Requires 'playwright' to be installed."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["open", "click", "type", "screenshot", "read", "close"],
                    "description": "Action to perform",
                },
                "url": {
                    "type": "string",
                    "description": "URL to open (for 'open' action)",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector to interact with (for 'click', 'type')",
                },
                "text": {
                    "type": "string",
                    "description": "Text to type (for 'type' action)",
                },
                "path": {
                    "type": "string",
                    "description": "Path to save screenshot (for 'screenshot' action)",
                },
            },
            "required": ["action"],
        }

    @property
    def requires_permission(self) -> bool:
        return True

    async def _ensure_browser(self):
        """Ensure browser is open."""
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError("Playwright is not installed. Run 'uv pip install playwright && playwright install chromium'")

        if not self._playwright:
            self._playwright = await async_playwright().start()
        
        if not self._browser:
            # We launch headless by default, but maybe creating a visible internal browser later?
            self._browser = await self._playwright.chromium.launch(headless=True)
            
        if not self._page:
            self._page = await self._browser.new_page()

    async def execute(self, action: str, **kwargs: Any) -> ToolResult:
        if not PLAYWRIGHT_AVAILABLE:
            return ToolResult(
                success=False,
                output="",
                error="Playwright not installed. Please ask user to install it.",
            )

        async with self._lock:
            try:
                if action == "open":
                    url = kwargs.get("url")
                    if not url:
                        return ToolResult(success=False, error="URL required for 'open'")
                    await self._ensure_browser()
                    if self._page:
                        await self._page.goto(url)
                        title = await self._page.title()
                        return ToolResult(success=True, output=f"Opened {url}. Title: {title}")

                elif action == "click":
                    selector = kwargs.get("selector")
                    if not selector:
                        return ToolResult(success=False, error="Selector required for 'click'")
                    await self._ensure_browser()
                    if self._page:
                        await self._page.click(selector)
                        return ToolResult(success=True, output=f"Clicked {selector}")

                elif action == "type":
                    selector = kwargs.get("selector")
                    text = kwargs.get("text")
                    if not selector or text is None:
                        return ToolResult(success=False, error="Selector and text required for 'type'")
                    await self._ensure_browser()
                    if self._page:
                        await self._page.fill(selector, text)
                        return ToolResult(success=True, output=f"Typed '{text}' into {selector}")

                elif action == "read":
                    await self._ensure_browser()
                    if self._page:
                        content = await self._page.content()
                        # Simple summarization or return raw HTML? Raw might be huge.
                        # Let's return text content
                        text = await self._page.inner_text("body")
                        return ToolResult(success=True, output=text[:2000] + "..." if len(text) > 2000 else text)

                elif action == "screenshot":
                    path = kwargs.get("path", "screenshot.png")
                    await self._ensure_browser()
                    if self._page:
                        await self._page.screenshot(path=path)
                        return ToolResult(success=True, output=f"Screenshot saved to {path}")

                elif action == "close":
                    if self._browser:
                        await self._browser.close()
                        self._browser = None
                        self._page = None
                    if self._playwright:
                        await self._playwright.stop()
                        self._playwright = None
                    return ToolResult(success=True, output="Browser closed")

                else:
                    return ToolResult(success=False, error=f"Unknown action: {action}")

            except Exception as e:
                return ToolResult(success=False, output="", error=f"Browser Error: {str(e)}")
            
            return ToolResult(success=False, error="Unknown error")
