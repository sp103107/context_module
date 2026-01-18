from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from aos_context.ledger import utc_iso
from aos_context.validation import assert_valid


@dataclass
class EpisodeResult:
    ok: bool
    episode_path: Optional[Path] = None
    episode_id: Optional[str] = None
    error: Optional[str] = None


def _summarize_events_naive(events: List[Dict[str, Any]], max_chars: int = 1200) -> str:
    """Deterministic, non-LLM episode summary.

    Replace with an LLM summarizer if desired; keep this as a safe fallback.
    """

    counts: Dict[str, int] = {}
    for e in events:
        t = str(e.get("event_type", "UNKNOWN"))
        counts[t] = counts.get(t, 0) + 1

    parts = ["Event counts:"]
    for k in sorted(counts.keys()):
        parts.append(f"- {k}: {counts[k]}")

    # Include last few notable items
    tail = events[-5:] if len(events) >= 5 else events
    parts.append("\nLast events (tail):")
    for e in tail:
        parts.append(f"- {e.get('event_type')} @ {e.get('timestamp')}")

    s = "\n".join(parts)
    return s[:max_chars]


def create_episode(
    *,
    episodes_dir: Path,
    ws_before: Dict[str, Any],
    ws_after: Dict[str, Any],
    ledger_events_since_last: List[Dict[str, Any]],
    memory_commit_ids: Optional[List[str]] = None,
    next_entry_point: str = "",
) -> EpisodeResult:
    episodes_dir.mkdir(parents=True, exist_ok=True)

    episode_id = f"ep_{uuid.uuid4().hex}"
    episode: Dict[str, Any] = {
        "_schema_version": "2.1",
        "episode_id": episode_id,
        "created_at": utc_iso(),
        "summary": _summarize_events_naive(ledger_events_since_last),
        "ws_before": ws_before,
        "ws_after": ws_after,
        "memory_commits": memory_commit_ids or [],
        "next_entry_point": next_entry_point,
    }

    try:
        assert_valid("episode.v2.1.schema.json", episode)
        path = episodes_dir / f"{episode_id}.v2.1.json"
        path.write_text(json.dumps(episode, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return EpisodeResult(ok=True, episode_path=path, episode_id=episode_id)
    except Exception as e:
        return EpisodeResult(ok=False, error=str(e))
