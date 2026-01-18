"""
Example: How to integrate AoS Context v2.1 into your agent repository.

This example shows three integration patterns:
1. HTTP Client (recommended for separate services)
2. Direct Import (for same-process usage)
3. Agent Loop Pattern (complete workflow)
"""

from __future__ import annotations

import requests
from typing import Dict, List, Optional, Any


# ============================================================================
# Pattern 1: HTTP Client Wrapper
# ============================================================================

class AoSContextClient:
    """HTTP client for AoS Context Management API.
    
    Use this when your agent runs as a separate service from the context server.
    """
    
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip('/')
    
    def boot_run(
        self,
        objective: str,
        acceptance_criteria: List[str] = None,
        constraints: List[str] = None,
        task_id: Optional[str] = None,
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Boot a new run and return run_id + initial WS."""
        resp = requests.post(
            f"{self.base_url}/runs/boot",
            json={
                "objective": objective,
                "acceptance_criteria": acceptance_criteria or [],
                "constraints": constraints or [],
                "task_id": task_id,
                "thread_id": thread_id,
            }
        )
        resp.raise_for_status()
        return resp.json()
    
    def get_ws(self, run_id: str) -> Dict[str, Any]:
        """Get current working set."""
        resp = requests.get(f"{self.base_url}/runs/{run_id}/ws")
        resp.raise_for_status()
        return resp.json()
    
    def update_ws(
        self,
        run_id: str,
        expected_seq: int,
        patch: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update working set with optimistic locking.
        
        Args:
            run_id: Run identifier
            expected_seq: Current _update_seq from WS (for optimistic lock)
            patch: Fields to update (will be wrapped in "set")
        
        Returns:
            Updated WS and context brief
        """
        resp = requests.post(
            f"{self.base_url}/runs/{run_id}/step/update",
            json={
                "patch": {
                    "_schema_version": "2.1",
                    "expected_seq": expected_seq,
                    "set": patch,
                }
            }
        )
        resp.raise_for_status()
        return resp.json()
    
    def propose_memory(
        self,
        run_id: str,
        mcrs: List[Dict[str, Any]],
        scope_filters: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Propose memory change requests (stages for later commit).
        
        Args:
            run_id: Run identifier
            mcrs: List of Memory Change Requests (MCRs)
            scope_filters: Optional scope filters
        
        Returns:
            batch_id for later commit
        """
        resp = requests.post(
            f"{self.base_url}/runs/{run_id}/memory/propose",
            json={
                "mcrs": mcrs,
                "scope_filters": scope_filters or {},
            }
        )
        resp.raise_for_status()
        return resp.json()
    
    def create_milestone(
        self,
        run_id: str,
        reason: str = "checkpoint",
        memory_batch_id: Optional[str] = None,
        next_entry_point: str = "",
    ) -> Dict[str, Any]:
        """Create milestone checkpoint (commits memory if batch_id provided).
        
        Args:
            run_id: Run identifier
            reason: Reason for milestone
            memory_batch_id: Optional batch_id from propose_memory
            next_entry_point: Continuation instructions
        
        Returns:
            Episode ID, path, committed memory IDs, milestone_token
        """
        resp = requests.post(
            f"{self.base_url}/runs/{run_id}/milestone",
            json={
                "reason": reason,
                "memory_batch_id": memory_batch_id,
                "next_entry_point": next_entry_point,
            }
        )
        resp.raise_for_status()
        return resp.json()
    
    def search_memory(
        self,
        run_id: str,
        query: str = "",
        top_k: int = 8,
        scope: Optional[str] = None,
        status: str = "active",
    ) -> Dict[str, Any]:
        """Search long-term memory.
        
        Args:
            run_id: Run identifier
            query: Search query string
            top_k: Number of results
            scope: Optional scope filter (user/project/global)
            status: Status filter (default: active)
        
        Returns:
            List of matching memory items
        """
        params = {"q": query, "top_k": top_k, "status": status}
        if scope:
            params["scope"] = scope
        resp = requests.get(
            f"{self.base_url}/runs/{run_id}/memory/search",
            params=params
        )
        resp.raise_for_status()
        return resp.json()


# ============================================================================
# Pattern 2: Agent Loop with Context Integration
# ============================================================================

class AgentWithContext:
    """Example agent that uses AoS Context for state management."""
    
    def __init__(self, context_client: AoSContextClient):
        self.context = context_client
        self.run_id: Optional[str] = None
    
    def start_task(self, objective: str) -> str:
        """Start a new task/run."""
        result = self.context.boot_run(
            objective=objective,
            acceptance_criteria=["Task completes successfully"],
            constraints=["Follow best practices"]
        )
        self.run_id = result["run_id"]
        print(f"Started run: {self.run_id}")
        return self.run_id
    
    def get_current_state(self) -> Dict[str, Any]:
        """Get current working set state."""
        if not self.run_id:
            raise ValueError("No active run. Call start_task() first.")
        return self.context.get_ws(self.run_id)
    
    def update_state(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update working set state with optimistic locking."""
        if not self.run_id:
            raise ValueError("No active run. Call start_task() first.")
        
        # Get current state to read _update_seq
        ws = self.get_current_state()
        
        # Apply updates
        result = self.context.update_ws(
            run_id=self.run_id,
            expected_seq=ws["_update_seq"],
            patch=updates
        )
        
        return result
    
    def remember(self, content: str, confidence: float = 0.8) -> Optional[str]:
        """Propose a memory item to remember."""
        if not self.run_id:
            return None
        
        mcr = {
            "_schema_version": "2.1",
            "op": "add",
            "type": "fact",
            "scope": "global",
            "content": content,
            "confidence": confidence,
            "rationale": "Agent observation",
            "source_refs": []
        }
        
        result = self.context.propose_memory(
            run_id=self.run_id,
            mcrs=[mcr]
        )
        
        return result.get("batch_id")
    
    def checkpoint(self, reason: str = "checkpoint", memory_batch_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a milestone checkpoint."""
        if not self.run_id:
            raise ValueError("No active run. Call start_task() first.")
        
        return self.context.create_milestone(
            run_id=self.run_id,
            reason=reason,
            memory_batch_id=memory_batch_id,
            next_entry_point="Continue from checkpoint"
        )
    
    def run_loop(self, objective: str, max_iterations: int = 10):
        """Main agent execution loop with context management."""
        # Start task
        self.start_task(objective)
        
        iteration = 0
        while iteration < max_iterations:
            # Get current state
            ws = self.get_current_state()
            print(f"\n--- Iteration {iteration + 1} ---")
            print(f"Stage: {ws.get('current_stage')}")
            print(f"Status: {ws.get('status')}")
            print(f"Next Action: {ws.get('next_action')}")
            
            # Agent logic (simplified)
            if ws.get("status") == "DONE":
                print("Task complete!")
                break
            
            # Update state
            self.update_state({
                "status": "BUSY",
                "next_action": f"Processing iteration {iteration + 1}",
                "current_stage": "EXECUTE"
            })
            
            # Remember important things
            if iteration % 3 == 0:
                batch_id = self.remember(
                    f"Completed iteration {iteration + 1}",
                    confidence=0.9
                )
                
                # Checkpoint every 3 iterations
                if batch_id:
                    checkpoint = self.checkpoint(
                        reason="periodic_checkpoint",
                        memory_batch_id=batch_id
                    )
                    print(f"Checkpoint created: {checkpoint['episode_id']}")
            
            iteration += 1
        
        # Final checkpoint
        final_checkpoint = self.checkpoint(reason="task_complete")
        print(f"\nFinal checkpoint: {final_checkpoint['episode_id']}")


# ============================================================================
# Pattern 3: Usage Examples
# ============================================================================

def example_basic_usage():
    """Basic usage example."""
    context = AoSContextClient("http://127.0.0.1:8000")
    
    # Boot run
    result = context.boot_run(
        objective="Build a web scraper",
        acceptance_criteria=["Scrapes target site", "Saves to JSON"],
        constraints=["No rate limiting violations"]
    )
    run_id = result["run_id"]
    print(f"Booted run: {run_id}")
    
    # Get WS
    ws = context.get_ws(run_id)
    print(f"Current stage: {ws['current_stage']}")
    print(f"Update sequence: {ws['_update_seq']}")
    
    # Update WS
    update_result = context.update_ws(
        run_id=run_id,
        expected_seq=ws["_update_seq"],
        patch={
            "status": "BUSY",
            "next_action": "Start scraping",
            "current_stage": "EXECUTE"
        }
    )
    print(f"Updated WS. New seq: {update_result['ws']['_update_seq']}")
    
    # Propose memory
    memory_result = context.propose_memory(
        run_id=run_id,
        mcrs=[{
            "_schema_version": "2.1",
            "op": "add",
            "type": "fact",
            "scope": "global",
            "content": "User wants web scraper",
            "confidence": 0.9,
            "rationale": "From objective",
            "source_refs": []
        }]
    )
    batch_id = memory_result["batch_id"]
    print(f"Proposed memory. Batch ID: {batch_id}")
    
    # Create milestone (commits memory)
    milestone = context.create_milestone(
        run_id=run_id,
        reason="checkpoint",
        memory_batch_id=batch_id,
        next_entry_point="Continue scraping"
    )
    print(f"Milestone created: {milestone['episode_id']}")
    print(f"Committed memories: {milestone['committed_memory_ids']}")


def example_agent_loop():
    """Example using AgentWithContext class."""
    context = AoSContextClient("http://127.0.0.1:8000")
    agent = AgentWithContext(context)
    
    agent.run_loop(
        objective="Process 100 items",
        max_iterations=10
    )


if __name__ == "__main__":
    print("=== Basic Usage Example ===")
    example_basic_usage()
    
    print("\n=== Agent Loop Example ===")
    example_agent_loop()

