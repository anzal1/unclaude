"""Web tools for UnClaude."""

import asyncio
import re
from typing import Any
from urllib.parse import quote_plus, urljoin

from unclaude.tools.base import Tool, ToolResult


class WebFetchTool(Tool):
    """Fetch content from a URL."""

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return (
            "Fetch the content of a web page and return it as text. "
            "Useful for reading documentation, APIs, or any public web page."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch",
                },
                "max_length": {
                    "type": "integer",
                    "description": "Maximum length of content to return (default 10000)",
                },
            },
            "required": ["url"],
        }

    async def execute(
        self, url: str, max_length: int = 10000, **kwargs: Any
    ) -> ToolResult:
        try:
            import httpx

            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "")

                if "text/html" in content_type:
                    # Try to extract text from HTML
                    html = response.text
                    # Simple HTML to text conversion
                    text = self._html_to_text(html)
                else:
                    text = response.text

                if len(text) > max_length:
                    text = text[:max_length] + "\n\n[Content truncated...]"

                return ToolResult(success=True, output=text)

        except ImportError:
            return ToolResult(
                success=False,
                output="",
                error="httpx library not installed. Run: pip install httpx",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text."""
        # Remove script and style elements
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags
        html = re.sub(r"<[^>]+>", " ", html)

        # Decode HTML entities
        html = html.replace("&nbsp;", " ")
        html = html.replace("&amp;", "&")
        html = html.replace("&lt;", "<")
        html = html.replace("&gt;", ">")
        html = html.replace("&quot;", '"')

        # Clean up whitespace
        html = re.sub(r"\s+", " ", html)
        html = "\n".join(line.strip() for line in html.split("\n") if line.strip())

        return html.strip()


class WebSearchTool(Tool):
    """Search the web using DuckDuckGo."""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Search the web for information. Returns a list of search results "
            "with titles, URLs, and snippets."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (default 5)",
                },
            },
            "required": ["query"],
        }

    async def execute(
        self, query: str, max_results: int = 5, **kwargs: Any
    ) -> ToolResult:
        try:
            import httpx

            # Use DuckDuckGo HTML search (no API key needed)
            url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; UnClaude/1.0)"
                    },
                )
                response.raise_for_status()
                html = response.text

            # Parse results from HTML
            results = self._parse_ddg_results(html, max_results)

            if not results:
                return ToolResult(
                    success=True,
                    output="No results found for the query.",
                )

            output_lines = [f"Search results for: {query}\n"]
            for i, result in enumerate(results, 1):
                output_lines.append(f"{i}. {result['title']}")
                output_lines.append(f"   URL: {result['url']}")
                output_lines.append(f"   {result['snippet']}\n")

            return ToolResult(success=True, output="\n".join(output_lines))

        except ImportError:
            return ToolResult(
                success=False,
                output="",
                error="httpx library not installed. Run: pip install httpx",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _parse_ddg_results(self, html: str, max_results: int) -> list[dict[str, str]]:
        """Parse DuckDuckGo HTML search results."""
        results = []

        # Find result blocks
        result_pattern = r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.+?)</a>'
        snippet_pattern = r'<a class="result__snippet"[^>]*>(.+?)</a>'

        urls = re.findall(result_pattern, html, re.DOTALL)
        snippets = re.findall(snippet_pattern, html, re.DOTALL)

        for i, (url, title) in enumerate(urls[:max_results]):
            # Clean up title
            title = re.sub(r"<[^>]+>", "", title).strip()

            # Get snippet if available
            snippet = ""
            if i < len(snippets):
                snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()

            # DuckDuckGo uses redirect URLs, extract actual URL
            if "uddg=" in url:
                import urllib.parse
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
                if "uddg" in parsed:
                    url = parsed["uddg"][0]

            results.append({
                "title": title,
                "url": url,
                "snippet": snippet,
            })

        return results
