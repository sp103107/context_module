from __future__ import annotations

import copy
import json
import os
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from aos_context.config import ContextConfig, DEFAULT_CONFIG
from aos_context.token_estimator import estimate_tokens
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

    def create_resume_pack(self, output_dir: Path) -> Path:
        """Create a zipped snapshot of the current task state.

        Creates a timestamped zip file containing:
        - working_set.json (current state)
        - run.jsonl (ledger audit trail, if available)

        Args:
            output_dir: Directory where the zip file will be created

        Returns:
            Path to the generated zip file

        Raises:
            FileNotFoundError: If working set doesn't exist
            ValueError: If output_dir cannot be created
        """
        if not self.exists():
            raise FileNotFoundError(f"Working set not found: {self.ws_path}")

        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        # Load current WS to get task ID for naming
        ws = self.load()
        task_id = ws.get("task_id", "unknown")

        # Generate timestamp for unique filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"task_{task_id}_resume_{timestamp}.zip"
        zip_path = output_dir / zip_filename

        # Find ledger path (typically in same run directory structure)
        # ws_path is: runs/{run_id}/state/working_set.v2.1.json
        # ledger is: runs/{run_id}/ledger/run.v2.1.jsonl
        run_dir = self.ws_path.parent.parent  # Up from state/ to runs/{run_id}/
        ledger_path = run_dir / "ledger" / "run.v2.1.jsonl"

        # Create zip archive
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Add working set (always required)
            zf.write(
                self.ws_path,
                arcname="working_set.json"
            )

            # Add ledger if it exists (proceed if missing)
            if ledger_path.exists():
                zf.write(ledger_path, arcname="run.jsonl")
            # Note: Proceed without ledger if missing (non-critical)

        return zip_path

    @classmethod
    def restore_from_pack(
        cls, zip_path: Path, target_dir: Path
    ) -> "WorkingSetManager":
        """Restore an agent from a resume pack zip file.

        Class method to boot an agent from a zip file snapshot.
        Validates the working set schema before restoring.

        Args:
            zip_path: Path to the resume pack zip file
            target_dir: Directory where files will be extracted and restored

        Returns:
            New WorkingSetManager instance pointing to restored data

        Raises:
            FileNotFoundError: If zip_path doesn't exist
            ValueError: If working_set.json is missing or invalid
            zipfile.BadZipFile: If zip file is corrupted
        """
        if not zip_path.exists():
            raise FileNotFoundError(f"Resume pack not found: {zip_path}")

        # Ensure target directory exists
        target_dir.mkdir(parents=True, exist_ok=True)

        # Extract zip contents
        with zipfile.ZipFile(zip_path, "r") as zf:
            # Validate zip structure
            namelist = zf.namelist()
            if "working_set.json" not in namelist:
                raise ValueError(
                    "Resume pack missing required file: working_set.json"
                )

            # Extract all files
            zf.extractall(target_dir)

        # Load and validate working set
        ws_path = target_dir / "working_set.json"
        if not ws_path.exists():
            raise ValueError(
                f"working_set.json not found after extraction in {target_dir}"
            )

        # Validate schema before creating manager
        try:
            ws_data = json.loads(ws_path.read_text(encoding="utf-8"))
            assert_valid("working_set.v2.1.schema.json", ws_data)
        except Exception as e:
            msg = f"Invalid working set schema in resume pack: {e}"
            raise ValueError(msg) from e

        # Create WorkingSetManager instance pointing to restored data
        # Note: We use the extracted path directly
        return cls(ws_path)
