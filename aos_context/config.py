from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LLMConfig:
    """Configuration for LLM provider (local or cloud).

    Supports OpenAI, Anthropic, Ollama, and local OpenAI-compatible servers.
    """

    provider: str = "openai"  # "openai", "anthropic", "ollama", "local"
    base_url: str | None = None  # For local servers (e.g., "http://localhost:1234/v1")
    model_name: str = "gpt-4o"
    api_key: str | None = None
    temperature: float = 0.7
    max_tokens: int = 2000

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Create LLMConfig from environment variables.

        Environment variables:
        - LLM_PROVIDER: Provider name (default: "openai")
        - LLM_BASE_URL: Base URL for local servers (optional)
        - LLM_MODEL_NAME: Model name (default: "gpt-4o")
        - LLM_API_KEY: API key (optional, can also use OPENAI_API_KEY, ANTHROPIC_API_KEY)
        - LLM_TEMPERATURE: Temperature (default: 0.7)
        - LLM_MAX_TOKENS: Max tokens (default: 2000)
        """
        provider = os.environ.get("LLM_PROVIDER", "openai")
        base_url = os.environ.get("LLM_BASE_URL")
        model_name = os.environ.get("LLM_MODEL_NAME", "gpt-4o")
        
        # Try provider-specific API key, fall back to generic
        api_key = os.environ.get("LLM_API_KEY")
        if not api_key:
            if provider == "openai":
                api_key = os.environ.get("OPENAI_API_KEY")
            elif provider == "anthropic":
                api_key = os.environ.get("ANTHROPIC_API_KEY")
        
        temperature = float(os.environ.get("LLM_TEMPERATURE", "0.7"))
        max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "2000"))
        
        return cls(
            provider=provider,
            base_url=base_url,
            model_name=model_name,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )


@dataclass(frozen=True)
class ContextConfig:
    """Runtime configuration for context management.

    Keep this small and serializable. Store full config in RL RUN_START payload.
    """

    schema_version: str = "2.1"

    # Working Set limits
    ws_max_tokens: int = 2000
    pinned_context_max_items: int = 10

    # Drift thresholds (optional vector drift gate)
    drift_warn_threshold: float = 0.60
    drift_block_threshold: float = 0.50

    # Milestone defaults
    milestone_step_cap: int = 10
    milestone_error_cap: int = 3

    # LLM configuration (optional)
    llm_config: LLMConfig | None = field(default_factory=LLMConfig.from_env)


DEFAULT_CONFIG = ContextConfig()
