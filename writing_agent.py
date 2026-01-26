"""Writing Agent - Demonstrates full integration with Ollama LLM.

This agent uses the context module to manage state while writing
a short children's story using Ollama.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

import requests


class AgentClient:
    """Client wrapper for context module API."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        """Initialize client.

        Args:
            base_url: Base URL for context module API
        """
        self.base_url = base_url

    def boot_run(
        self,
        objective: str,
        acceptance_criteria: List[str],
        constraints: List[str],
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Boot a new run.

        Args:
            objective: Task objective
            acceptance_criteria: List of acceptance criteria
            constraints: List of constraints
            task_id: Optional task ID (auto-generated if not provided)

        Returns:
            Response with run_id and status
        """
        payload = {
            "objective": objective,
            "acceptance_criteria": acceptance_criteria,
            "constraints": constraints,
        }
        if task_id:
            payload["task_id"] = task_id

        resp = requests.post(f"{self.base_url}/runs", json=payload)
        resp.raise_for_status()
        return resp.json()

    def get_state(self, run_id: str) -> Dict[str, Any]:
        """Get current working set state.

        Args:
            run_id: Run identifier

        Returns:
            Working set JSON
        """
        resp = requests.get(f"{self.base_url}/runs/{run_id}")
        resp.raise_for_status()
        return resp.json()

    def update_state(
        self, run_id: str, expected_seq: int, patch: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update working set with patch.

        Args:
            run_id: Run identifier
            expected_seq: Expected update sequence number
            patch: Patch to apply

        Returns:
            Updated working set

        Raises:
            StateConflictError: If state has changed (409 Conflict)
        """
        payload = {"expected_seq": expected_seq, "patch": patch}
        resp = requests.patch(f"{self.base_url}/runs/{run_id}", json=payload)

        if resp.status_code == 409:
            raise StateConflictError("State has changed. Reload and retry.")

        resp.raise_for_status()
        return resp.json()

    def propose_memory(
        self,
        run_id: str,
        mcrs: List[Dict[str, Any]],
        scope_filters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Propose memory change requests.

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

    def commit_memory(
        self, run_id: str, batch_id: str, milestone_token: str
    ) -> Dict[str, Any]:
        """Commit staged memory batch.

        Args:
            run_id: Run identifier
            batch_id: Batch ID from propose_memory
            milestone_token: Token from milestone endpoint

        Returns:
            Response with committed memory IDs
        """
        resp = requests.post(
            f"{self.base_url}/runs/{run_id}/memory/commit",
            json={"batch_id": batch_id, "milestone_token": milestone_token},
        )
        resp.raise_for_status()
        return resp.json()

    def create_milestone(
        self, run_id: str, reason: str = "Story completion milestone"
    ) -> Dict[str, Any]:
        """Create a milestone checkpoint.

        Args:
            run_id: Run identifier
            reason: Reason for milestone

        Returns:
            Response with milestone_token
        """
        resp = requests.post(
            f"{self.base_url}/runs/{run_id}/milestone",
            json={"reason": reason, "next_entry_point": ""},
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


class StateConflictError(Exception):
    """Raised when state update conflicts with current state."""

    pass


class OllamaClient:
    """Simple Ollama client for LLM interactions."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama2"):
        """Initialize Ollama client.

        Args:
            base_url: Ollama API base URL
            model: Model name to use
        """
        self.base_url = base_url
        self.model = model

    def complete(
        self, prompt: str, system: Optional[str] = None, temperature: float = 0.7
    ) -> str:
        """Generate completion using Ollama.

        Args:
            prompt: User prompt
            system: Optional system message
            temperature: Sampling temperature

        Returns:
            Generated text
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }

        resp = requests.post(
            f"{self.base_url}/api/chat", json=payload, timeout=120
        )
        resp.raise_for_status()
        result = resp.json()
        return result.get("message", {}).get("content", "")


def run_writing_agent(
    story_topic: str = "a brave little robot",
    model: str = "llama3",
    max_steps: int = 5,
) -> str:
    """Run the writing agent to create a children's story.

    Args:
        story_topic: Topic for the story
        model: Ollama model to use
        max_steps: Maximum number of agent steps

    Returns:
        Final run_id
    """
    print("=" * 70)
    print("Writing Agent - Children's Story Generator")
    print("=" * 70)
    print()

    # Initialize clients
    agent_client = AgentClient()
    ollama_client = OllamaClient(model=model)

    # Step 1: Boot the run
    print("Step 1: Booting agent run...")
    objective = f"Write a short children's story about {story_topic}"
    boot_result = agent_client.boot_run(
        objective=objective,
        acceptance_criteria=[
            "Story is complete (300-500 words)",
            "Story has a clear beginning, middle, and end",
            "Story is appropriate for children (ages 5-10)",
            "Story includes a positive message or lesson",
        ],
        constraints=[
            "Keep language simple and age-appropriate",
            "Include engaging characters",
            "Make it fun and imaginative",
        ],
        task_id="writing_agent_task",
    )
    run_id = boot_result["run_id"]
    print(f"  [OK] Run booted: {run_id}")
    print(f"  [OK] Objective: {objective}\n")
    time.sleep(1)

    # Step 2: Plan the story
    print("Step 2: Planning the story...")
    try:
        state = agent_client.get_state(run_id)
        current_seq = state["_update_seq"]

        # Use LLM to create a story outline
        planning_prompt = f"""Create a brief outline for a children's story about {story_topic}.
