from __future__ import annotations

import math
from typing import Any


def estimate_tokens(text: str) -> int:
    """Deterministic, dependency-free token estimation.

    - Uses a conservative heuristic: tokens ~= ceil(len(chars) / 4.0).
    - This is not exact, but it's stable and suitable for eviction decisions.

    If you want exact token counting, wrap this with tiktoken or model-specific
    tokenizer at integration time.
    """

    if not text:
        return 0
    return int(math.ceil(len(text) / 4.0))


def estimate_tokens_any(value: Any) -> int:
    """Estimate tokens for common JSON-compatible structures."""

    if value is None:
        return 0
    if isinstance(value, str):
        return estimate_tokens(value)
    if isinstance(value, (int, float, bool)):
        return estimate_tokens(str(value))
    if isinstance(value, dict):
        return sum(estimate_tokens_any(k) + estimate_tokens_any(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return sum(estimate_tokens_any(v) for v in value)
    return estimate_tokens(str(value))
