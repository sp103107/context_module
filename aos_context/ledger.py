from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from aos_context.validation import assert_valid

try:
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore


@dataclass
class LedgerAppendResult:
    ok: bool
    sequence_id: Optional[int] = None
    error: Optional[str] = None


class FileLedger:
    """Append-only JSONL ledger with optional POSIX file locking."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("", encoding="utf-8")

    def _lock(self, fh) -> None:
        if fcntl is None:
            return
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)

    def _unlock(self, fh) -> None:
        if fcntl is None:
            return
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def append(self, event: Dict[str, Any]) -> LedgerAppendResult:
        """Validate and append a ledger_event.v2.1.json line.

        Expects caller to set sequence_id. If missing, we assign one by counting
        lines under lock (O(n), acceptable for MVP).
        """

        try:
            assert_valid("ledger_event.v2.1.schema.json", event)
        except Exception as e:
            return LedgerAppendResult(ok=False, error=f"schema: {e}")

        try:
            with self.path.open("a+", encoding="utf-8") as fh:
                self._lock(fh)

                # Assign sequence_id if absent
                if event.get("sequence_id") is None:
                    fh.seek(0)
                    count = 0
                    for _ in fh:
                        count += 1
                    event["sequence_id"] = count + 1

                fh.seek(0, os.SEEK_END)
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
                fh.flush()
                os.fsync(fh.fileno())

                seq = int(event["sequence_id"])
                self._unlock(fh)

            return LedgerAppendResult(ok=True, sequence_id=seq)
        except Exception as e:
            return LedgerAppendResult(ok=False, error=str(e))


def utc_iso() -> str:
    """UTC timestamp (ISO 8601) without external deps."""

    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
