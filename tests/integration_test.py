"""Integration Test - Verify package works as installed library.

This test simulates an external agent using the aos_context package.
It verifies that all major components work together correctly.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from aos_context.config import LLMConfig
from aos_context.llm_adapter import LLMClient
from aos_context.ws_manager import WorkingSetManager


def run_integration_test() -> bool:
    """Run comprehensive integration test.

    Returns:
        True if all tests pass, False otherwise
    """
    print("=" * 60)
    print("AoS Context Module - Integration Test")
    print("=" * 60)
    print()

    # Create temp directory for entire test
    tmpdir = tempfile.mkdtemp()
    tmp_path = Path(tmpdir)

    try:
        # Step 1: Initialize WorkingSetManager
        print("Step 1: Initializing WorkingSetManager...")
        try:
            ws_path = tmp_path / "state" / "working_set.v2.1.json"
            wsm = WorkingSetManager(ws_path)
            print("  [OK] WorkingSetManager initialized")
        except Exception as e:
            print(f"  [FAIL] Failed: {e}")
            return False

        # Step 2: Boot a new run
        print("\nStep 2: Booting new run...")
        try:
            ws = wsm.create_initial(
                task_id="integration_test_task",
                thread_id="integration_thread",
                run_id="integration_run",
                objective="Integration Test Run - Verify package functionality",
                acceptance_criteria=[
                    "All imports work",
                    "WorkingSetManager functions",
                    "LLM adapter works",
                    "Snapshot creation works",
                ],
                constraints=["Must complete without errors"],
            )
            print(f"  [OK] Run booted: {ws['run_id']}")
            print(f"  [OK] Status: {ws['status']}")
            print(f"  [OK] Update Sequence: {ws['_update_seq']}")
        except Exception as e:
            print(f"  [FAIL] Failed: {e}")
            return False

        # Step 3: Load and verify context
        print("\nStep 3: Loading context...")
        try:
            loaded_ws = wsm.load()
            assert loaded_ws["run_id"] == "integration_run"
            assert (
                loaded_ws["objective"]
                == "Integration Test Run - Verify package functionality"
            )
            print("  [OK] Context loaded successfully")
            print(f"  [OK] Objective: {loaded_ws['objective']}")
        except Exception as e:
            print(f"  [FAIL] Failed: {e}")
            return False

        # Step 4: Update context with patch
        print("\nStep 4: Updating context with patch...")
        try:
            current_seq = loaded_ws["_update_seq"]
            patch = {
                "_schema_version": "2.1",
                "expected_seq": current_seq,
                "set": {
                    "status": "BUSY",
                    "next_action": "Running integration tests",
                    "current_stage": "TEST",
                },
            }
            result = wsm.apply_patch(patch)
            if result.ok:
                print("  [OK] Patch applied successfully")
                print(f"  [OK] New status: {result.new_ws['status']}")
                print(f"  [OK] New update sequence: {result.new_ws['_update_seq']}")
            else:
                print(f"  [FAIL] Patch failed: {result.error}")
                return False
        except Exception as e:
            print(f"  [FAIL] Failed: {e}")
            return False

        # Step 5: Initialize LLM Client (with local/ollama provider)
        print("\nStep 5: Initializing LLM Client...")
        try:
            # Use local provider for testing (doesn't require API keys)
            llm_config = LLMConfig(
                provider="local",
                base_url="http://localhost:11434/v1",  # Ollama default
                model_name="llama3",
                api_key=None,
            )
            client = LLMClient(llm_config)
            print("  [OK] LLMClient initialized")
            print(f"  [OK] Provider: {llm_config.provider}")
            print(f"  [OK] Model: {llm_config.model_name}")
        except Exception as e:
            print(f"  [WARN] LLM Client initialization warning: {e}")
            print(
                "  [INFO] This is OK if Ollama is not running. Skipping LLM test."
            )
            client = None

        # Step 6: Test LLM completion (if client available)
        if client:
            print("\nStep 6: Testing LLM completion...")
            try:
                messages = [
                    {"role": "user", "content": "Say 'Integration test successful'"}
                ]
                response = client.complete(messages, temperature=0.7, max_tokens=50)
                print(f"  [OK] LLM response received: {response[:50]}...")
            except Exception as e:
                print(f"  [WARN] LLM completion warning: {e}")
                print(
                    "  [INFO] This is OK if Ollama/local server is not running."
                )
        else:
            print("\nStep 6: Skipping LLM test (client not available)")

    # Step 7: Create snapshot
        print("\nStep 7: Creating snapshot...")
        try:
            snapshot_dir = tmp_path / "snapshots"
            snapshot_dir.mkdir(exist_ok=True)
            pack_path = wsm.create_resume_pack(snapshot_dir)
            print(f"  [OK] Snapshot created: {pack_path.name}")
            assert pack_path.exists(), "Snapshot file should exist"
            print(f"  [OK] Snapshot file verified")
        except Exception as e:
            print(f"  [FAIL] Failed: {e}")
            return False

        # Step 8: Test restore from pack
        print("\nStep 8: Testing restore from snapshot...")
        try:
            restore_dir = tmp_path / "restored"
            restored_wsm = WorkingSetManager.restore_from_pack(
                pack_path, restore_dir
            )
            restored_ws = restored_wsm.load()
            assert restored_ws["run_id"] == "integration_run"
            assert (
                restored_ws["objective"]
                == "Integration Test Run - Verify package functionality"
            )
            print("  [OK] Snapshot restored successfully")
            print(f"  [OK] Restored objective: {restored_ws['objective']}")
        except Exception as e:
            print(f"  [FAIL] Failed: {e}")
            return False

        print("\n" + "=" * 60)
        print("[SUCCESS] Integration Test Passed")
        print("=" * 60)
        return True

    finally:
        # Clean up temp directory
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass


if __name__ == "__main__":
    success = run_integration_test()
    exit(0 if success else 1)
