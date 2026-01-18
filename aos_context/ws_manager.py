from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from aos_context.config import ContextConfig, DEFAULT_CONFIG
from aos_context.token_estimator import estimate_tokens, estimate_tokens_any
from aos_context.validation import assert_valid, validate_instance


class WSLockError(RuntimeError):
    pass


class WSSizeError(RuntimeError):
    pass


@dataclass
class ApplyPatchResult:
    ok: bool
    new_ws: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class WorkingSetManager:
    """Load/validate/update Working Set (WS) with optimistic locking and eviction."""

    def __init__(self, ws_path: Path, config: ContextConfig = DEFAULT_CONFIG) -> None:
        self.ws_path = ws_path
        self.config = config
        self.ws_path.parent.mkdir(parents=True, exist_ok=True)

    def exists(self) -> bool:
        return self.ws_path.exists()

    def load(self) -> Dict[str, Any]:
        if not self.ws_path.exists():
            raise FileNotFoundError(f"WS not found: {self.ws_path}")
        ws = json.loads(self.ws_path.read_text(encoding="utf-8"))
        assert_valid("working_set.v2.1.schema.json", ws)
        return ws

    def save(self, ws: Dict[str, Any]) -> None:
        """Atomic write: temp file + fsync + os.replace for crash safety."""
        assert_valid("working_set.v2.1.schema.json", ws)
        content = json.dumps(ws, ensure_ascii=False, indent=2) + "\n"
        # Write to temp file in same directory
        temp_path = self.ws_path.with_suffix(".tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            # Atomic replace (cross-platform)
            os.replace(str(temp_path), str(self.ws_path))
            # Sync directory (best effort, may not be available on all platforms)
            try:
                dir_fd = os.open(str(self.ws_path.parent), os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except (OSError, AttributeError):
                pass  # Best effort only
        except Exception:
            # Clean up temp file on error
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            raise

    def create_initial(
        self,
        *,
        task_id: str,
        thread_id: str,
        run_id: str,
        objective: str,
        acceptance_criteria: List[str],
        constraints: List[str],
        current_stage: str = "BOOT",
    ) -> Dict[str, Any]:
        ws: Dict[str, Any] = {
            "_schema_version": "2.1",
            "_update_seq": 0,
            "task_id": task_id,
            "thread_id": thread_id,
            "run_id": run_id,
            "status": "BOOT",
            "objective": objective,
            "acceptance_criteria": acceptance_criteria,
            "current_stage": current_stage,
            "next_action": "",
            "constraints": constraints,
            "artifact_refs": [],
            "blockers": [],
            "last_action_summary": "",
            "pinned_context": [],
            "sliding_context": [],
        }
        self._enforce_limits(ws)
        self.save(ws)
        return ws

    def apply_patch(self, patch: Dict[str, Any]) -> ApplyPatchResult:
        """Apply a ws_patch with optimistic lock. Returns new ws."""

        # Validate patch schema first (reject unknown patch fields early)
        res = validate_instance("ws_patch.v2.1.schema.json", patch)
        if not res.ok:
            return ApplyPatchResult(ok=False, error=f"patch schema: {res.error}")

        current = self.load()
        expected_seq = int(patch["expected_seq"])
        if expected_seq != int(current["_update_seq"]):
            return ApplyPatchResult(
                ok=False,
                error=f"LOCK_ERROR expected_seq={expected_seq} current_seq={current['_update_seq']}",
            )

        new_ws = copy.deepcopy(current)

        # Apply replacements (simple, deterministic)
        updates = patch.get("set", {})
        for k, v in updates.items():
            if k in {"_schema_version", "_update_seq", "task_id", "thread_id", "run_id", "objective"}:
                return ApplyPatchResult(ok=False, error=f"immutable field in patch: {k}")
            new_ws[k] = v

        # Enforce pinned_context max and eviction
        try:
            self._enforce_limits(new_ws)
        except WSSizeError as e:
            return ApplyPatchResult(ok=False, error=f"WS_SIZE_ERROR: {e}")

        # Increment sequence and persist
        new_ws["_update_seq"] = int(current["_update_seq"]) + 1

        try:
            self.save(new_ws)
        except Exception as e:
            return ApplyPatchResult(ok=False, error=f"save: {e}")

        return ApplyPatchResult(ok=True, new_ws=new_ws)

    def _base_load_tokens(self, ws: Dict[str, Any]) -> int:
        obj = estimate_tokens(str(ws.get("objective", "")))
        ac = sum(estimate_tokens(str(s)) for s in (ws.get("acceptance_criteria", []) or []))
        cons = sum(estimate_tokens(str(s)) for s in (ws.get("constraints", []) or []))

        pinned = 0
        for it in (ws.get("pinned_context", []) or []):
            if isinstance(it, dict):
                pinned += estimate_tokens(str(it.get("content", "")))
            else:
                pinned += estimate_tokens(str(it))

        # Small constant overhead for headings/formatting in the Context Brief.
        overhead = 25
        return obj + ac + cons + pinned + overhead

    def _total_tokens_estimate(self, ws: Dict[str, Any]) -> int:
        total = self._base_load_tokens(ws)

        total += estimate_tokens(str(ws.get("status", "")))
        total += estimate_tokens(str(ws.get("current_stage", "")))
        total += estimate_tokens(str(ws.get("next_action", "")))
        total += estimate_tokens(str(ws.get("last_action_summary", "")))
        total += sum(estimate_tokens(str(s)) for s in (ws.get("blockers", []) or []))

        for it in (ws.get("sliding_context", []) or []):
            if isinstance(it, dict):
                # Primary contribution to prompt size is the content.
                total += estimate_tokens(str(it.get("content", "")))
                # Small overhead for rendering pri/ts.
                total += 6
            else:
                total += estimate_tokens(str(it))

        return total

    def _enforce_limits(self, ws: Dict[str, Any]) -> None:
        # Cap pinned_context items deterministically (keep most recent = last N)
        pinned = ws.get("pinned_context", [])
        if isinstance(pinned, list) and len(pinned) > self.config.pinned_context_max_items:
            # Keep last N items (most recent by insertion order)
            ws["pinned_context"] = pinned[-self.config.pinned_context_max_items:]

        base = self._base_load_tokens(ws)
        if base > self.config.ws_max_tokens:
            raise WSSizeError(f"base_load_tokens={base} exceeds ws_max_tokens={self.config.ws_max_tokens}")

        # Rebuild sliding_context under budget (priority desc, timestamp desc)
        sliding = ws.get("sliding_context", [])
        if not isinstance(sliding, list):
            sliding = []

        def sort_key(item: Any):
            pri = 0
            ts = ""
            if isinstance(item, dict):
                pri = int(item.get("priority", 0))
                ts = str(item.get("timestamp", ""))
            return (pri, ts)

        sliding_sorted = sorted(sliding, key=sort_key, reverse=True)

        # Budget remaining after pinned/base
        remaining = max(0, self.config.ws_max_tokens - base)

        kept: List[Any] = []
        used = 0
        for item in sliding_sorted:
            if isinstance(item, dict):
                t = estimate_tokens(str(item.get("content", ""))) + 6
            else:
                t = estimate_tokens(str(item))
            if used + t <= remaining:
                kept.append(item)
                used += t

        ws["sliding_context"] = kept

        # Final sanity check
        total = self._total_tokens_estimate(ws)
        if total > self.config.ws_max_tokens:
            raise WSSizeError(f"total_tokens={total} exceeds ws_max_tokens={self.config.ws_max_tokens}")

        # Validate after enforcement (ensures strictness)
        assert_valid("working_set.v2.1.schema.json", ws)
