# AoS Context Management v2.1 — Schemas + Python Reference Implementation

This repo is a **ready-to-run** implementation of the **Context Management v2.1** spec:

- **WS (Working Set)**: hot mutable state with optimistic locking + deterministic eviction
- **RL (Run Ledger)**: append-only JSONL audit log
- **EP (Episodes)**: immutable milestone checkpoints
- **LTM (Long-Term Memory)**: gated propose/commit workflow (MVP in-memory store; swap with Mem0)
- **Resume Pack**: portable snapshot with manifest hashes

All persisted artifacts are validated against **Draft 2020-12 JSON Schema** with `additionalProperties:false`.

## Quickstart (CLI)

```bash
cd aos_context_v2_1
python -m aos_context.cli demo --root ./runs
```

## Quickstart (API)

```bash
cd aos_context_v2_1
uvicorn aos_context.api.main:app --reload --port 8000
```

### Boot a run

```bash
curl -sS -X POST http://127.0.0.1:8000/runs/boot \
  -H 'Content-Type: application/json' \
  -d '{
    "objective": "Generate schemas and implement WS/RL/EP for my agent factory.",
    "acceptance_criteria": ["Schemas validate", "WS patch applies", "Ledger appends"],
    "constraints": ["No unknown WS fields", "Commit memory only at milestones"]
  }' | jq
```

### Apply a WS patch

1) GET the current WS to read `_update_seq`.
2) POST a patch with `expected_seq` = current `_update_seq`.

```bash
curl -sS http://127.0.0.1:8000/runs/<run_id>/ws | jq

curl -sS -X POST http://127.0.0.1:8000/runs/<run_id>/step/update \
  -H 'Content-Type: application/json' \
  -d '{
    "patch": {
      "_schema_version": "2.1",
      "expected_seq": 0,
      "set": {
        "status": "BUSY",
        "current_stage": "PLAN",
        "next_action": "Write strict schemas for all artifacts.",
        "sliding_context": [
          {"id": "ctx1", "content": "Use pinned+sliding contexts.", "timestamp": "2026-01-18T00:00:00Z", "priority": 2}
        ]
      }
    }
  }' | jq
```

### Create a milestone (episode)

```bash
curl -sS -X POST http://127.0.0.1:8000/runs/<run_id>/milestone \
  -H 'Content-Type: application/json' \
  -d '{"reason": "checkpoint", "next_entry_point": "Continue from PLAN stage."}' | jq
```

### Memory Operations

#### Propose memory (stage MCRs)

```bash
curl -sS -X POST http://127.0.0.1:8000/runs/<run_id>/memory/propose \
  -H 'Content-Type: application/json' \
  -d '{
    "mcrs": [
      {
        "_schema_version": "2.1",
        "op": "add",
        "type": "fact",
        "scope": "global",
        "content": "User prefers Python over JavaScript",
        "confidence": 0.9,
        "rationale": "Observed in multiple conversations",
        "source_refs": []
      }
    ],
    "scope_filters": {}
  }' | jq
```

#### Commit memory (milestone-only gate)

```bash
# Only works during milestone phase (or with allow_outside_milestone=true for tests)
curl -sS -X POST http://127.0.0.1:8000/runs/<run_id>/memory/commit \
  -H 'Content-Type: application/json' \
  -d '{
    "batch_id": "batch_...",
    "allow_outside_milestone": false
  }' | jq
```

#### Search memory

```bash
curl -sS "http://127.0.0.1:8000/runs/<run_id>/memory/search?q=python&top_k=10&scope=global&status=active" | jq
```

### Resume Pack Operations

#### Snapshot resume pack

```bash
curl -sS -X POST http://127.0.0.1:8000/runs/<run_id>/resume/snapshot \
  -H 'Content-Type: application/json' \
  -d '{
    "zip_pack": true,
    "pointers": {"ledger_last_seq": 42}
  }' | jq
```

#### Load resume pack

```bash
curl -sS -X POST http://127.0.0.1:8000/runs/resume/load \
  -H 'Content-Type: application/json' \
  -d '{
    "pack_path": "./runs/<run_id>/resume/pack_<id>.zip",
    "new_run_id": null
  }' | jq
```

