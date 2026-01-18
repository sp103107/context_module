# Frontend Architecture & Integration Guide

## HTML Frontend Design

### Current Frontend Structure

**Location**: `aos_context/static/index.html`

**Architecture**: Single-page application (SPA) with vanilla JavaScript

### Frontend Components Map

```
┌─────────────────────────────────────────────────────────────┐
│                    AoS Context v2.1                         │
│                   Control Panel (SPA)                       │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
┌───────▼────────┐  ┌─────────▼─────────┐  ┌───────▼────────┐
│  Section 1     │  │  Section 2        │  │  Section 3     │
│  Boot Run      │  │  Working Set      │  │  Update WS      │
│                │  │                   │  │                 │
│  - Objective   │  │  - Run ID input   │  │  - Run ID       │
│  - Criteria    │  │  - Load button    │  │  - Expected Seq │
│  - Constraints │  │  - WS display     │  │  - Patch JSON   │
│  - Boot button │  │                   │  │  - Apply button │
└────────────────┘  └───────────────────┘  └────────────────┘
        │                     │                     │
┌───────▼────────┐  ┌─────────▼─────────┐  ┌───────▼────────┐
│  Section 4     │  │  Section 5        │  │  Section 6     │
│  Memory Ops    │  │  Milestone         │  │  Resume Pack   │
│                │  │                   │  │                 │
│  - Run ID      │  │  - Run ID         │  │  - Run ID       │
│  - Propose MCR │  │  - Batch ID       │  │  - Snapshot     │
│  - Search      │  │  - Reason         │  │  - Load Pack    │
│  - Results     │  │  - Entry Point    │  │  - Pack Path   │
└────────────────┘  └───────────────────┘  └────────────────┘
```

### UI Flow Diagram

```
┌─────────────┐
│  1. Boot    │───► Run ID generated
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 2. Load WS  │───► Display WS + _update_seq
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 3. Patch WS │───► Update with expected_seq
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 4. Propose  │───► Memory batch_id
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 5. Milestone│───► Episode + milestone_token
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 6. Snapshot │───► Resume pack created
└─────────────┘
```

### Frontend Features

#### 1. Boot Run Section
- **Inputs**: Objective (textarea), Acceptance Criteria (textarea), Constraints (textarea)
- **Action**: Creates new run, auto-fills Run ID in all sections
- **Output**: Run ID, initial WS state

#### 2. Working Set Viewer
- **Input**: Run ID
- **Action**: Fetches and displays current WS
- **Output**: Full WS JSON with `_update_seq` highlighted

#### 3. WS Update Section
- **Inputs**: Run ID, Expected Sequence, WS Patch (JSON)
- **Action**: Applies patch with optimistic locking
- **Output**: Updated WS, Context Brief

#### 4. Memory Operations
- **Propose**: Stage MCRs (JSON array), returns batch_id
- **Search**: Query memory with filters
- **Output**: Batch ID (for propose), Search results (for search)

#### 5. Milestone Section
- **Inputs**: Run ID, Memory Batch ID, Reason, Next Entry Point
- **Action**: Creates episode checkpoint, commits memory (if batch_id provided)
- **Output**: Episode ID, Episode Path, Committed Memory IDs, **milestone_token**

#### 6. Resume Pack Section
- **Snapshot**: Creates portable pack (zip or directory)
- **Load**: Loads pack into new run
- **Output**: Pack ID, Pack Path (for snapshot), New Run ID (for load)

### Frontend API Integration

All sections use `fetch()` API to call FastAPI endpoints:

```javascript
// Base URL (auto-detected from window.location)
const API_BASE = window.location.origin;

// Example: Boot run
async function bootRun() {
    const response = await fetch(`${API_BASE}/runs/boot`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            objective: "...",
            acceptance_criteria: [...],
            constraints: [...]
        })
    });
    const data = await response.json();
    // Handle response
}
```

### UI State Management

- **Run ID Propagation**: When a run is booted, Run ID auto-fills in all sections
- **Expected Sequence**: Auto-updated after WS load or patch
- **Batch ID**: Auto-filled after memory propose
- **Milestone Token**: Displayed after milestone creation (for manual commit if needed)

### Error Handling

- All API errors return structured JSON: `{ok: false, error: "..."}`
- Errors displayed in red `<pre>` output sections
- Success responses displayed in green

### Styling

