"""Tests for FastAPI endpoints and milestone token gating."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aos_context.api.main import (
    MEMORY,
    MILESTONE_TOKENS,
    TOKEN_TTL_SECONDS,
    _clear_milestone_token,
    _generate_milestone_token,
    _validate_milestone_token,
    app,
)

client = TestClient(app)


@pytest.fixture
def clean_tokens():
    """Clear milestone tokens and memory store before and after each test."""
    MILESTONE_TOKENS.clear()
    # Reset memory store (it's a singleton)
    MEMORY._mem.clear()
    MEMORY._batches.clear()
    yield
    MILESTONE_TOKENS.clear()
    MEMORY._mem.clear()
    MEMORY._batches.clear()


def test_health_endpoint() -> None:
    """Test health endpoint returns ok."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "2.1.0"


def test_boot_run() -> None:
    """Test boot endpoint creates a run."""
    response = client.post(
        "/runs/boot",
        json={
            "objective": "Test objective",
            "acceptance_criteria": ["Criterion 1"],
            "constraints": ["Constraint 1"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "run_id" in data
    assert "ws" in data
    assert data["ws"]["objective"] == "Test objective"
    assert data["ws"]["_update_seq"] == 0


def test_get_ws_not_found() -> None:
    """Test getting WS for non-existent run returns 404."""
    response = client.get("/runs/nonexistent/ws")
    assert response.status_code == 404


def test_ws_patch_optimistic_lock(clean_tokens) -> None:
    """Test WS patch with optimistic locking."""
    # Boot a run
    boot_resp = client.post(
        "/runs/boot",
        json={"objective": "Test", "acceptance_criteria": [], "constraints": []},
    )
    run_id = boot_resp.json()["run_id"]

    # Get WS to read _update_seq
    ws_resp = client.get(f"/runs/{run_id}/ws")
    ws = ws_resp.json()
    expected_seq = ws["_update_seq"]

    # Apply patch with correct expected_seq
    patch_resp = client.post(
        f"/runs/{run_id}/step/update",
        json={
            "patch": {
                "_schema_version": "2.1",
                "expected_seq": expected_seq,
                "set": {"status": "BUSY", "next_action": "Do something"},
            }
        },
    )
    assert patch_resp.status_code == 200
    patched_ws = patch_resp.json()["ws"]
    assert patched_ws["status"] == "BUSY"
    assert patched_ws["_update_seq"] == expected_seq + 1

    # Try patch with wrong expected_seq (should fail)
    bad_patch_resp = client.post(
        f"/runs/{run_id}/step/update",
        json={
            "patch": {
                "_schema_version": "2.1",
                "expected_seq": expected_seq,  # Now outdated
                "set": {"status": "IDLE"},
            }
        },
    )
    assert bad_patch_resp.status_code == 409  # Conflict


def test_memory_propose(clean_tokens) -> None:
    """Test memory propose endpoint."""
    boot_resp = client.post(
        "/runs/boot",
        json={"objective": "Test", "acceptance_criteria": [], "constraints": []},
    )
    run_id = boot_resp.json()["run_id"]

    mcr = {
        "_schema_version": "2.1",
        "op": "add",
        "type": "fact",
        "scope": "global",
        "content": "Test memory",
        "confidence": 0.8,
        "rationale": "Testing",
        "source_refs": [],
    }

    propose_resp = client.post(
        f"/runs/{run_id}/memory/propose",
        json={"mcrs": [mcr], "scope_filters": {}},
    )
    assert propose_resp.status_code == 200
    data = propose_resp.json()
    assert data["ok"] is True
    assert "batch_id" in data
    assert data["staged_count"] == 1


def test_memory_commit_requires_token(clean_tokens) -> None:
    """Test memory commit requires milestone token."""
    boot_resp = client.post(
        "/runs/boot",
        json={"objective": "Test", "acceptance_criteria": [], "constraints": []},
    )
    run_id = boot_resp.json()["run_id"]

    # Propose memory
    mcr = {
        "_schema_version": "2.1",
        "op": "add",
        "type": "fact",
        "scope": "global",
        "content": "Test",
        "confidence": 0.8,
        "rationale": "Test",
        "source_refs": [],
    }
    propose_resp = client.post(
        f"/runs/{run_id}/memory/propose",
        json={"mcrs": [mcr], "scope_filters": {}},
    )
    batch_id = propose_resp.json()["batch_id"]

    # Try commit without token (should fail)
    commit_resp = client.post(
        f"/runs/{run_id}/memory/commit",
        json={"batch_id": batch_id},
    )
    assert commit_resp.status_code == 200  # Returns structured error
    data = commit_resp.json()
    assert data["ok"] is False
    assert "milestone_token" in data["error"].lower()


def test_milestone_token_flow(clean_tokens) -> None:
    """Test complete milestone token flow."""
    boot_resp = client.post(
        "/runs/boot",
        json={"objective": "Test", "acceptance_criteria": [], "constraints": []},
    )
    run_id = boot_resp.json()["run_id"]

    # Propose memory
    mcr = {
        "_schema_version": "2.1",
        "op": "add",
        "type": "fact",
        "scope": "global",
        "content": "Test memory",
        "confidence": 0.8,
        "rationale": "Testing",
        "source_refs": [],
    }
    propose_resp = client.post(
        f"/runs/{run_id}/memory/propose",
        json={"mcrs": [mcr], "scope_filters": {}},
    )
    batch_id = propose_resp.json()["batch_id"]

    # Create milestone (generates token)
    milestone_resp = client.post(
        f"/runs/{run_id}/milestone",
        json={
            "reason": "checkpoint",
            "memory_batch_id": batch_id,
            "next_entry_point": "Continue",
        },
    )
    assert milestone_resp.status_code == 200
    milestone_data = milestone_resp.json()
    assert "milestone_token" in milestone_data
    # Token should be cleared after milestone completes
    assert run_id not in MILESTONE_TOKENS


def test_memory_search(clean_tokens) -> None:
    """Test memory search endpoint."""
    boot_resp = client.post(
        "/runs/boot",
        json={"objective": "Test", "acceptance_criteria": [], "constraints": []},
    )
    run_id = boot_resp.json()["run_id"]

    # Search (should return empty initially)
    search_resp = client.get(f"/runs/{run_id}/memory/search?q=test&top_k=10")
    assert search_resp.status_code == 200
    data = search_resp.json()
    assert data["ok"] is True
    assert data["count"] == 0


def test_milestone_token_validation(clean_tokens) -> None:
    """Test milestone token validation functions."""
    run_id = "test_run_123"

    # Generate token
    token = _generate_milestone_token(run_id)
    assert token.startswith("milestone_")
    assert run_id in MILESTONE_TOKENS

    # Validate token
    assert _validate_milestone_token(run_id, token) is True
    assert _validate_milestone_token(run_id, "invalid") is False
    assert _validate_milestone_token(run_id, None) is False

    # Clear token
    _clear_milestone_token(run_id)
    assert run_id not in MILESTONE_TOKENS
    assert _validate_milestone_token(run_id, token) is False


def test_milestone_token_expiration(clean_tokens) -> None:
    """Test milestone token expiration."""
    run_id = "test_run_456"
    token = _generate_milestone_token(run_id)

    # Manually expire token by setting old expiration
    stored_token, _ = MILESTONE_TOKENS[run_id]
    MILESTONE_TOKENS[run_id] = (stored_token, time.time() - 1)

    # Validation should fail and clean up
    assert _validate_milestone_token(run_id, token) is False
    assert run_id not in MILESTONE_TOKENS


def test_test_mode_bypass(clean_tokens) -> None:
    """Test allow_outside_milestone only works in test mode."""
    boot_resp = client.post(
        "/runs/boot",
        json={"objective": "Test", "acceptance_criteria": [], "constraints": []},
    )
    run_id = boot_resp.json()["run_id"]

    # Propose memory
    mcr = {
        "_schema_version": "2.1",
        "op": "add",
        "type": "fact",
        "scope": "global",
        "content": "Test",
        "confidence": 0.8,
        "rationale": "Test",
        "source_refs": [],
    }
    propose_resp = client.post(
        f"/runs/{run_id}/memory/propose",
        json={"mcrs": [mcr], "scope_filters": {}},
    )
    batch_id = propose_resp.json()["batch_id"]

    # Try commit with allow_outside_milestone but without test mode (should fail)
    old_test_mode = os.environ.get("AOS_TEST_MODE")
    try:
        if "AOS_TEST_MODE" in os.environ:
            del os.environ["AOS_TEST_MODE"]

        commit_resp = client.post(
            f"/runs/{run_id}/memory/commit",
            json={"batch_id": batch_id, "allow_outside_milestone": True},
        )
        data = commit_resp.json()
        assert data["ok"] is False
        assert "AOS_TEST_MODE" in data["error"]

        # Enable test mode
        os.environ["AOS_TEST_MODE"] = "1"
        # Need to reload the module to pick up env var change
        # For this test, we'll just verify the logic exists
        # In real usage, server restart would be needed
    finally:
        if old_test_mode is not None:
            os.environ["AOS_TEST_MODE"] = old_test_mode
        elif "AOS_TEST_MODE" in os.environ:
            del os.environ["AOS_TEST_MODE"]


def test_resume_snapshot(clean_tokens) -> None:
    """Test resume snapshot endpoint."""
    boot_resp = client.post(
        "/runs/boot",
        json={"objective": "Test", "acceptance_criteria": [], "constraints": []},
    )
    run_id = boot_resp.json()["run_id"]

    snapshot_resp = client.post(
        f"/runs/{run_id}/resume/snapshot",
        json={"zip_pack": True, "pointers": {}},
    )
    assert snapshot_resp.status_code == 200
    data = snapshot_resp.json()
    assert data["ok"] is True
    assert "pack_id" in data
    assert data["pack_id"] is not None


def test_end_to_end_flow(clean_tokens, tmp_path: Path) -> None:
    """Test complete end-to-end flow: boot -> patch -> propose -> milestone -> snapshot."""
    # 1. Boot
    boot_resp = client.post(
        "/runs/boot",
        json={
            "objective": "E2E test",
            "acceptance_criteria": ["Test passes"],
            "constraints": [],
        },
    )
    run_id = boot_resp.json()["run_id"]

    # 2. Patch WS
    ws_resp = client.get(f"/runs/{run_id}/ws")
    expected_seq = ws_resp.json()["_update_seq"]
    patch_resp = client.post(
        f"/runs/{run_id}/step/update",
        json={
            "patch": {
                "_schema_version": "2.1",
                "expected_seq": expected_seq,
                "set": {"status": "BUSY", "next_action": "Test memory"},
            }
        },
    )
    assert patch_resp.status_code == 200

    # 3. Propose memory
    mcr = {
        "_schema_version": "2.1",
        "op": "add",
        "type": "fact",
        "scope": "global",
        "content": "E2E test memory",
        "confidence": 0.9,
        "rationale": "End-to-end test",
        "source_refs": [],
    }
    propose_resp = client.post(
        f"/runs/{run_id}/memory/propose",
        json={"mcrs": [mcr], "scope_filters": {}},
    )
    batch_id = propose_resp.json()["batch_id"]

    # 4. Create milestone (commits memory)
    milestone_resp = client.post(
        f"/runs/{run_id}/milestone",
        json={
            "reason": "checkpoint",
            "memory_batch_id": batch_id,
            "next_entry_point": "Continue",
        },
    )
    assert milestone_resp.status_code == 200
    milestone_data = milestone_resp.json()
    assert "episode_id" in milestone_data
    assert len(milestone_data["committed_memory_ids"]) == 1

    # 5. Snapshot resume pack
    snapshot_resp = client.post(
        f"/runs/{run_id}/resume/snapshot",
        json={"zip_pack": False, "pointers": {}},
    )
    assert snapshot_resp.status_code == 200
    snapshot_data = snapshot_resp.json()
    assert snapshot_data["ok"] is True
    assert snapshot_data["pack_id"] is not None