## Web UI

Access the control panel at `http://127.0.0.1:8000/` (redirects to `/static/index.html`).

The UI provides:
- Boot runs
- View and update working sets
- Propose and search memory
- Create milestones
- Snapshot and load resume packs

## End-to-End Demo Flow

```bash
# 1. Boot a run
RUN_ID=$(curl -sS -X POST http://127.0.0.1:8000/runs/boot \
  -H 'Content-Type: application/json' \
  -d '{"objective": "Test end-to-end flow"}' | jq -r '.run_id')

# 2. Patch WS
curl -sS -X POST http://127.0.0.1:8000/runs/$RUN_ID/step/update \
  -H 'Content-Type: application/json' \
  -d '{
    "patch": {
      "_schema_version": "2.1",
      "expected_seq": 0,
      "set": {"status": "BUSY", "next_action": "Test memory"}
    }
  }' | jq

# 3. Propose memory
BATCH_ID=$(curl -sS -X POST http://127.0.0.1:8000/runs/$RUN_ID/memory/propose \
  -H 'Content-Type: application/json' \
  -d '{
    "mcrs": [{
      "_schema_version": "2.1",
      "op": "add",
      "type": "fact",
      "scope": "global",
      "content": "Test memory item",
      "confidence": 0.8,
      "rationale": "Testing",
      "source_refs": []
    }]
  }' | jq -r '.batch_id')

# 4. Create milestone (commits memory)
curl -sS -X POST http://127.0.0.1:8000/runs/$RUN_ID/milestone \
  -H 'Content-Type: application/json' \
  -d "{\"reason\": \"checkpoint\", \"memory_batch_id\": \"$BATCH_ID\"}" | jq

# 5. Snapshot resume pack
curl -sS -X POST http://127.0.0.1:8000/runs/$RUN_ID/resume/snapshot \
  -H 'Content-Type: application/json' \
  -d '{"zip_pack": true}' | jq
```

## Files and Layout

- `aos_context/schemas/` — strict Draft 2020-12 schemas
- `aos_context/ws_manager.py` — optimistic lock + deterministic eviction
- `aos_context/ledger.py` — append-only JSONL ledger
- `aos_context/context_brief.py` — stable markdown injection template
- `aos_context/episode.py` — milestone checkpoint generation
- `aos_context/resume_pack.py` — portable snapshot + manifest
- `aos_context/memory.py` — MVP memory store (replace with Mem0)

## Standalone Module Use

This module can be imported and used programmatically:

```python
from aos_context.ws_manager import WorkingSetManager
from aos_context.ledger import FileLedger
from aos_context.memory import InMemoryMemoryStore
from aos_context.config import DEFAULT_CONFIG
from pathlib import Path

# Initialize components
ws_path = Path("./runs/my_run/state/working_set.v2.1.json")
wsm = WorkingSetManager(ws_path, config=DEFAULT_CONFIG)

# Create initial WS
ws = wsm.create_initial(
    task_id="task_123",
    thread_id="thread_456",
    run_id="run_789",
    objective="My objective",
    acceptance_criteria=["Criterion 1"],
    constraints=["Constraint 1"],
)

# Apply patch with optimistic locking
result = wsm.apply_patch({
    "_schema_version": "2.1",
    "expected_seq": 0,
    "set": {"status": "BUSY", "next_action": "Do something"}
})

# Use ledger
ledger = FileLedger(Path("./runs/my_run/ledger/run.v2.1.jsonl"))
ledger.append({
    "_schema_version": "2.1",
    "event_id": "...",
    "event_type": "WS_UPDATE_APPLIED",
    # ... other fields
})

# Use memory store
memory = InMemoryMemoryStore()
propose_result = memory.propose([{...}], scope_filters={})
commit_result = memory.commit(propose_result.batch_id)
```

## Replace LTM with Mem0

Swap `InMemoryMemoryStore` with a Mem0 adapter that implements:

- `search(query, filters, top_k)`
- `propose(mcrs, scope_filters)`
- `commit(batch_id)`

Keep the **Double-Key Commit** rule: propose in the loop; commit only at milestone.
