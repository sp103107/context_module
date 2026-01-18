# Frontend UI Map

## Visual Layout

```
┌─────────────────────────────────────────────────────────────────┐
│                    AoS Context v2.1                             │
│                   Control Panel                                 │
│              http://127.0.0.1:8000/                             │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  SECTION 1: BOOT RUN                                            │
├─────────────────────────────────────────────────────────────────┤
│  Objective: [textarea - multi-line]                              │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Generate schemas and implement WS/RL/EP for my agent...  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Acceptance Criteria: [textarea - one per line]                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Schemas validate                                          │  │
│  │ WS patch applies                                          │  │
│  │ Ledger appends                                            │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Constraints: [textarea - one per line]                         │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ No unknown WS fields                                      │  │
│  │ Commit memory only at milestones                          │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  [Boot Run] ← Button                                            │
│                                                                  │
│  Output: [JSON response with run_id]                            │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  SECTION 2: WORKING SET                                         │
├─────────────────────────────────────────────────────────────────┤
│  Run ID: [run_abc123...] [Load WS] ← Button                     │
│                                                                  │
│  Output: [Full WS JSON with _update_seq highlighted]           │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ {                                                         │  │
│  │   "_update_seq": 0,  ← Auto-copied to Section 3         │  │
│  │   "status": "BOOT",                                       │  │
│  │   "objective": "...",                                     │  │
│  │   ...                                                     │  │
│  │ }                                                         │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  SECTION 3: UPDATE WORKING SET                                  │
├─────────────────────────────────────────────────────────────────┤
│  Run ID: [run_abc123...]                                        │
│  Expected Sequence: [0] ← Auto-filled from Section 2            │
│                                                                  │
│  WS Patch (JSON): [textarea]                                    │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ {                                                         │  │
│  │   "set": {                                                │  │
│  │     "status": "BUSY",                                     │  │
│  │     "next_action": "Write schemas..."                     │  │
│  │   }                                                       │  │
│  │ }                                                         │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  [Apply Patch] ← Button                                         │
│                                                                  │
│  Output: [Updated WS + Context Brief]                          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  SECTION 4: MEMORY OPERATIONS                                   │
├─────────────────────────────────────────────────────────────────┤
│  Run ID: [run_abc123...]                                        │
│                                                                  │
│  Propose Memory (MCR JSON array): [textarea]                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ [{                                                        │  │
│  │   "_schema_version": "2.1",                               │  │
│  │   "op": "add",                                            │  │
│  │   "type": "fact",                                         │  │
│  │   "scope": "global",                                      │  │
│  │   "content": "User prefers Python",                       │  │
│  │   "confidence": 0.9,                                      │  │
│  │   "rationale": "Observed",                                 │  │
│  │   "source_refs": []                                       │  │
│  │ }]                                                        │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  [Propose] [Search] ← Buttons                                   │
│                                                                  │
│  Output: [Batch ID (auto-fills Section 5) or Search Results]   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  SECTION 5: MILESTONE                                           │
├─────────────────────────────────────────────────────────────────┤
│  Run ID: [run_abc123...]                                        │
│  Memory Batch ID: [batch_xyz...] ← Auto-filled from Section 4   │
│  Reason: [checkpoint]                                           │
│  Next Entry Point: [textarea]                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Continue from PLAN stage.                                 │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  [Create Milestone] ← Button                                    │
│                                                                  │
│  Output: [Episode ID, Path, Committed IDs, milestone_token]      │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  SECTION 6: RESUME PACK                                         │
├─────────────────────────────────────────────────────────────────┤
│  Run ID: [run_abc123...]                                        │
│                                                                  │
│  [Snapshot] [Load Pack] ← Buttons                               │
│                                                                  │
│  Pack Path (for load): [input]                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ ./runs/run_abc123/resume/pack_xyz.zip                    │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Output: [Pack ID, Path, Manifest] or [New Run ID]             │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

```
User Input → JavaScript → Fetch API → FastAPI → Response → Display

Example Flow:
1. User enters objective → clicks "Boot Run"
2. JS: fetch('/runs/boot', {method: 'POST', body: JSON.stringify(...)})
3. FastAPI: Creates run, returns {run_id, ws}
4. JS: Auto-fills run_id in all sections
5. Display: Shows run_id and initial WS
```

## State Management

### Auto-Fill Chain

```
Boot Run
  ↓
run_id → All sections
  ↓
Load WS
  ↓
_update_seq → Section 3 (Expected Sequence)
  ↓
Propose Memory
  ↓
batch_id → Section 5 (Memory Batch ID)
  ↓
Create Milestone
  ↓
milestone_token → Display (for manual commit if needed)
```

### User Actions

1. **Boot**: Creates run, auto-fills run_id everywhere
2. **Load WS**: Shows current state, auto-fills expected_seq
3. **Patch**: Updates WS, refreshes expected_seq
4. **Propose**: Stages memory, auto-fills batch_id
5. **Milestone**: Creates checkpoint, shows token
6. **Snapshot**: Creates pack, shows path

## Color Coding

- **Blue buttons**: Primary actions (#007bff)
- **Green output**: Success responses
- **Red output**: Error responses
- **Gray borders**: Section dividers
- **White cards**: Content sections

## Responsive Design

- **Desktop**: Max-width 1200px, centered
- **Tablet**: Same layout, smaller padding
- **Mobile**: Stack sections vertically

## Error Handling

All errors show in red `<pre>` blocks:
```json
{
  "ok": false,
  "error": "Memory commit requires milestone_token..."
}
```

Success shows in green:
```json
{
  "ok": true,
  "run_id": "run_abc123",
  "ws": {...}
}
```

