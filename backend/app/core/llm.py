"""LLM provider abstraction for the Cortex Autopilot.

The Autopilot talks to the LLM through the OpenAI Python SDK, which is
compatible with any OpenAI-shaped endpoint. The default provider is
Nvidia NIM (https://integrate.api.nvidia.com/v1), but switching to
OpenAI / Azure / Ollama / a self-hosted vLLM is a one-line config change.

Usage:
    provider = LlmProvider.from_settings()
    response = await provider.chat(messages, tools=tool_schemas)
    if response.tool_calls:
        ...execute tools, append results, loop...
    else:
        final_answer = response.content

When no API key is configured (`CORTEX_LLM_PROVIDER=none` or missing key),
the provider falls back to `DummyLlmProvider` which returns a deterministic
"not configured" message. This lets the rest of the Autopilot stack boot
in dev / CI without an external dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.core.settings import settings


@dataclass
class LlmResponse:
    """The bits of the OpenAI ChatCompletion response the agent cares about."""

    content: str
    tool_calls: List[Dict[str, Any]]
    finish_reason: str
    raw: Any = None


class BaseLlmProvider:
    """Abstract LLM provider — async `chat()` is the only required method."""

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> LlmResponse:
        raise NotImplementedError


class OpenAiCompatibleProvider(BaseLlmProvider):
    """Works against any OpenAI-compatible endpoint (Nvidia NIM, vLLM, Ollama)."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        default_headers: Optional[Dict[str, str]] = None,
    ):
        # Lazy import so the openai package only needs to be installed
        # when the Autopilot actually runs.
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The `openai` package is required for LLM features. "
                "Install it with: pip install openai"
            ) from exc

        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            default_headers=default_headers or {},
        )
        self._model = model

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> LlmResponse:
        kwargs: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if tools:
            kwargs["tools"] = [
                {"type": "function", "function": tool} for tool in tools
            ]

        completion = await self._client.chat.completions.create(**kwargs)
        choice = completion.choices[0]
        message = choice.message

        tool_calls: List[Dict[str, Any]] = []
        if message.tool_calls:
            import json

            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except (ValueError, TypeError):
                    args = {}
                tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": args,
                    }
                )

        return LlmResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            raw=completion,
        )


class DummyLlmProvider(BaseLlmProvider):
    """No-op provider used when no LLM API key is configured.

    Returns a single short message and no tool calls so the agent loop
    exits cleanly with a clear explanation rather than crashing.
    """

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> LlmResponse:
        return LlmResponse(
            content=(
                "LLM provider not configured. Set CORTEX_LLM_PROVIDER=nvidia "
                "and CORTEX_NVIDIA_API_KEY to enable agent reasoning."
            ),
            tool_calls=[],
            finish_reason="stop",
        )


def get_llm_provider() -> BaseLlmProvider:
    """Build the LLM provider based on the current settings."""
    provider = settings.CORTEX_LLM_PROVIDER

    if provider == "none":
        return DummyLlmProvider()

    if provider == "nvidia":
        if not settings.CORTEX_NVIDIA_API_KEY:
            return DummyLlmProvider()
        return OpenAiCompatibleProvider(
            api_key=settings.CORTEX_NVIDIA_API_KEY,
            base_url=settings.CORTEX_NVIDIA_BASE_URL,
            model=settings.CORTEX_NVIDIA_MODEL,
        )

    if provider == "openai":
        # Reuse the same class; caller supplies a real OpenAI key via env.
        import os

        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            return DummyLlmProvider()
        return OpenAiCompatibleProvider(
            api_key=key,
            base_url="https://api.openai.com/v1",
            model="gpt-4o-mini",
        )

    return DummyLlmProvider()
