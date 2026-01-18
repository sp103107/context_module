# Complete Integration Guide

## Overview

This guide explains how to use AoS Context v2.1 in your agent repository, covering:
- Frontend architecture
- Server startup
- Agent integration patterns
- Example code

## Quick Links

- **Frontend Architecture**: See `FRONTEND_ARCHITECTURE.md`
- **Frontend Visual Map**: See `FRONTEND_MAP.md`
- **Quick Start**: See `QUICKSTART.md`
- **Example Code**: See `examples/agent_integration_example.py`

## Server Startup

### Development Mode

```bash
# 1. Navigate to repo
cd aos_context_v2_1

# 2. Install (if not done)
pip install -e ".[dev]"

# 3. Start server
uvicorn aos_context.api.main:app --reload --port 8000
```

**Access Points:**
- Web UI: http://127.0.0.1:8000/
- API Docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

### Production Mode

```bash
# Multiple workers
uvicorn aos_context.api.main:app --workers 4 --host 0.0.0.0 --port 8000

# With environment variables
AOS_RUNS_ROOT=/data/runs uvicorn aos_context.api.main:app --host 0.0.0.0
```

## Frontend Overview

The frontend is a **single-page application** at `aos_context/static/index.html`:

### 6 Main Sections

1. **Boot Run** - Create new runs
2. **Working Set** - View current state
3. **Update WS** - Apply patches with optimistic locking
4. **Memory Ops** - Propose/search memory
5. **Milestone** - Create checkpoints
6. **Resume Pack** - Snapshot/load packs

### Key Features

- **Auto-fill**: Run ID, expected_seq, batch_id propagate automatically
- **Real-time**: All operations use fetch() API
- **Error handling**: Structured error responses
- **No dependencies**: Pure vanilla JavaScript

## Agent Integration

### Pattern 1: HTTP Client (Recommended)

**Best for**: Separate agent service, microservices architecture

```python
from context_client import AoSContextClient

# Initialize
context = AoSContextClient("http://127.0.0.1:8000")

# Boot run
result = context.boot_run(objective="My task")
run_id = result["run_id"]

# Get state
ws = context.get_ws(run_id)

# Update state
context.update_ws(
    run_id=run_id,
    expected_seq=ws["_update_seq"],
    patch={"status": "BUSY"}
)
```

**See**: `examples/agent_integration_example.py` for full client implementation

### Pattern 2: Direct Import

**Best for**: Same-process usage, embedded agents

```python
from aos_context.ws_manager import WorkingSetManager
from aos_context.config import DEFAULT_CONFIG
from pathlib import Path

wsm = WorkingSetManager(
    Path("./runs/my_run/state/working_set.v2.1.json"),
    config=DEFAULT_CONFIG
)

ws = wsm.create_initial(...)
result = wsm.apply_patch(...)
```

### Pattern 3: Agent Loop Pattern

**Best for**: Long-running agents with periodic checkpoints

```python
from agent_integration_example import AgentWithContext, AoSContextClient

context = AoSContextClient("http://127.0.0.1:8000")
agent = AgentWithContext(context)

# Run agent loop with automatic state management
agent.run_loop(
    objective="Process 100 items",
    max_iterations=10
)
```

## Complete Workflow Example

```python
from context_client import AoSContextClient

context = AoSContextClient("http://127.0.0.1:8000")

# 1. Boot
result = context.boot_run(
    objective="Build web scraper",
    acceptance_criteria=["Scrapes site", "Saves JSON"],
    constraints=["No rate limiting"]
)
run_id = result["run_id"]

# 2. Get state
ws = context.get_ws(run_id)
print(f"Stage: {ws['current_stage']}")

# 3. Update
update_result = context.update_ws(
    run_id=run_id,
    expected_seq=ws["_update_seq"],
    patch={"status": "BUSY", "next_action": "Start scraping"}
)

# 4. Propose memory
memory_result = context.propose_memory(
    run_id=run_id,
    mcrs=[{
        "_schema_version": "2.1",
        "op": "add",
        "type": "fact",
        "scope": "global",
        "content": "User wants scraper",
        "confidence": 0.9,
        "rationale": "From objective",
        "source_refs": []
    }]
)
batch_id = memory_result["batch_id"]

# 5. Milestone (commits memory)
milestone = context.create_milestone(
    run_id=run_id,
    reason="checkpoint",
    memory_batch_id=batch_id
)
print(f"Episode: {milestone['episode_id']}")

# 6. Snapshot
snapshot = context.snapshot_resume_pack(run_id=run_id)
print(f"Pack: {snapshot['pack_id']}")
```

## Environment Variables

```bash
# Runs directory (default: ./runs)
export AOS_RUNS_ROOT=/path/to/runs

# Test mode (allows memory commit bypass)
export AOS_TEST_MODE=1
```

## API Endpoints Reference

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/health` | Health check |
| POST | `/runs/boot` | Create run |
| GET | `/runs/{run_id}/ws` | Get WS |
| POST | `/runs/{run_id}/step/update` | Update WS |
| POST | `/runs/{run_id}/memory/propose` | Stage memory |
| POST | `/runs/{run_id}/memory/commit` | Commit memory |
| GET | `/runs/{run_id}/memory/search` | Search memory |
| POST | `/runs/{run_id}/milestone` | Create checkpoint |
| POST | `/runs/{run_id}/resume/snapshot` | Create pack |
| POST | `/runs/resume/load` | Load pack |

## Key Concepts

### Optimistic Locking

Always use `_update_seq` from WS as `expected_seq` in patches:

```python
ws = context.get_ws(run_id)
context.update_ws(
    run_id=run_id,
    expected_seq=ws["_update_seq"],  # ← Critical!
    patch={...}
)
```

### Milestone Token Gating

Memory commit requires milestone_token from milestone endpoint:

```python
# Create milestone (returns token)
milestone = context.create_milestone(run_id=run_id, ...)
token = milestone["milestone_token"]

# Use token for commit (if committing separately)
context.commit_memory(
    run_id=run_id,
    batch_id=batch_id,
    milestone_token=token
)
```

**Note**: If you pass `memory_batch_id` to milestone, it commits automatically.

### Memory Gating

- **Propose**: Allowed anytime
- **Commit**: Only at milestone (or with AOS_TEST_MODE=1)

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run API tests
pytest tests/test_api.py -v

# With coverage
pytest tests/ --cov=aos_context --cov-report=html
```

## Troubleshooting

**Server won't start?**
- Check port 8000 is available
- Verify dependencies: `pip install -e ".[dev]"`

**Can't access UI?**
- Server running? Check: `curl http://127.0.0.1:8000/health`
- Port correct? Default is 8000

**Memory commit fails?**
- Need milestone_token from milestone endpoint
- Or set AOS_TEST_MODE=1 for testing

**WS update fails with 409?**
- expected_seq mismatch - reload WS first
- Another process updated WS concurrently

## Next Steps

1. **Customize Frontend**: Edit `aos_context/static/index.html`
2. **Add Auth**: Add authentication middleware if needed
3. **Scale**: Deploy with multiple workers or load balancer
4. **Persist Memory**: Swap InMemoryMemoryStore with Mem0 adapter
5. **Monitor**: Add logging/metrics endpoints

## Support

- **API Docs**: http://127.0.0.1:8000/docs (Swagger UI)
- **Tests**: See `tests/` directory
- **Examples**: See `examples/` directory

