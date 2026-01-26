"""Agent Loop Script - Demonstrates end-to-end context management workflow.

This script simulates an agent that:
1. Boots a run
2. Fetches and updates state
3. Handles optimistic locking conflicts
4. Proposes and commits memories
5. Creates snapshots

Run this in a separate terminal while server.py is running.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import requests


class StateConflictError(Exception):
    """Raised when a state update conflicts (409 Conflict)."""

    pass


class AgentClient:
    """Simple client wrapper for the AoS Context API."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip("/")

    def boot_run(
        self,
        objective: str,
        acceptance_criteria: Optional[List[str]] = None,
        constraints: Optional[List[str]] = None,
        task_id: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Boot a new run.

        Args:
            objective: Task objective
            acceptance_criteria: List of acceptance criteria
            constraints: List of constraints
            task_id: Optional task ID
            thread_id: Optional thread ID

        Returns:
            Response with run_id and status
        """
        resp = requests.post(
            f"{self.base_url}/runs",
            json={
                "objective": objective,
                "acceptance_criteria": acceptance_criteria or [],
                "constraints": constraints or [],
                "task_id": task_id,
                "thread_id": thread_id,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def get_state(self, run_id: str) -> Dict[str, Any]:
        """Get current working set state.

        Args:
            run_id: Run identifier

        Returns:
            Full working set JSON
        """
        resp = requests.get(f"{self.base_url}/runs/{run_id}")
        resp.raise_for_status()
        return resp.json()

    def update_state(
        self, run_id: str, expected_seq: int, patch: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update working set state with optimistic locking.

        Args:
            run_id: Run identifier
            expected_seq: Expected sequence number (for optimistic lock)
            patch: Fields to update

        Returns:
            Updated working set

        Raises:
            StateConflictError: If 409 Conflict occurs (state changed)
        """
        resp = requests.patch(
            f"{self.base_url}/runs/{run_id}",
            json={"patch": patch, "expected_seq": expected_seq},
        )

        if resp.status_code == 409:
            raise StateConflictError("State has changed. Reload and retry.")

        resp.raise_for_status()
        return resp.json()

    def propose_memory(
        self, run_id: str, mcrs: List[Dict[str, Any]], scope_filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Propose memory change requests for staging.

        Args:
            run_id: Run identifier
            mcrs: List of Memory Change Requests
            scope_filters: Optional scope filters

        Returns:
            Response with batch_id
        """
        resp = requests.post(
            f"{self.base_url}/runs/{run_id}/memory/propose",
            json={"mcrs": mcrs, "scope_filters": scope_filters or {}},
        )
        resp.raise_for_status()
        return resp.json()

    def commit_memory(self, run_id: str, batch_id: str) -> Dict[str, Any]:
        """Commit staged memory batch.

        Args:
            run_id: Run identifier
            batch_id: Batch ID from propose_memory

        Returns:
            Response with committed memory IDs
        """
        resp = requests.post(
            f"{self.base_url}/runs/{run_id}/memory/commit",
            json={"batch_id": batch_id},
        )
        resp.raise_for_status()
        return resp.json()

    def snapshot(self, run_id: str) -> Dict[str, Any]:
        """Create a resume pack snapshot.

        Args:
            run_id: Run identifier

        Returns:
            Response with pack path
        """
        resp = requests.post(f"{self.base_url}/runs/{run_id}/snapshot")
        resp.raise_for_status()
        return resp.json()


def mock_llm_think(state: Dict[str, Any], step: int) -> Dict[str, Any]:
    """Simulate LLM thinking process.

    Args:
        state: Current working set state
        step: Current step number

    Returns:
        Dictionary with updates to apply
    """
    status = state.get("status", "BOOT")
    current_stage = state.get("current_stage", "BOOT")
    next_action = state.get("next_action", "")

    updates: Dict[str, Any] = {}

    if status == "BOOT":
        # Initial planning phase
        updates["status"] = "BUSY"
        updates["current_stage"] = "PLAN"
        updates["next_action"] = "Break down the research task into steps"
        updates["last_action_summary"] = "Initialized research task"

    elif status == "BUSY":
        # Working phase
        if current_stage == "PLAN":
            updates["current_stage"] = "RESEARCH"
            updates["next_action"] = f"Research step {step}: Gather information"
            updates["last_action_summary"] = f"Completed planning, starting research step {step}"

        elif current_stage == "RESEARCH":
            if step >= 5:
                # Simulate completion
                updates["status"] = "DONE"
                updates["current_stage"] = "COMPLETE"
                updates["next_action"] = "Task completed successfully"
                updates["last_action_summary"] = "Research completed"
            else:
                updates["next_action"] = f"Research step {step + 1}: Continue gathering information"
                updates["last_action_summary"] = f"Completed research step {step}"

    return updates


def run_loop(objective: str, max_steps: int = 10) -> None:
    """Run the agent loop demonstrating the full workflow.

    Args:
        objective: Task objective
        max_steps: Maximum number of loop iterations
    """
    client = AgentClient()

    print("=" * 60)
    print("AoS Context Agent Loop Demo")
    print("=" * 60)
    print(f"\nObjective: {objective}\n")

    # Step 1: Boot the run
    print("Step 1: Booting run...")
    boot_result = client.boot_run(
        objective=objective,
        acceptance_criteria=["Research completed", "Findings documented"],
        constraints=["Use reliable sources"],
    )
    run_id = boot_result["run_id"]
    print(f"✓ Run booted: {run_id}")
    print(f"  Status: {boot_result['status']}\n")
    time.sleep(1)

    # Track if we've done memory operation
    memory_committed = False

    # Step 2: Enter main loop
    step = 0
    while step < max_steps:
        step += 1
        print(f"\n--- Loop Iteration {step} ---")

        # Step 3: Fetch State
        print("Fetching current state...")
        try:
            state = client.get_state(run_id)
            expected_seq = state["_update_seq"]
            status = state.get("status", "BOOT")
            print(f"  Status: {status}")
            print(f"  Stage: {state.get('current_stage', 'N/A')}")
            print(f"  Next Action: {state.get('next_action', 'N/A')}")
            print(f"  Update Seq: {expected_seq}")
        except Exception as e:
            print(f"✗ Error fetching state: {e}")
            break

        # Check if done
        if status == "DONE":
            print("\n✓ Task completed!")
            break

        time.sleep(1)

        # Step 4: "Think" (Simulate LLM)
        print("Thinking (simulating LLM)...")
        updates = mock_llm_think(state, step)
        print(f"  Planned updates: {list(updates.keys())}")

        time.sleep(1)

        # Step 5: Send Patch (with conflict handling)
        print("Sending state update...")
        try:
            result = client.update_state(run_id, expected_seq, updates)
            if result.get("ok"):
                new_state = result.get("ws", {})
                print(f"✓ State updated successfully")
                print(f"  New Status: {new_state.get('status')}")
                print(f"  New Update Seq: {new_state.get('_update_seq')}")
            else:
                print(f"✗ Update failed: {result.get('error')}")
        except StateConflictError:
            print("⚡ Conflict! State has changed. Re-fetching state...")
            continue  # Loop back to fetch state
        except Exception as e:
            print(f"✗ Error updating state: {e}")
            break

        time.sleep(1)

        # Step 6: Memory (once during the loop)
        if not memory_committed and step == 3:
            print("\n--- Memory Operation ---")
            print("Proposing memory...")

            memory_item = {
                "_schema_version": "2.1",
                "op": "add",
                "type": "fact",
                "scope": "global",
                "content": f"Research progress: Completed {step} steps of investigation",
                "confidence": 0.85,
                "rationale": "Agent observation during research",
                "source_refs": [],
            }

            try:
                propose_result = client.propose_memory(
                    run_id, [memory_item], scope_filters={}
                )
                if propose_result.get("ok"):
                    batch_id = propose_result.get("batch_id")
                    print(f"✓ Memory proposed. Batch ID: {batch_id}")

                    time.sleep(1)

                    print("Committing memory...")
                    commit_result = client.commit_memory(run_id, batch_id)
                    if commit_result.get("ok"):
                        committed_ids = commit_result.get("committed_ids", [])
                        print(f"✓ Memory committed. IDs: {committed_ids}")
                        memory_committed = True
                    else:
                        print(f"✗ Commit failed: {commit_result.get('error')}")
                else:
                    print(f"✗ Propose failed: {propose_result.get('error')}")
            except Exception as e:
                print(f"✗ Memory operation error: {e}")

        print()

    # Final snapshot
    print("\n--- Creating Final Snapshot ---")
    try:
        snapshot_result = client.snapshot(run_id)
        if snapshot_result.get("ok"):
            pack_path = snapshot_result.get("pack_path")
            print(f"✓ Snapshot created: {pack_path}")
        else:
            print(f"✗ Snapshot failed: {snapshot_result.get('error')}")
    except Exception as e:
        print(f"✗ Snapshot error: {e}")

    print("\n" + "=" * 60)
    print("Agent Loop Complete")
    print("=" * 60)


if __name__ == "__main__":
    try:
        # Test server connection first
        client = AgentClient()
        health = requests.get(f"{client.base_url}/health")
        if health.status_code != 200:
            print("✗ Server not responding. Make sure server.py is running.")
            exit(1)

        print("✓ Server connection verified\n")

        # Run the loop
        run_loop("Research the history of the Context Module.")
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to server.")
        print("  Make sure server.py is running on http://localhost:8000")
        print("  Start it with: python server.py")
    except KeyboardInterrupt:
        print("\n\nLoop interrupted by user.")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()

