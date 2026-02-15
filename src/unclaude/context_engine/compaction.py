"""Context compaction via LLM summarization.

When the context window is getting too full, we compact old messages
into a concise summary. This lets the agent maintain long conversations
without losing important context.

From OpenClaw's compaction.ts:
1. Identify messages to compact (old ones beyond a threshold)
2. Send them to the LLM with a summarization prompt
3. Replace the old messages with the summary
4. Keep recent messages intact

The summary preserves:
- Key decisions made
- Files modified and why
- Errors encountered and how they were resolved
- Outstanding tasks/questions
- Important code snippets or references
"""

from typing import Any

from unclaude.providers import Provider


COMPACTION_PROMPT = """You are a conversation summarizer. Summarize the following conversation history
into a concise but complete summary that preserves all important context for continuing the conversation.

PRESERVE:
- Key decisions and their rationale
- Files that were modified and why
- Errors encountered and their resolutions
- Outstanding tasks or questions
- Important code snippets or API details
- User preferences expressed
- The current state of the task

FORMAT:
- Use bullet points for clarity
- Group by topic/file/task
- Include specific file paths and line numbers where relevant
- Keep code snippets if they're referenced later

CONVERSATION TO SUMMARIZE:
{messages}

SUMMARY:"""


class ContextCompactor:
    """Compacts conversation history via LLM summarization.

    This is the nuclear option for context management.
    Use it when pruning isn't enough.
    """

    def __init__(
        self,
        provider: Provider | None = None,
        compact_threshold: int = 50,  # Messages before compaction triggers
        keep_recent: int = 20,  # Messages to keep after compaction
    ):
        self.provider = provider
        self.compact_threshold = compact_threshold
        self.keep_recent = keep_recent

    async def compact(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[str, list[dict[str, Any]]]:
        """Compact old messages into a summary.

        Args:
            messages: Full message history.

        Returns:
            (summary, remaining_messages) tuple.
            remaining_messages includes the summary as a system message
            followed by the recent messages.
        """
        if len(messages) <= self.keep_recent:
            return "", messages

        # Separate system messages from conversation
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        # Split into old (to compact) and recent (to keep)
        old_messages = non_system[:-self.keep_recent]
        recent_messages = non_system[-self.keep_recent:]

        if not old_messages:
            return "", messages

        # Format old messages for summarization
        formatted = self._format_messages_for_summary(old_messages)

        # Generate summary
        summary = await self._generate_summary(formatted)

        if not summary:
            # Fallback: just truncate without summary
            return "", system_msgs + recent_messages

        # Build new message list
        compacted_messages = system_msgs.copy()
        compacted_messages.append({
            "role": "system",
            "content": f"[CONVERSATION HISTORY SUMMARY - {len(old_messages)} messages compacted]\n{summary}\n[END SUMMARY]",
        })
        compacted_messages.extend(recent_messages)

        return summary, compacted_messages

    def _format_messages_for_summary(
        self,
        messages: list[dict[str, Any]],
    ) -> str:
        """Format messages into a readable string for the summarizer."""
        parts = []

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "") or ""

            if role == "user":
                parts.append(f"USER: {content[:1000]}")
            elif role == "assistant":
                # Include tool calls info
                if msg.get("tool_calls"):
                    tools_used = [tc.get("function", {}).get(
                        "name", "?") for tc in msg["tool_calls"]]
                    parts.append(
                        f"ASSISTANT: {content[:500]} [Used tools: {', '.join(tools_used)}]")
                else:
                    parts.append(f"ASSISTANT: {content[:1000]}")
            elif role == "tool":
                name = msg.get("name", "unknown")
                # Heavily truncate tool results for summary
                parts.append(f"TOOL ({name}): {content[:300]}")

        return "\n".join(parts)

    async def _generate_summary(self, formatted_messages: str) -> str:
        """Generate a summary using the LLM.

        Falls back to a simple extraction if LLM is unavailable.
        """
        if not self.provider:
            return self._fallback_summary(formatted_messages)

        try:
            from unclaude.providers import Message

            prompt = COMPACTION_PROMPT.format(messages=formatted_messages)
            response = await self.provider.chat(
                messages=[Message(role="user", content=prompt)],
                tools=None,
            )
            return response.content or self._fallback_summary(formatted_messages)
        except Exception:
            return self._fallback_summary(formatted_messages)

    def _fallback_summary(self, text: str) -> str:
        """Simple fallback summary when LLM is unavailable.

        Just extracts key lines and truncates.
        """
        lines = text.split("\n")

        # Keep user messages and tool names
        important = []
        for line in lines:
            if line.startswith("USER:"):
                important.append(line[:200])
            elif "Used tools:" in line:
                important.append(line[:200])
            elif line.startswith("TOOL (") and ("Error" in line or "success" in line.lower()):
                important.append(line[:200])

        if important:
            return "Key points from conversation history:\n" + "\n".join(important[:30])
        return "Previous conversation history was compacted."

    def should_compact(self, messages: list[dict[str, Any]]) -> bool:
        """Check if compaction should be triggered.

        Args:
            messages: Current message history.

        Returns:
            True if compaction is recommended.
        """
        non_system = [m for m in messages if m.get("role") != "system"]
        return len(non_system) > self.compact_threshold
