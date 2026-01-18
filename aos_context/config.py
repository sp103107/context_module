from __future__ import annotations

from dataclasses import dataclass


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


DEFAULT_CONFIG = ContextConfig()
