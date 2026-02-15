"""Context pruning for managing context window size.

The problem: Tool results can be HUGE. A `file_read` might return
an entire file. A `bash_execute` might dump a massive log. This
fills the context window rapidly and degrades performance.

OpenClaw's solution (adapted here):
1. Soft-trim tool results: large outputs get head+tail truncation
2. Age-based pruning: older tool results get trimmed more aggressively
3. Keep recent assistant messages intact (they contain reasoning)
4. System messages are never pruned
5. Track token estimates to know when to prune
"""

from typing import Any


# Approximate tokens per character (rough estimate for English text)
CHARS_PER_TOKEN = 4

# Default limits
DEFAULT_MAX_CONTEXT_TOKENS = 100_000  # ~100K tokens
DEFAULT_TOOL_RESULT_MAX_CHARS = 10_000  # 10K chars (~2.5K tokens)
DEFAULT_RECENT_KEEP_COUNT = 10  # Keep last 10 messages untouched


class ContextPruner:
    """Prunes conversation context to fit within token limits.

    Strategy:
    1. System messages: Never prune
    2. Recent messages (last N): Keep intact
    3. Tool results: Trim to M characters (head + tail)
    4. Old assistant messages: Keep but truncate lengthy ones
    5. Old user messages: Keep (they're usually short)
    """

    def __init__(
        self,
        max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS,
        tool_result_max_chars: int = DEFAULT_TOOL_RESULT_MAX_CHARS,
        recent_keep_count: int = DEFAULT_RECENT_KEEP_COUNT,
    ):
        self.max_context_tokens = max_context_tokens
        self.tool_result_max_chars = tool_result_max_chars
        self.recent_keep_count = recent_keep_count

    def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Estimate total tokens in a message list."""
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "") or ""
            total_chars += len(content)
            # Tool calls add some overhead
            if msg.get("tool_calls"):
                import json
                total_chars += len(json.dumps(msg["tool_calls"]))
        return total_chars // CHARS_PER_TOKEN

    def _trim_content(self, content: str, max_chars: int) -> str:
        """Trim content to max_chars, keeping head + tail."""
        if not content or len(content) <= max_chars:
            return content

        head_size = int(max_chars * 0.6)
        tail_size = int(max_chars * 0.3)

        head = content[:head_size]
        tail = content[-tail_size:]

        trimmed = len(content) - head_size - tail_size
        return f"{head}\n\n... [{trimmed} chars trimmed] ...\n\n{tail}"

    def prune(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Prune messages to fit within token limits.

        Args:
            messages: List of message dicts (role, content, etc.)

        Returns:
            Pruned list of messages.
        """
        if not messages:
            return messages

        current_tokens = self.estimate_tokens(messages)
        if current_tokens <= self.max_context_tokens:
            # Still within limits, but trim oversized tool results
            return self._trim_tool_results(messages)

        # Phase 1: Trim tool results
        pruned = self._trim_tool_results(messages)

        # Phase 2: If still too large, aggressively trim old messages
        current_tokens = self.estimate_tokens(pruned)
        if current_tokens > self.max_context_tokens:
            pruned = self._aggressive_prune(pruned)

        return pruned

    def _trim_tool_results(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Trim oversized tool results.

        Recent tool results get more space, older ones get less.
        """
        result = []
        total = len(messages)

        for i, msg in enumerate(messages):
            if msg.get("role") == "tool":
                content = msg.get("content", "") or ""

                # Calculate age-adjusted max chars
                age = total - i  # Higher = older
                if age > self.recent_keep_count:
                    # Old tool results get aggressive trimming
                    max_chars = min(
                        self.tool_result_max_chars,
                        max(500, self.tool_result_max_chars //
                            (age // self.recent_keep_count + 1)),
                    )
                else:
                    max_chars = self.tool_result_max_chars

                trimmed_content = self._trim_content(content, max_chars)
                result.append({**msg, "content": trimmed_content})
            else:
                result.append(msg)

        return result

    def _aggressive_prune(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Aggressively prune to fit within limits.

        Keeps:
        - All system messages
        - Last N messages (user + assistant + tool)
        - Highly truncated versions of everything else
        """
        if len(messages) <= self.recent_keep_count + 1:
            return messages

        system_messages = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]

        # Keep recent messages
        recent = non_system[-self.recent_keep_count:]

        # Heavily truncate older messages
        older = non_system[:-self.recent_keep_count]
        truncated_older = []

        for msg in older:
            role = msg.get("role", "")
            content = msg.get("content", "") or ""

            if role == "user":
                # Keep user messages but truncate if very long
                truncated_older.append({
                    **msg,
                    "content": self._trim_content(content, 500),
                })
            elif role == "assistant":
                # Truncate assistant reasoning
                truncated_older.append({
                    **msg,
                    "content": self._trim_content(content, 1000),
                    # Keep tool calls intact
                    "tool_calls": msg.get("tool_calls"),
                })
            elif role == "tool":
                # Heavily truncate old tool results
                truncated_older.append({
                    **msg,
                    "content": self._trim_content(content, 200),
                })

        return system_messages + truncated_older + recent

    def should_compact(self, messages: list[dict[str, Any]]) -> bool:
        """Check if messages should be compacted (summarized).

        Compaction is more aggressive than pruning - it replaces
        old messages with a summary.

        Returns:
            True if compaction is recommended.
        """
        tokens = self.estimate_tokens(messages)
        # Compact when we're at 70% of max
        return tokens > (self.max_context_tokens * 0.7)
