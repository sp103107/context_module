# Quick Start Guide

## 1. Start the Server

```bash
# Install dependencies (if not already done)
pip install -e ".[dev]"

# Start server
uvicorn aos_context.api.main:app --reload --port 8000
```

Server will be available at: **http://127.0.0.1:8000**

## 2. Access the Web UI

Open your browser: **http://127.0.0.1:8000**

You'll see the control panel with 6 sections:
1. Boot Run
2. Working Set Viewer
3. Update Working Set
4. Memory Operations
5. Milestone
6. Resume Pack

## 3. Basic Workflow (Web UI)

1. **Boot a Run**:
   - Enter objective: "Build a web scraper"
   - Add acceptance criteria (one per line)
   - Add constraints (one per line)
   - Click "Boot Run"
   - Run ID auto-fills in all sections

2. **View Working Set**:
   - Run ID is already filled
   - Click "Load WS"
   - See current state and `_update_seq`

3. **Update Working Set**:
   - Expected Sequence auto-filled from WS
   - Enter patch JSON:
     ```json
     {
       "status": "BUSY",
       "next_action": "Start scraping"
     }
     ```
   - Click "Apply Patch"

4. **Propose Memory**:
   - Enter MCR JSON array
   - Click "Propose"
   - Batch ID auto-fills in Milestone section

5. **Create Milestone**:
   - Batch ID already filled
   - Enter reason: "checkpoint"
   - Click "Create Milestone"
   - See episode ID and milestone_token

6. **Snapshot Resume Pack**:
   - Click "Snapshot"
   - Get pack ID and path

## 4. Using in Your Agent Repo

### Install as Dependency

```bash
# In your agent repo
pip install git+https://github.com/your-org/aos_context_v2_1.git
# OR
pip install -e /path/to/aos_context_v2_1
```

### Use HTTP Client

```python
from context_client import AoSContextClient

context = AoSContextClient("http://127.0.0.1:8000")

# Boot run
result = context.boot_run(objective="My task")
run_id = result["run_id"]

# Get WS
ws = context.get_ws(run_id)

# Update WS
context.update_ws(
    run_id=run_id,
    expected_seq=ws["_update_seq"],
    patch={"status": "BUSY"}
)
```

### Use Direct Import

```python
from aos_context.ws_manager import WorkingSetManager
from aos_context.config import DEFAULT_CONFIG
from pathlib import Path

wsm = WorkingSetManager(
    Path("./runs/my_run/state/working_set.v2.1.json"),
    config=DEFAULT_CONFIG
)
```

## 5. Environment Variables

```bash
# Set runs directory
export AOS_RUNS_ROOT=/path/to/runs

# Enable test mode (allows memory commit bypass)
export AOS_TEST_MODE=1

# Start server
uvicorn aos_context.api.main:app --reload
```

## 6. API Documentation

FastAPI auto-generates docs at: **http://127.0.0.1:8000/docs**

Interactive Swagger UI for testing endpoints.

## 7. Health Check

```bash
curl http://127.0.0.1:8000/health
# Returns: {"status": "ok", "version": "2.1.0"}
```

## Troubleshooting

**Port already in use?**
```bash
uvicorn aos_context.api.main:app --reload --port 8001
```

**Can't access UI?**
- Check server is running
- Verify port matches (default 8000)
- Check firewall settings

**Memory commit fails?**
- Ensure you have milestone_token from milestone endpoint
- Or set AOS_TEST_MODE=1 for testing

**Runs not persisting?**
- Check AOS_RUNS_ROOT environment variable
- Verify write permissions on runs directory

