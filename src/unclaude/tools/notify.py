"""Notify owner tool — lets the agent send messages to its human via Telegram/WhatsApp."""

import asyncio
from typing import Any

from unclaude.tools.base import Tool, ToolResult


class NotifyOwnerTool(Tool):
    """Tool for sending messages to the agent's human owner.

    Uses the configured messaging adapters (Telegram, WhatsApp, etc.)
    to reach the owner directly. The agent should use this whenever it
    needs to communicate something to the user — task results, questions,
    URLs, status updates, etc.
    """

    @property
    def name(self) -> str:
        return "notify_owner"

    @property
    def description(self) -> str:
        return (
            "Send a message to your human owner via their configured messaging "
            "platform (Telegram, WhatsApp, etc.). Use this to share results, "
            "ask questions, send URLs/links, report progress, or alert them "
            "about something important. The message will be delivered to all "
            "registered messaging platforms."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": (
                        "The message to send to your owner. Supports basic "
                        "Markdown formatting. Keep it clear and concise."
                    ),
                },
            },
            "required": ["message"],
        }

    @property
    def requires_permission(self) -> bool:
        return False  # Sending messages to the owner is always safe

    async def execute(self, message: str, **kwargs: Any) -> ToolResult:
        try:
            from unclaude.messaging import get_messenger

            messenger = get_messenger()

            # Check if any adapters are configured
            configured = [
                p.value for p, a in messenger.adapters.items()
                if a.is_configured()
            ]
            if not configured:
                return ToolResult(
                    success=False,
                    output="",
                    error=(
                        "No messaging platforms configured. "
                        "The owner hasn't set up Telegram/WhatsApp yet. "
                        "Try an alternative approach (e.g., write to a file, "
                        "or include the info in your final response)."
                    ),
                )

            # Send to all registered chats
            success = await messenger.send(message)

            if success:
                return ToolResult(
                    success=True,
                    output=f"Message sent to owner via {', '.join(configured)}.",
                )
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=(
                        "Failed to deliver message. The messaging adapter "
                        "may be misconfigured or the service is down."
                    ),
                )

        except ImportError:
            return ToolResult(
                success=False,
                output="",
                error="Messaging module not available.",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output="",
                error=f"Failed to send message: {str(e)}",
            )
