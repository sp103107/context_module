# AoS Context Module

A crash-safe, transactional state management system for AI agents.

The AoS Context Module provides a production-ready framework for managing agent state, memory, and context with features like optimistic locking, deterministic eviction, and portable snapshots.

## Features

- **Working Set (WS)**: Hot mutable state with optimistic locking and deterministic eviction
- **Run Ledger (RL)**: Append-only JSONL audit log for complete history
- **Episodes (EP)**: Immutable milestone checkpoints
- **Long-Term Memory (LTM)**: Transactional propose/commit workflow with Qdrant support
- **Resume Packs**: Portable snapshots for state migration between environments
- **FastAPI Server**: RESTful API for remote access
- **Schema Validation**: All artifacts validated against JSON Schema Draft 2020-12

## Installation

### From GitHub

```bash
pip install git+https://github.com/sp103107/context_module.git
```

### Local Editable Installation

```bash
git clone https://github.com/sp103107/context_module.git
cd context_module
pip install -e .
```

### Dependencies

The package requires:
- Python >= 3.10
- fastapi >= 0.111.0
- uvicorn[standard] >= 0.30.0
- pydantic >= 2.6.0
- jsonschema >= 4.21.0
- qdrant-client >= 1.7.0 (optional, for vector memory)

## Quick Start

### Python Library Usage

#### 1. Initialize a Working Set Manager

```python
from pathlib import Path
from aos_context.ws_manager import WorkingSetManager

# Create a working set manager
ws_path = Path("./runs/my_task/state/working_set.v2.1.json")
wsm = WorkingSetManager(ws_path)
```

#### 2. Boot a Task

```python
# Create initial working set
ws = wsm.create_initial(
    task_id="task_123",
    thread_id="thread_456",
    run_id="run_789",
    objective="Build a web scraper",
    acceptance_criteria=["Scrapes target site", "Saves to JSON"],
    constraints=["No rate limiting violations"]
)

print(f"Run ID: {ws['run_id']}")
print(f"Status: {ws['status']}")
print(f"Update Sequence: {ws['_update_seq']}")
```

#### 3. Update State with Optimistic Locking

```python
# Get current state
current_ws = wsm.load()
expected_seq = current_ws["_update_seq"]

# Apply a patch
patch = {
    "_schema_version": "2.1",
    "expected_seq": expected_seq,
    "set": {
        "status": "BUSY",
        "next_action": "Start scraping",
        "current_stage": "EXECUTE"
    }
}

result = wsm.apply_patch(patch)
if result.ok:
    print(f"Updated successfully. New seq: {result.new_ws['_update_seq']}")
else:
    print(f"Update failed: {result.error}")
    # Handle conflict - reload and retry
```

#### 4. Create Resume Pack

```python
from pathlib import Path

# Create a portable snapshot
snapshots_dir = Path("./snapshots")
pack_path = wsm.create_resume_pack(snapshots_dir)
print(f"Snapshot saved to: {pack_path}")

# Restore from pack
restored_wsm = WorkingSetManager.restore_from_pack(
    pack_path,
    Path("./restored_workspace")
)
restored_ws = restored_wsm.load()
print(f"Restored objective: {restored_ws['objective']}")
```

### API Server Usage

#### Start the Server

```bash
# Using uvicorn directly
uvicorn server:app --reload --port 8000

# Or using Python
python server.py
```

The server will be available at `http://127.0.0.1:8000`

#### API Endpoints

##### 1. Boot a Run

Create a new agent run.

```bash
curl -X POST http://127.0.0.1:8000/runs \
  -H "Content-Type: application/json" \
  -d '{
    "objective": "Research the history of AI",
    "acceptance_criteria": ["Findings documented", "Sources cited"],
    "constraints": ["Use reliable sources"]
  }'
```

**Response:**
```json
{
  "run_id": "run_abc123...",
  "status": "BOOT"
}
```

##### 2. Get Run State

Retrieve the current working set state.

```bash
curl http://127.0.0.1:8000/runs/{run_id}
```

**Response:**
```json
{
  "_schema_version": "2.1",
  "_update_seq": 0,
  "run_id": "run_abc123...",
  "status": "BOOT",
  "objective": "Research the history of AI",
  "current_stage": "BOOT",
  "next_action": "",
  ...
}
```

##### 3. Update State (with Optimistic Locking)

Update the working set. Returns `409 Conflict` if state has changed.