The story should be 300-500 words, appropriate for ages 5-10, with:
- A main character
- A simple conflict or challenge
- A resolution with a positive message

Provide just a 3-4 sentence outline."""

        print("  [INFO] Asking LLM for story outline...")
        outline = ollama_client.complete(
            planning_prompt,
            system="You are a creative children's story writer.",
            temperature=0.8,
        )
        print(f"  [OK] Outline generated:\n  {outline[:200]}...\n")

        # Update state with outline
        patch = {
            "_schema_version": "2.1",
            "expected_seq": current_seq,
            "set": {
                "status": "BUSY",
                "current_stage": "PLANNING",
                "next_action": "Creating story outline",
                "last_action_summary": f"Generated outline: {outline[:100]}...",
            },
        }
        result = agent_client.update_state(run_id, current_seq, patch)
        print(f"  [OK] State updated: Status = {result.get('status', 'N/A')}\n")
        time.sleep(1)

    except StateConflictError:
        print("  [WARN] State conflict, reloading...")
        state = agent_client.get_state(run_id)
        current_seq = state["_update_seq"]

    # Step 3: Write the story
    print("Step 3: Writing the story...")
    story_parts = []
    step_count = 0

    while step_count < max_steps:
        try:
            state = agent_client.get_state(run_id)
            current_seq = state["_update_seq"]

            if step_count == 0:
                # Generate the beginning
                writing_prompt = f"""Write the beginning of a children's story about {story_topic}.
Make it engaging, age-appropriate (5-10 years), and about 100-150 words.
Start with introducing the main character and setting."""

                print("  [INFO] Writing story beginning...")
                beginning = ollama_client.complete(
                    writing_prompt,
                    system="You are a creative children's story writer. Write in a warm, engaging style.",
                    temperature=0.8,
                )
                story_parts.append(beginning)
                print(f"  [OK] Beginning written ({len(beginning)} chars)\n")

            elif step_count == 1:
                # Generate the middle
                writing_prompt = f"""Continue the children's story. The beginning was:
{story_parts[0]}

Write the middle section (100-150 words) where the main character faces a challenge or problem.
Keep it age-appropriate and engaging."""

                print("  [INFO] Writing story middle...")
                middle = ollama_client.complete(
                    writing_prompt,
                    system="You are a creative children's story writer. Write in a warm, engaging style.",
                    temperature=0.8,
                )
                story_parts.append(middle)
                print(f"  [OK] Middle written ({len(middle)} chars)\n")

            elif step_count == 2:
                # Generate the end
                writing_prompt = f"""Complete the children's story. So far we have:
BEGINNING:
{story_parts[0]}

MIDDLE:
{story_parts[1]}

