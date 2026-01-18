from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from aos_context.validation import assert_valid, validate_instance
from aos_context.ledger import utc_iso


@dataclass
class MemorySearchResult:
    memory_id: str
    content: str
    confidence: float
    score: float


@dataclass
class ProposeResult:
    ok: bool
    batch_id: Optional[str] = None
    error: Optional[str] = None


@dataclass
class CommitResult:
    ok: bool
    committed_ids: Optional[List[str]] = None
    error: Optional[str] = None


class MemoryStore:
    """Abstract interface for LTM.

    Swap this with Mem0 or a real vector DB.
    """

    def search(self, query: str, *, filters: Dict[str, Any], top_k: int = 8) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def propose(self, mcrs: List[Dict[str, Any]], *, scope_filters: Dict[str, Any]) -> ProposeResult:
        raise NotImplementedError

    def commit(self, batch_id: str) -> CommitResult:
        raise NotImplementedError


class InMemoryMemoryStore(MemoryStore):
    """MVP memory store.

    - Stores memories in-process.
    - Retrieval is naive (keyword overlap) but deterministic.
    - Supports propose/commit with tombstones.
    """

    def __init__(self) -> None:
        self._mem: Dict[str, Dict[str, Any]] = {}
        self._batches: Dict[str, List[Dict[str, Any]]] = {}

    def add_memory_item(self, item: Dict[str, Any]) -> None:
        assert_valid("memory_item.v2.1.schema.json", item)
        self._mem[item["memory_id"]] = item

    def search(self, query: str, *, filters: Dict[str, Any], top_k: int = 8) -> List[Dict[str, Any]]:
        q = (query or "").lower().strip()
        q_terms = {t for t in q.split() if t}

        def pass_filters(it: Dict[str, Any]) -> bool:
            if it.get("status") != "active":
                return False
            for k, v in filters.items():
                if v is None:
                    continue
                if it.get(k) != v:
                    return False
            return True

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for it in self._mem.values():
            if not pass_filters(it):
                continue
            content = str(it.get("content", "")).lower()
            terms = set(content.split())
            overlap = len(q_terms & terms)
            conf = float(it.get("confidence", 0.0))
            score = overlap + conf
            scored.append((score, it))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [it for _, it in scored[:top_k]]

    def propose(self, mcrs: List[Dict[str, Any]], *, scope_filters: Dict[str, Any]) -> ProposeResult:
        # validate MCR schema
        for m in mcrs:
            res = validate_instance("mcr.v2.1.schema.json", m)
            if not res.ok:
                return ProposeResult(ok=False, error=f"mcr schema: {res.error}")

        batch_id = f"batch_{uuid.uuid4().hex}"
        # freeze batch with the provided scope filters attached
        staged = []
        for m in mcrs:
            mm = dict(m)
            mm["_scope_filters"] = dict(scope_filters)
            staged.append(mm)
        self._batches[batch_id] = staged
        return ProposeResult(ok=True, batch_id=batch_id)

    def commit(self, batch_id: str) -> CommitResult:
        batch = self._batches.get(batch_id)
        if not batch:
            return CommitResult(ok=False, error="unknown batch_id")

        committed: List[str] = []
        for m in batch:
            op = m.get("op")
            if op == "noop":
                continue

            # Create memory item(s)
            new_id = m.get("memory_id") or f"mem_{uuid.uuid4().hex}"
            item: Dict[str, Any] = {
                "_schema_version": "2.1",
                "memory_id": new_id,
                "type": m["type"],
                "scope": m["scope"],
                "user_id": m.get("user_id"),
                "project_id": m.get("project_id"),
                "content": m["content"],
                "confidence": float(m.get("confidence", 0.8)),
                "status": "active" if op in {"add", "supersede"} else "deprecated",
                "supersedes": m.get("supersedes", []),
                "source_refs": m.get("source_refs", []),
                "created_at": m.get("created_at") or utc_iso(),
                "updated_at": m.get("updated_at") or utc_iso(),
            }
            assert_valid("memory_item.v2.1.schema.json", item)
            self._mem[new_id] = item
            committed.append(new_id)

            # Tombstone superseded items
            if op == "supersede":
                for sid in m.get("supersedes", []) or []:
                    old = self._mem.get(sid)
                    if old:
                        old = dict(old)
                        old["status"] = "deprecated"
                        old["updated_at"] = item["updated_at"]
                        self._mem[sid] = old

            if op == "deprecate":
                target = m.get("target_memory_id")
                if target and target in self._mem:
                    old = dict(self._mem[target])
                    old["status"] = "deprecated"
                    self._mem[target] = old

        # drop batch after commit
        del self._batches[batch_id]
        return CommitResult(ok=True, committed_ids=committed)
