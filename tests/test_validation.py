from __future__ import annotations

import uuid

from aos_context.ledger import utc_iso
from aos_context.validation import validate_instance


def test_working_set_schema_accepts_minimal() -> None:
    ws = {
        "_schema_version": "2.1",
        "_update_seq": 0,
        "task_id": f"task_{uuid.uuid4().hex}",
        "thread_id": f"thread_{uuid.uuid4().hex}",
        "run_id": f"run_{uuid.uuid4().hex}",
        "status": "BOOT",
        "objective": "demo",
        "acceptance_criteria": [],
        "current_stage": "BOOT",
        "next_action": "",
        "constraints": [],
        "artifact_refs": [],
        "blockers": [],
        "last_action_summary": "",
        "pinned_context": [],
        "sliding_context": [],
    }
    r = validate_instance("working_set.v2.1.schema.json", ws)
    assert r.ok, r.error


def test_ws_patch_schema_accepts_set() -> None:
    patch = {
        "_schema_version": "2.1",
        "expected_seq": 0,
        "set": {"status": "BUSY", "next_action": "do thing"},
    }
    r = validate_instance("ws_patch.v2.1.schema.json", patch)
    assert r.ok, r.error


def test_ledger_event_schema_accepts_run_start() -> None:
    e = {
        "_schema_version": "2.1",
        "event_id": str(uuid.uuid4()),
        "parent_event_id": None,
        "sequence_id": 1,
        "event_type": "RUN_START",
        "timestamp": utc_iso(),
        "writer_id": "test",
        "task_id": "t",
        "thread_id": "th",
        "run_id": "r",
        "payload": {"config": {"ws_max_tokens": 2000}},
    }
    r = validate_instance("ledger_event.v2.1.schema.json", e)
    assert r.ok, r.error
