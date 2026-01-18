"""LLM Adapter - Standard interface for local and cloud LLM providers.

Supports:
- OpenAI (cloud)
- Anthropic (cloud)
- Ollama (local)
- Local OpenAI-compatible servers (LM Studio, etc.)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from aos_context.config import LLMConfig


class LLMClient:
    """Unified client for LLM providers (local and cloud).

    Automatically selects the appropriate client based on provider configuration.
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        """Initialize LLM client.

        Args:
            config: LLMConfig instance. If None, loads from environment.
        """
        self.config = config or LLMConfig.from_env()
        self._client = self._create_client()

    def _create_client(self) -> Any:
        """Create the appropriate client based on provider."""
        provider = self.config.provider.lower()

        if provider == "openai":
            return self._create_openai_client()
        elif provider == "anthropic":
            return self._create_anthropic_client()
        elif provider in ("ollama", "local"):
            return self._create_openai_compatible_client()
        else:
            raise ValueError(
                f"Unsupported provider: {provider}. "
                "Supported: 'openai', 'anthropic', 'ollama', 'local'"
            )

    def _create_openai_client(self) -> Any:
        """Create OpenAI client."""
        try:
            from openai import OpenAI

            kwargs = {}
            if self.config.api_key:
                kwargs["api_key"] = self.config.api_key
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url

            return OpenAI(**kwargs)
        except ImportError:
            raise ImportError(
                "OpenAI client not installed. Install with: pip install openai"
            )

    def _create_anthropic_client(self) -> Any:
        """Create Anthropic client."""
        try:
            from anthropic import Anthropic

            kwargs = {}
            if self.config.api_key:
                kwargs["api_key"] = self.config.api_key

            return Anthropic(**kwargs)
        except ImportError:
            raise ImportError(
                "Anthropic client not installed. Install with: pip install anthropic"
            )

    def _create_openai_compatible_client(self) -> Any:
        """Create OpenAI-compatible client for local servers (Ollama, LM Studio, etc.)."""
        try:
            from openai import OpenAI

            base_url = self.config.base_url or "http://localhost:11434/v1"
            if not base_url.endswith("/v1"):
                base_url = f"{base_url.rstrip('/')}/v1"

            return OpenAI(
                base_url=base_url,
                api_key="not-needed",  # Local servers often don't require keys
            )
        except ImportError:
            raise ImportError(
                "OpenAI client not installed. Install with: pip install openai"
            )

    def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Complete a chat conversation.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
                     Format: [{"role": "user", "content": "Hello"}]
            temperature: Override default temperature
            max_tokens: Override default max_tokens

        Returns:
            Assistant's response text

        Raises:
            ValueError: If provider is unsupported
            ImportError: If required client library is not installed
        """
        provider = self.config.provider.lower()
        temp = temperature if temperature is not None else self.config.temperature
        max_toks = max_tokens if max_tokens is not None else self.config.max_tokens

        if provider == "openai":
            return self._complete_openai(messages, temp, max_toks)
        elif provider == "anthropic":
            return self._complete_anthropic(messages, temp, max_toks)
        elif provider in ("ollama", "local"):
            return self._complete_openai_compatible(messages, temp, max_toks)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def _complete_openai(
        self, messages: List[Dict[str, str]], temperature: float, max_tokens: int
    ) -> str:
        """Complete using OpenAI API."""
        response = self._client.chat.completions.create(
            model=self.config.model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    def _complete_anthropic(
        self, messages: List[Dict[str, str]], temperature: float, max_tokens: int
    ) -> str:
        """Complete using Anthropic API."""
        # Anthropic uses different message format
        system_message = None
        conversation = []

        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                conversation.append(msg)

        response = self._client.messages.create(
            model=self.config.model_name,
            messages=conversation,
            system=system_message,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.content[0].text

    def _complete_openai_compatible(
        self, messages: List[Dict[str, str]], temperature: float, max_tokens: int
    ) -> str:
        """Complete using OpenAI-compatible API (Ollama, LM Studio, etc.)."""
        response = self._client.chat.completions.create(
            model=self.config.model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""


# Convenience function for quick usage
def create_llm_client(config: Optional[LLMConfig] = None) -> LLMClient:
    """Create an LLM client with optional configuration.

    Args:
        config: Optional LLMConfig. If None, loads from environment.

    Returns:
        LLMClient instance
    """
    return LLMClient(config)

