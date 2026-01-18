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


def test_create_resume_pack(tmp_path: Path) -> None:
    """Test create_resume_pack creates a valid zip file."""
    ws_path = tmp_path / "state" / "working_set.v2.1.json"
    wsm = WorkingSetManager(ws_path)
    ws = wsm.create_initial(
        task_id="task_123",
        thread_id="thread_456",
        run_id="run_789",
        objective="Test resume pack",
        acceptance_criteria=[],
        constraints=[],
    )

    # Create output directory
    output_dir = tmp_path / "snapshots"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create resume pack
    pack_path = wsm.create_resume_pack(output_dir)

    # Verify zip file exists
    assert pack_path.exists()
    assert pack_path.suffix == ".zip"
    assert "task_task_123" in pack_path.name

    # Verify zip contents
    import zipfile
    with zipfile.ZipFile(pack_path, "r") as zf:
        namelist = zf.namelist()
        assert "working_set.json" in namelist


def test_restore_from_pack(tmp_path: Path) -> None:
    """Test restore_from_pack restores working set from zip."""
    # Create initial WS
    ws_path = tmp_path / "original" / "state" / "working_set.v2.1.json"
    wsm = WorkingSetManager(ws_path)
    ws = wsm.create_initial(
        task_id="task_restore",
        thread_id="thread_restore",
        run_id="run_restore",
        objective="Test restore",
        acceptance_criteria=["Criterion 1"],
        constraints=["Constraint 1"],
    )

    # Create resume pack
    output_dir = tmp_path / "snapshots"
    output_dir.mkdir(parents=True, exist_ok=True)
    pack_path = wsm.create_resume_pack(output_dir)

    # Restore from pack
    restore_dir = tmp_path / "restored"
    restored_wsm = WorkingSetManager.restore_from_pack(pack_path, restore_dir)

    # Verify restored WS
    restored_ws = restored_wsm.load()
    assert restored_ws["task_id"] == "task_restore"
    assert restored_ws["objective"] == "Test restore"
    assert restored_ws["acceptance_criteria"] == ["Criterion 1"]
    assert restored_ws["constraints"] == ["Constraint 1"]


def test_restore_from_pack_invalid_schema(tmp_path: Path) -> None:
    """Test restore_from_pack rejects invalid schema."""
    import zipfile
    import json

    # Create a zip with invalid working set
    invalid_zip = tmp_path / "invalid.zip"
    with zipfile.ZipFile(invalid_zip, "w") as zf:
        invalid_ws = {"invalid": "data", "_schema_version": "2.1"}
        zf.writestr("working_set.json", json.dumps(invalid_ws))

    # Attempt restore should fail
    restore_dir = tmp_path / "restored"
    try:
        WorkingSetManager.restore_from_pack(invalid_zip, restore_dir)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Invalid working set schema" in str(e)
