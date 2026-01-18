from __future__ import annotations

import uuid
from pathlib import Path

from aos_context.config import ContextConfig
from aos_context.ledger import utc_iso
from aos_context.ws_manager import WorkingSetManager


def test_optimistic_lock_rejects_mismatch(tmp_path: Path) -> None:
    ws_path = tmp_path / "state" / "working_set.v2.1.json"
    wsm = WorkingSetManager(ws_path)
    ws = wsm.create_initial(
        task_id="t",
        thread_id="th",
        run_id="r",
        objective="o",
        acceptance_criteria=[],
        constraints=[],
    )
    assert ws["_update_seq"] == 0

    # Wrong expected_seq
    r = wsm.apply_patch({"_schema_version": "2.1", "expected_seq": 99, "set": {"status": "BUSY"}})
    assert not r.ok
    assert "LOCK_ERROR" in (r.error or "")


def test_eviction_keeps_high_priority(tmp_path: Path) -> None:
    # Force very small ws_max_tokens to trigger eviction
    cfg = ContextConfig(ws_max_tokens=120, pinned_context_max_items=10)
    ws_path = tmp_path / "state" / "working_set.v2.1.json"
    wsm = WorkingSetManager(ws_path, config=cfg)
    wsm.create_initial(
        task_id="t",
        thread_id="th",
        run_id="r",
        objective="short",
        acceptance_criteria=[],
        constraints=[],
    )

    sliding = []
    # many low-priority items
    for i in range(20):
        sliding.append({"id": f"l{i}", "content": "low " * 10, "timestamp": utc_iso(), "priority": 1})
    # one high-priority item
    sliding.append({"id": "high", "content": "IMPORTANT", "timestamp": utc_iso(), "priority": 9})

    r = wsm.apply_patch({
        "_schema_version": "2.1",
        "expected_seq": 0,
        "set": {"sliding_context": sliding}
    })
    assert r.ok, r.error

    ws2 = wsm.load()
    ids = {it["id"] for it in ws2["sliding_context"]}
    assert "high" in ids