- **Framework**: Vanilla CSS (no dependencies)
- **Design**: Clean, card-based layout
- **Responsive**: Max-width 1200px, centered
- **Colors**: Blue primary (#007bff), red errors, green success

---

## Server Startup Guide

### Basic Startup

```bash
# Navigate to repo
cd aos_context_v2_1

# Activate virtual environment (if using one)
# source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate     # Windows

# Start server
uvicorn aos_context.api.main:app --reload --port 8000
```

### Production Startup

```bash
# With multiple workers
uvicorn aos_context.api.main:app --workers 4 --host 0.0.0.0 --port 8000

# With SSL (if using reverse proxy)
# Use nginx/caddy as reverse proxy
```

### Environment Variables

```bash
# Set runs root directory (default: ./runs)
export AOS_RUNS_ROOT=/path/to/runs

# Enable test mode (allows allow_outside_milestone bypass)
export AOS_TEST_MODE=1

# Start with custom config
AOS_RUNS_ROOT=./my_runs uvicorn aos_context.api.main:app --reload
```

### Access Points

- **Web UI**: http://127.0.0.1:8000/ (redirects to /static/index.html)
- **API Docs**: http://127.0.0.1:8000/docs (FastAPI auto-generated)
- **Health Check**: http://127.0.0.1:8000/health
- **API Base**: http://127.0.0.1:8000/runs/...

---

## Agent Repository Integration

### Option 1: HTTP Client Integration

Create a Python client wrapper in your agent repo:

```python
# agent_repo/context_client.py
import requests
from typing import Dict, List, Optional, Any

class AoSContextClient:
    """Client for AoS Context Management API."""
    
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
        """Boot a new run."""
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
        """Get working set."""
        resp = requests.get(f"{self.base_url}/runs/{run_id}/ws")
        resp.raise_for_status()
        return resp.json()
    
    def update_ws(
        self,
        run_id: str,
        expected_seq: int,
        patch: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update working set with optimistic locking."""
        resp = requests.post(
            f"{self.base_url}/runs/{run_id}/step/update",
            json={"patch": {
                "_schema_version": "2.1",
                "expected_seq": expected_seq,
                "set": patch,
            }}
        )
        resp.raise_for_status()
        return resp.json()
    
    def propose_memory(
        self,
        run_id: str,
        mcrs: List[Dict[str, Any]],
        scope_filters: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Propose memory change requests."""
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
        """Create milestone checkpoint."""
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
        """Search long-term memory."""
        params = {"q": query, "top_k": top_k, "status": status}
        if scope:
            params["scope"] = scope
        resp = requests.get(
            f"{self.base_url}/runs/{run_id}/memory/search",
            params=params
        )
        resp.raise_for_status()
        return resp.json()
    
    def snapshot_resume_pack(
        self,
        run_id: str,
        zip_pack: bool = True,
        pointers: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Create resume pack snapshot."""
        resp = requests.post(
            f"{self.base_url}/runs/{run_id}/resume/snapshot",
            json={
                "zip_pack": zip_pack,
                "pointers": pointers or {},
            }
        )
        resp.raise_for_status()
        return resp.json()


# Usage in agent
from context_client import AoSContextClient

context = AoSContextClient("http://127.0.0.1:8000")

# Boot run
result = context.boot_run(
    objective="Build a web scraper",
    acceptance_criteria=["Scrapes target site", "Saves to JSON"],
    constraints=["No rate limiting violations"]
)
run_id = result["run_id"]

# Get WS
ws = context.get_ws(run_id)
print(f"Current stage: {ws['current_stage']}")

# Update WS
update_result = context.update_ws(
    run_id=run_id,
    expected_seq=ws["_update_seq"],
    patch={"status": "BUSY", "next_action": "Start scraping"}
)

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

# Create milestone (commits memory)
milestone = context.create_milestone(
    run_id=run_id,
    reason="checkpoint",
    memory_batch_id=batch_id,
    next_entry_point="Continue scraping"
)
print(f"Episode: {milestone['episode_id']}")
```

### Option 2: Direct Python Import

If running in the same process:

```python
# agent_repo/agent.py
from aos_context.ws_manager import WorkingSetManager
from aos_context.ledger import FileLedger
from aos_context.memory import InMemoryMemoryStore
from aos_context.episode import create_episode
from aos_context.config import DEFAULT_CONFIG
from pathlib import Path

# Initialize
run_id = "run_123"
ws_path = Path(f"./runs/{run_id}/state/working_set.v2.1.json")
wsm = WorkingSetManager(ws_path, config=DEFAULT_CONFIG)

# Use directly
ws = wsm.create_initial(...)
result = wsm.apply_patch(...)
```

### Option 3: Docker Compose (Recommended for Production)

```yaml
# docker-compose.yml
version: '3.8'
services:
  aos-context:
    build: ./aos_context_v2_1
    ports:
      - "8000:8000"
    environment:
      - AOS_RUNS_ROOT=/data/runs
    volumes:
      - ./runs:/data/runs
    command: uvicorn aos_context.api.main:app --host 0.0.0.0 --port 8000
  
  agent:
    build: ./agent_repo
    depends_on:
      - aos-context
    environment:
      - AOS_CONTEXT_URL=http://aos-context:8000
```

### Integration Patterns

#### Pattern 1: Agent Loop with Context

```python
class Agent:
    def __init__(self, context_client: AoSContextClient):
        self.context = context_client
        self.run_id = None
    
    def run(self, objective: str):
        # Boot
        boot_result = self.context.boot_run(objective=objective)
        self.run_id = boot_result["run_id"]
        
        # Main loop
        while True:
            # Get current state
            ws = self.context.get_ws(self.run_id)
            
            # Agent logic
            action = self.plan_next_action(ws)
            
            # Update WS
            self.context.update_ws(
                run_id=self.run_id,
                expected_seq=ws["_update_seq"],
                patch={"next_action": action}
            )
            
            # Propose memory
            if self.should_remember():
                self.context.propose_memory(...)
            
            # Milestone checkpoint
            if self.should_checkpoint():
                self.context.create_milestone(...)
```

#### Pattern 2: MCP Packet Integration

```python
# For MCP-compliant agent systems
def handle_mcp_packet(packet: Dict[str, Any]):
    """Handle MCP packet for context operations."""
    vport = packet.get("vport")
    action = packet.get("action")
    
    if vport == "aos.context":
        if action == "context.boot":
            return context_client.boot_run(**packet["payload"])
        elif action == "context.ws.get":
            return context_client.get_ws(packet["payload"]["run_id"])
        elif action == "context.ws.patch":
            return context_client.update_ws(**packet["payload"])
        # ... etc
```

### Testing Integration

```python
# tests/test_agent_integration.py
import pytest
from context_client import AoSContextClient

@pytest.fixture
def context():
    return AoSContextClient("http://127.0.0.1:8000")

def test_agent_workflow(context):
    # Boot
    result = context.boot_run(objective="Test")
    run_id = result["run_id"]
    
    # Workflow
    ws = context.get_ws(run_id)
    assert ws["objective"] == "Test"
    
    # Update
    updated = context.update_ws(
        run_id=run_id,
        expected_seq=ws["_update_seq"],
        patch={"status": "BUSY"}
    )
    assert updated["ws"]["status"] == "BUSY"
```

---

## Quick Reference

### API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Health check |
| POST | `/runs/boot` | Create new run |
| GET | `/runs/{run_id}/ws` | Get working set |
| POST | `/runs/{run_id}/step/update` | Update WS (optimistic lock) |
| POST | `/runs/{run_id}/memory/propose` | Stage memory changes |
| POST | `/runs/{run_id}/memory/commit` | Commit memory (needs token) |
| GET | `/runs/{run_id}/memory/search` | Search memory |
| POST | `/runs/{run_id}/milestone` | Create checkpoint |
| POST | `/runs/{run_id}/resume/snapshot` | Create resume pack |
| POST | `/runs/resume/load` | Load resume pack |

### Key Concepts

- **Optimistic Locking**: Use `_update_seq` from WS, pass as `expected_seq` in patch
- **Milestone Token**: Get from milestone endpoint, use for memory commit
- **Memory Gating**: Propose anytime, commit only at milestone (or with test mode)
- **Resume Packs**: Portable snapshots with manifest + hashes

---

## Next Steps

1. **Customize Frontend**: Modify `aos_context/static/index.html` for your needs
2. **Add Authentication**: Add auth middleware if needed
3. **Persist Memory**: Swap `InMemoryMemoryStore` with Mem0 adapter
4. **Scale**: Use multiple workers or deploy behind load balancer
5. **Monitor**: Add logging/metrics endpoints