Write the ending (100-150 words) that resolves the challenge and includes a positive message or lesson.
Make it heartwarming and satisfying."""

                print("  [INFO] Writing story ending...")
                ending = ollama_client.complete(
                    writing_prompt,
                    system="You are a creative children's story writer. Write in a warm, engaging style.",
                    temperature=0.8,
                )
                story_parts.append(ending)
                print(f"  [OK] Ending written ({len(ending)} chars)\n")

            # Update state with progress
            full_story = "\n\n".join(story_parts)
            patch = {
                "_schema_version": "2.1",
                "expected_seq": current_seq,
                "set": {
                    "status": "BUSY" if step_count < max_steps - 1 else "DONE",
                    "current_stage": "WRITING",
                    "next_action": f"Writing part {step_count + 1} of {max_steps}",
                    "last_action_summary": f"Story progress: {len(full_story)} characters written",
                },
            }
            agent_client.update_state(run_id, current_seq, patch)
            step_count += 1
            time.sleep(1)

        except StateConflictError:
            print("  [WARN] State conflict, reloading...")
            state = agent_client.get_state(run_id)
            continue
        except Exception as e:
            print(f"  [ERROR] Error during writing: {e}")
            break

    # Step 4: Finalize and save story
    print("Step 4: Finalizing story...")
    try:
        state = agent_client.get_state(run_id)
        current_seq = state["_update_seq"]
        full_story = "\n\n".join(story_parts)

        # Save story to pinned context
        story_artifact = {
            "type": "story",
            "title": f"Story about {story_topic}",
            "content": full_story,
            "word_count": len(full_story.split()),
            "topic": story_topic,
        }

        # Update state with final story
        patch = {
            "_schema_version": "2.1",
            "expected_seq": current_seq,
            "set": {
                "status": "DONE",
                "current_stage": "COMPLETE",
                "next_action": "Story complete!",
                "last_action_summary": f"Story completed: {story_artifact['word_count']} words",
            },
            "append": {
                "pinned_context": [story_artifact],
            },
        }
        final_state = agent_client.update_state(run_id, current_seq, patch)
        print(f"  [OK] Story saved to context\n")
        print(f"  [OK] Final status: {final_state.get('status', 'N/A')}\n")

        # Step 5: Propose and commit memory (skip milestone for now - server.py doesn't have it)
        print("Step 5: Proposing memory...")
        try:
            # Propose memory about the story
            memory_item = {
                "content": f"Completed children's story about {story_topic}. Story is {story_artifact['word_count']} words long.",
                "type": "achievement",
                "metadata": {
                    "story_topic": story_topic,
                    "word_count": story_artifact["word_count"],
                },
            }
            propose_result = agent_client.propose_memory(run_id, [memory_item])
            batch_id = propose_result.get("batch_id")
            print(f"  [OK] Memory proposed (batch: {batch_id})\n")
            
            # Note: Memory commit requires milestone endpoint which server.py doesn't have
            # For now, we'll skip the commit step
            print("  [INFO] Skipping memory commit (requires milestone endpoint)\n")
        except Exception as e:
            print(f"  [WARN] Memory operations failed: {e}\n")

        # Step 6: Create snapshot
        print("Step 6: Creating snapshot...")
        snapshot_result = agent_client.snapshot(run_id)
        print(f"  [OK] Snapshot created: {snapshot_result.get('pack_path', 'N/A')}\n")

        # Display the story
        print("=" * 70)
        print("FINAL STORY")
        print("=" * 70)
        try:
            print(full_story)
        except UnicodeEncodeError:
            # Fallback for Windows console encoding issues
            print(full_story.encode('ascii', 'replace').decode('ascii'))
        print("=" * 70)
        print(f"\nStory Statistics:")
        print(f"  - Word Count: {story_artifact['word_count']}")
        print(f"  - Character Count: {len(full_story)}")
        print(f"  - Topic: {story_topic}")
        print(f"  - Run ID: {run_id}")

        return run_id

    except Exception as e:
        print(f"  [ERROR] Error during finalization: {e}")
        return run_id


if __name__ == "__main__":
    import sys

    # Get story topic from command line or use default
    topic = sys.argv[1] if len(sys.argv) > 1 else "a brave little robot"
    model = sys.argv[2] if len(sys.argv) > 2 else "llama2"

    print(f"Starting Writing Agent...")
    print(f"  Topic: {topic}")
    print(f"  Model: {model}\n")

    try:
        run_id = run_writing_agent(story_topic=topic, model=model)
        print(f"\n[SUCCESS] Writing agent completed! Run ID: {run_id}")
    except KeyboardInterrupt:
        print("\n[INFO] Agent interrupted by user")
    except Exception as e:
        print(f"\n[ERROR] Agent failed: {e}")
        import traceback

        traceback.print_exc()