```bash
# First, get current state to read _update_seq
curl http://127.0.0.1:8000/runs/{run_id} > current_state.json

# Then update with expected_seq
curl -X PATCH http://127.0.0.1:8000/runs/{run_id} \
  -H "Content-Type: application/json" \
  -d '{
    "patch": {
      "status": "BUSY",
      "next_action": "Start research",
      "current_stage": "RESEARCH"
    },
    "expected_seq": 0
  }'
```

**Response (Success):**
```json
{
  "ok": true,
  "ws": {
    "_update_seq": 1,
    "status": "BUSY",
    ...
  }
}
```

**Response (Conflict - 409):**
```json
{
  "ok": false,
  "error": "Conflict: State has changed. Reload and retry."
}
```

##### 4. Propose Memory

Stage memory change requests for later commit.

```bash
curl -X POST http://127.0.0.1:8000/runs/{run_id}/memory/propose \
  -H "Content-Type: application/json" \
  -d '{
    "mcrs": [{
      "_schema_version": "2.1",
      "op": "add",
      "type": "fact",
      "scope": "global",
      "content": "AI was first proposed in 1956",
      "confidence": 0.9,
      "rationale": "Historical fact",
      "source_refs": []
    }],
    "scope_filters": {}
  }'
```

**Response:**
```json
{
  "ok": true,
  "batch_id": "batch_xyz789..."
}
```

##### 5. Commit Memory

Commit staged memories to active status.

```bash
curl -X POST http://127.0.0.1:8000/runs/{run_id}/memory/commit \
  -H "Content-Type: application/json" \
  -d '{
    "batch_id": "batch_xyz789..."
  }'
```

**Response:**
```json
{
  "ok": true,
  "committed_ids": ["mem_abc123..."]
}
```

##### 6. Create Snapshot

Create a portable resume pack.

```bash
curl -X POST http://127.0.0.1:8000/runs/{run_id}/snapshot
```

**Response:**
```json
{
  "ok": true,
  "pack_path": "./server_workspace/snapshots/task_123_resume_20260118_120000.zip"
}
```

##### 7. Health Check

```bash
curl http://127.0.0.1:8000/health
```

**Response:**
```json
{
  "status": "ok",
  "service": "aos-context-server"
}
```

## Configuration

### Environment Variables

#### Qdrant Memory Backend

To use Qdrant for vector-based memory storage:

```bash
export QDRANT_URL=http://localhost:6333
export QDRANT_COLLECTION=agent_memories
python server.py
```

The server will automatically:
- Connect to Qdrant at the specified URL
- Create the collection if it doesn't exist
- Use QdrantMemoryStore instead of InMemoryMemoryStore

**Note:** For production, replace the dummy embedder in `server.py` with a real embedding function (OpenAI, HuggingFace, etc.).

#### Workspace Directory

```bash
export AOS_RUNS_ROOT=/path/to/runs
```

## Architecture

### Working Set (WS)

The Working Set is the hot, mutable state of an agent run. It includes:
- Task metadata (objective, acceptance criteria, constraints)
- Current status and stage
- Pinned context (always included)
- Sliding context (evicted based on token budget)

**Key Features:**
- Optimistic locking via `_update_seq`
- Deterministic eviction (priority + timestamp)
- Atomic writes (crash-safe)

### Memory System

The memory system supports a two-phase commit workflow:

1. **Propose**: Stage memory change requests (MCRs)
2. **Commit**: Activate staged memories

**Backends:**
- `InMemoryMemoryStore`: Simple in-process storage (default)
- `QdrantMemoryStore`: Vector database for semantic search (production)

### Resume Packs

Resume packs are portable ZIP files containing:
- `working_set.json`: Current state
- `run.jsonl`: Ledger history (if available)

Use cases:
- Migrate agent state between environments
- Create checkpoints for rollback
- Share agent state between systems

## Examples

### Complete Agent Loop

See `run_agent_loop.py` for a complete example demonstrating:
- Booting a run
- Fetching and updating state
- Handling 409 conflicts
- Proposing and committing memories
- Creating snapshots

```bash
# Terminal 1: Start server
python server.py

# Terminal 2: Run agent loop
python run_agent_loop.py
```

### Integration Example

See `examples/agent_integration_example.py` for integration patterns:
- HTTP client wrapper
- Agent loop with context management
- Error handling and retry logic

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Code Coverage

```bash
pytest tests/ --cov=aos_context --cov-report=html
```

### Linting

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/
```

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Contributions welcome! Please open an issue or pull request on GitHub.

## Links

- **GitHub**: https://github.com/sp103107/context_module
- **API Documentation**: http://127.0.0.1:8000/docs (when server is running)
- **Interactive API**: http://127.0.0.1:8000/redoc
