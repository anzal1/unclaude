"""Model provider abstraction using LiteLLM."""

from typing import Any, AsyncIterator

import litellm
from pydantic import BaseModel

from unclaude.config import ProviderConfig, get_settings


class Message(BaseModel):
    """A message in the conversation."""

    role: str  # system, user, assistant, tool
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class ToolDefinition(BaseModel):
    """Definition of a tool that can be called by the LLM."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


class ToolCall(BaseModel):
    """A tool call requested by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


class LLMResponse(BaseModel):
    """Response from the LLM."""

    content: str | None = None
    tool_calls: list[ToolCall] = []
    finish_reason: str | None = None
    usage: dict[str, int] = {}


class Provider:
    """LLM provider abstraction using LiteLLM."""

    def __init__(self, provider_name: str | None = None):
        """Initialize the provider.

        Args:
            provider_name: Name of the provider to use. If None, uses default.
        """
        settings = get_settings()
        self.provider_name = provider_name or settings.default_provider

        if self.provider_name not in settings.providers:
            # Create a default Gemini config if no providers configured
            self.config = ProviderConfig(
                model="gemini/gemini-2.0-flash",
                api_key=None,  # Will use GEMINI_API_KEY env var
            )
        else:
            self.config = settings.providers[self.provider_name]

    def _get_model_name(self) -> str:
        """Get the full model name for LiteLLM."""
        model = self.config.model

        # LiteLLM requires provider prefix for some models
        if self.config.provider == "ollama":
            return f"ollama/{model}"
        elif self.provider_name == "gemini" and not model.startswith("gemini/"):
            return f"gemini/{model}"
        elif self.provider_name == "anthropic" and not model.startswith("anthropic/"):
            return f"anthropic/{model}"
        elif self.provider_name == "openai":
            return model  # OpenAI is the default

        return model

    def _build_tools(self, tools: list[ToolDefinition]) -> list[dict[str, Any]]:
        """Convert tool definitions to OpenAI-compatible format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Send a chat request to the LLM.

        Args:
            messages: List of messages in the conversation.
            tools: Optional list of tools the LLM can call.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.

        Returns:
            LLMResponse with content and/or tool calls.
        """
        # Convert messages to dict format
        message_dicts = []
        for msg in messages:
            msg_dict: dict[str, Any] = {"role": msg.role}
            
            # Always include content for assistant messages (even if empty)
            if msg.role == "assistant":
                msg_dict["content"] = msg.content or ""
            elif msg.content is not None:
                msg_dict["content"] = msg.content
            
            if msg.tool_calls:
                msg_dict["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                msg_dict["tool_call_id"] = msg.tool_call_id
            if msg.name:
                msg_dict["name"] = msg.name
            message_dicts.append(msg_dict)

        # Build request kwargs
        kwargs: dict[str, Any] = {
            "model": self._get_model_name(),
            "messages": message_dicts,
            "temperature": temperature,
        }

        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        if tools:
            kwargs["tools"] = self._build_tools(tools)

        if self.config.api_key:
            kwargs["api_key"] = self.config.api_key

        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url

        # Make the request using LiteLLM with retry for empty responses
        max_retries = 3
        last_error = None
        original_tools = kwargs.get("tools")
        
        for attempt in range(max_retries):
            try:
                response = await litellm.acompletion(**kwargs)
                
                # Parse the response
                choice = response.choices[0]
                message = choice.message

                tool_calls = []
                if message.tool_calls:
                    import json

                    for tc in message.tool_calls:
                        tool_calls.append(
                            ToolCall(
                                id=tc.id,
                                name=tc.function.name,
                                arguments=json.loads(tc.function.arguments),
                            )
                        )

                return LLMResponse(
                    content=message.content,
                    tool_calls=tool_calls,
                    finish_reason=choice.finish_reason,
                    usage={
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens,
                    },
                )
            except Exception as e:
                last_error = e
                error_msg = str(e).lower()
                
                # Check for known Gemini/LiteLLM errors
                is_empty_error = any(x in error_msg for x in [
                    "empty", "must contain", "cannot both be empty"
                ])
                
                if is_empty_error and attempt < max_retries - 1:
                    # Remove tools on retry - this often fixes Gemini issues
                    if "tools" in kwargs:
                        del kwargs["tools"]
                    # Add small delay
                    import asyncio
                    await asyncio.sleep(0.5)
                    continue
                elif is_empty_error:
                    # On final attempt for empty error, return graceful response
                    return LLMResponse(
                        content="I received an incomplete response from the AI model. This sometimes happens with complex tool interactions. Please try rephrasing your request or breaking it into smaller steps.",
                        tool_calls=[],
                        finish_reason="error",
                        usage={},
                    )
                else:
                    # For other errors, raise them
                    raise
        
        # If we get here, return placeholder
        return LLMResponse(
            content=f"I encountered an issue processing your request. Please try again.",
            tool_calls=[],
            finish_reason="error",
            usage={},
        )

    async def stream_chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        """Stream a chat response from the LLM.

        Args:
            messages: List of messages in the conversation.
            tools: Optional list of tools (not supported in streaming).
            temperature: Sampling temperature.

        Yields:
            Chunks of the response content.
        """
        message_dicts = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
            if msg.content
        ]

        kwargs: dict[str, Any] = {
            "model": self._get_model_name(),
            "messages": message_dicts,
            "temperature": temperature,
            "stream": True,
        }

        if self.config.api_key:
            kwargs["api_key"] = self.config.api_key

        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url

        response = await litellm.acompletion(**kwargs)

        async for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
