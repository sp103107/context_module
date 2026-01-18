from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request, status as http_status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from aos_context.config import DEFAULT_CONFIG
from aos_context.context_brief import render_context_brief
from aos_context.episode import create_episode
from aos_context.ledger import FileLedger, utc_iso
from aos_context.memory import InMemoryMemoryStore
from aos_context.resume_pack import load_resume_pack, snapshot_resume_pack
from aos_context.ws_manager import WorkingSetManager

app = FastAPI(title="AoS Context v2.1", version="2.1.0")

# Mount static files
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

RUNS_ROOT = Path(os.environ.get("AOS_RUNS_ROOT", "./runs"))
RUNS_ROOT.mkdir(parents=True, exist_ok=True)

# MVP: single in-memory LTM store. Swap with Mem0.
MEMORY = InMemoryMemoryStore()

# Milestone token store: run_id -> (token, expires_at)
# Tokens expire after 5 minutes or when milestone completes
MILESTONE_TOKENS: Dict[str, Tuple[str, float]] = {}
TOKEN_TTL_SECONDS = 300  # 5 minutes


@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Global exception handler to prevent default FastAPI error JSON leakage.

    All contract endpoints must return structured error responses.
    Logs ERROR event to ledger if run_id is available.
    """
    run_id = None
    if hasattr(request, "path_params") and "run_id" in request.path_params:
        run_id = request.path_params["run_id"]

    error_detail = str(exc)
    if isinstance(exc, HTTPException):
        status_code = exc.status_code
        error_detail = exc.detail
    else:
        status_code = http_status.HTTP_500_INTERNAL_SERVER_ERROR

    # Log to ledger if run_id available
    if run_id:
        try:
            led = _ledger(run_id)
            led.append({
                "_schema_version": "2.1",
                "event_id": str(uuid.uuid4()),
                "parent_event_id": None,
                "sequence_id": None,
                "event_type": "ERROR",
                "timestamp": utc_iso(),
                "writer_id": "api",
                "task_id": "",
                "thread_id": "",
                "run_id": run_id,
                "payload": {
                    "error_type": type(exc).__name__,
                    "error_detail": error_detail,
                    "path": str(request.url.path),
                },
            })
        except Exception:
            pass  # Best effort logging

    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "error": error_detail,
            "error_type": type(exc).__name__,
        },
    )


class BootRequest(BaseModel):
    task_id: Optional[str] = None
    thread_id: Optional[str] = None
    objective: str
    acceptance_criteria: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)


class BootResponse(BaseModel):
    run_id: str
    ws: Dict[str, Any]


class PatchRequest(BaseModel):
    patch: Dict[str, Any]


class PatchResponse(BaseModel):
    ws: Dict[str, Any]
    context_brief: str


class MilestoneRequest(BaseModel):
    reason: str = "manual"
    memory_batch_id: Optional[str] = None
    next_entry_point: str = ""


class MilestoneResponse(BaseModel):
    episode_id: str
    episode_path: str
    committed_memory_ids: List[str]
    milestone_token: Optional[str] = None


class MemoryProposeRequest(BaseModel):
    mcrs: List[Dict[str, Any]] = Field(..., min_length=1)
    scope_filters: Dict[str, Any] = Field(default_factory=dict)


class MemoryProposeResponse(BaseModel):
    ok: bool
    batch_id: Optional[str] = None
    staged_count: int
    error: Optional[str] = None


class MemoryCommitRequest(BaseModel):
    batch_id: str
    milestone_token: Optional[str] = None
    allow_outside_milestone: bool = False  # Test override flag


class MemoryCommitResponse(BaseModel):
    ok: bool
    committed_ids: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class MemorySearchResponse(BaseModel):
    ok: bool
    items: List[Dict[str, Any]] = Field(default_factory=list)
    count: int
    error: Optional[str] = None


class ResumeSnapshotRequest(BaseModel):
    zip_pack: bool = True
    pointers: Dict[str, Any] = Field(default_factory=dict)


class ResumeSnapshotResponse(BaseModel):
    ok: bool
    pack_id: Optional[str] = None
    pack_dir: Optional[str] = None
    pack_zip: Optional[str] = None
    manifest_path: Optional[str] = None
    error: Optional[str] = None


class ResumeLoadRequest(BaseModel):
    pack_path: str
    new_run_id: Optional[str] = None


class ResumeLoadResponse(BaseModel):
    ok: bool
    run_id: Optional[str] = None
    ws: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@app.get("/")
async def root():
    """Redirect to static UI."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "version": "2.1.0"}


def _run_dir(run_id: str) -> Path:
    return RUNS_ROOT / run_id


def _wsm(run_id: str) -> WorkingSetManager:
    ws_path = _run_dir(run_id) / "state" / "working_set.v2.1.json"
    return WorkingSetManager(ws_path, config=DEFAULT_CONFIG)


def _ledger(run_id: str) -> FileLedger:
    return FileLedger(_run_dir(run_id) / "ledger" / "run.v2.1.jsonl")


def _generate_milestone_token(run_id: str) -> str:
    """Generate and store a milestone token for the run."""
    token = f"milestone_{uuid.uuid4().hex[:16]}"
    expires_at = time.time() + TOKEN_TTL_SECONDS
    MILESTONE_TOKENS[run_id] = (token, expires_at)
    return token


def _validate_milestone_token(run_id: str, token: Optional[str]) -> bool:
    """Validate milestone token for the run."""
    if not token:
        return False
    stored = MILESTONE_TOKENS.get(run_id)
    if not stored:
        return False
    stored_token, expires_at = stored
    if time.time() > expires_at:
        # Token expired, clean up
        MILESTONE_TOKENS.pop(run_id, None)
        return False
    return stored_token == token


def _clear_milestone_token(run_id: str) -> None:
    """Clear milestone token after commit or milestone completion."""
    MILESTONE_TOKENS.pop(run_id, None)


@app.post("/runs/boot", response_model=BootResponse)
def boot(req: BootRequest) -> BootResponse:
    run_id = f"run_{uuid.uuid4().hex}"
    rd = _run_dir(run_id)
    for sub in ["state", "ledger", "episodes", "resume", "artifacts"]:
        (rd / sub).mkdir(parents=True, exist_ok=True)

    wsm = _wsm(run_id)
    ws = wsm.create_initial(
        task_id=req.task_id or f"task_{uuid.uuid4().hex}",
        thread_id=req.thread_id or f"thread_{uuid.uuid4().hex}",
        run_id=run_id,
        objective=req.objective,
        acceptance_criteria=req.acceptance_criteria,
        constraints=req.constraints,
        current_stage="BOOT",
    )

    led = _ledger(run_id)
    led.append(
        {
            "_schema_version": "2.1",
            "event_id": str(uuid.uuid4()),
            "parent_event_id": None,
            "sequence_id": None,
            "event_type": "RUN_START",
            "timestamp": utc_iso(),
            "writer_id": "api",
            "task_id": ws["task_id"],
            "thread_id": ws["thread_id"],
            "run_id": ws["run_id"],
            "payload": {"config": DEFAULT_CONFIG.__dict__},
        }
    )

    return BootResponse(run_id=run_id, ws=ws)


@app.get("/runs/{run_id}/ws")
def get_ws(run_id: str) -> Dict[str, Any]:
    wsm = _wsm(run_id)
    if not wsm.exists():
        raise HTTPException(status_code=404, detail="run not found")
    return wsm.load()


@app.post("/runs/{run_id}/step/update", response_model=PatchResponse)
def step_update(run_id: str, req: PatchRequest) -> PatchResponse:
    wsm = _wsm(run_id)
    if not wsm.exists():
        raise HTTPException(status_code=404, detail="run not found")

    res = wsm.apply_patch(req.patch)
    if not res.ok:
        # optimistic lock errors surface as 409
        if res.error and res.error.startswith("LOCK_ERROR"):
            raise HTTPException(status_code=409, detail=res.error)
        raise HTTPException(status_code=400, detail=res.error)

    ws = res.new_ws or wsm.load()

    # Append WS_UPDATE event
    led = _ledger(run_id)
    led.append(
        {
            "_schema_version": "2.1",
            "event_id": str(uuid.uuid4()),
            "parent_event_id": None,
            "sequence_id": None,
            "event_type": "WS_UPDATE_APPLIED",
            "timestamp": utc_iso(),
            "writer_id": "api",
            "task_id": ws["task_id"],
            "thread_id": ws["thread_id"],
            "run_id": ws["run_id"],
            "payload": {"new_seq": ws["_update_seq"]},
        }
    )

    # Retrieve LTM (MVP: by project/user filters if present)
    ltm = MEMORY.search(
        ws.get("objective", ""),
        filters={"user_id": None, "project_id": None, "scope": None},
        top_k=8,
    )
    brief = render_context_brief(ws, ltm_results=ltm)

    return PatchResponse(ws=ws, context_brief=brief)


@app.post("/runs/{run_id}/milestone", response_model=MilestoneResponse)
def milestone(run_id: str, req: MilestoneRequest) -> MilestoneResponse:
    rd = _run_dir(run_id)
    wsm = _wsm(run_id)
    if not wsm.exists():
        raise HTTPException(status_code=404, detail="run not found")

    # Capture ws_after (current state)
    ws_after = wsm.load()

    # Find last episode to get ws_before (last milestone's ws_after)
    episodes_dir = rd / "episodes"
    ws_before = ws_after  # Default: use current if no prior episode
    if episodes_dir.exists():
        episodes = sorted(
            episodes_dir.glob("*.v2.1.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if episodes:
            try:
                last_ep = json.loads(episodes[0].read_text(encoding="utf-8"))
                ws_before = last_ep.get("ws_after", ws_after)
            except Exception:
                pass  # Fallback to current ws

    # Load ledger tail (naive)
    ledger_path = rd / "ledger" / "run.v2.1.jsonl"
    events: List[Dict[str, Any]] = []
    if ledger_path.exists():
        lines = ledger_path.read_text(encoding="utf-8").splitlines()[-200:]
        for line in lines:
            if line.strip():
                try:
                    events.append(json.loads(line))
                except Exception:
                    continue

    # Generate milestone token before processing
    milestone_token = _generate_milestone_token(run_id)

    committed: List[str] = []
    if req.memory_batch_id:
        cr = MEMORY.commit(req.memory_batch_id)
        if not cr.ok:
            detail = f"memory commit: {cr.error}"
            _clear_milestone_token(run_id)
            raise HTTPException(status_code=400, detail=detail)
        committed = cr.committed_ids or []

    ep = create_episode(
        episodes_dir=rd / "episodes",
        ws_before=ws_before,
        ws_after=ws_after,
        ledger_events_since_last=events,
        memory_commit_ids=committed,
        next_entry_point=req.next_entry_point,
    )
    if not ep.ok or not ep.episode_id or not ep.episode_path:
        _clear_milestone_token(run_id)
        raise HTTPException(status_code=500, detail=f"episode: {ep.error}")

    # Mark milestone in ledger
    led = _ledger(run_id)
    led.append(
        {
            "_schema_version": "2.1",
            "event_id": str(uuid.uuid4()),
            "parent_event_id": None,
            "sequence_id": None,
            "event_type": "MILESTONE",
            "timestamp": utc_iso(),
            "writer_id": "api",
            "task_id": ws_after["task_id"],
            "thread_id": ws_after["thread_id"],
            "run_id": ws_after["run_id"],
            "payload": {
                "reason": req.reason,
                "episode_id": ep.episode_id,
                "milestone_token": milestone_token,
            },
        }
    )

    # Clear token after milestone completes
    _clear_milestone_token(run_id)

    return MilestoneResponse(
        episode_id=ep.episode_id,
        episode_path=str(ep.episode_path),
        committed_memory_ids=committed,
        milestone_token=milestone_token,
    )


@app.post(
    "/runs/{run_id}/memory/propose", response_model=MemoryProposeResponse
)
def memory_propose(
    run_id: str, req: MemoryProposeRequest
) -> MemoryProposeResponse:
    """Stage memory change requests (MCRs) for later commit.

    Propose is allowed in loop. Commit only at milestone.
    """
    wsm = _wsm(run_id)
    if not wsm.exists():
        raise HTTPException(status_code=404, detail="run not found")

    ws = wsm.load()

    # Propose MCRs
    result = MEMORY.propose(req.mcrs, scope_filters=req.scope_filters)
    if not result.ok:
        return MemoryProposeResponse(
            ok=False,
            staged_count=0,
            error=result.error,
        )

    # Log to ledger
    led = _ledger(run_id)
    led.append({
        "_schema_version": "2.1",
        "event_id": str(uuid.uuid4()),
        "parent_event_id": None,
        "sequence_id": None,
        "event_type": "MEMORY_PROPOSE",
        "timestamp": utc_iso(),
        "writer_id": "api",
        "task_id": ws["task_id"],
        "thread_id": ws["thread_id"],
        "run_id": ws["run_id"],
        "payload": {
            "batch_id": result.batch_id,
            "mcr_count": len(req.mcrs),
        },
    })

    return MemoryProposeResponse(
        ok=True,
        batch_id=result.batch_id,
        staged_count=len(req.mcrs),
    )


@app.post(
    "/runs/{run_id}/memory/commit", response_model=MemoryCommitResponse
)
def memory_commit(
    run_id: str, req: MemoryCommitRequest
) -> MemoryCommitResponse:
    """Commit staged memory items.

    Milestone-only gate (default). Use allow_outside_milestone=True for tests.
    """
    wsm = _wsm(run_id)
    if not wsm.exists():
        raise HTTPException(status_code=404, detail="run not found")

    ws = wsm.load()

    # Check milestone gate: require milestone_token OR allow_outside_milestone (test mode only)
    test_mode = os.environ.get("AOS_TEST_MODE", "0") == "1"
    if not (test_mode and req.allow_outside_milestone):
        if not _validate_milestone_token(run_id, req.milestone_token):
            # Log ERROR event
            led = _ledger(run_id)
            led.append({
                "_schema_version": "2.1",
                "event_id": str(uuid.uuid4()),
                "parent_event_id": None,
                "sequence_id": None,
                "event_type": "ERROR",
                "timestamp": utc_iso(),
                "writer_id": "api",
                "task_id": ws["task_id"],
                "thread_id": ws["thread_id"],
                "run_id": ws["run_id"],
                "payload": {
                    "error_type": "MemoryCommitGateViolation",
                    "error_detail": (
                        "Memory commit requires valid milestone_token. "
                        "allow_outside_milestone only works with AOS_TEST_MODE=1"
                    ),
                    "batch_id": req.batch_id,
                },
            })

            return MemoryCommitResponse(
                ok=False,
                error=(
                    "Memory commit requires milestone_token from milestone "
                    "endpoint. allow_outside_milestone only works with "
                    "AOS_TEST_MODE=1 environment variable."
                ),
            )

    # Commit
    result = MEMORY.commit(req.batch_id)
    if not result.ok:
        return MemoryCommitResponse(
            ok=False,
            error=result.error,
        )

    # Clear milestone token after successful commit
    if req.milestone_token:
        _clear_milestone_token(run_id)

    # Log to ledger
    led = _ledger(run_id)
    led.append({
        "_schema_version": "2.1",
        "event_id": str(uuid.uuid4()),
        "parent_event_id": None,
        "sequence_id": None,
        "event_type": "MEMORY_COMMIT",
        "timestamp": utc_iso(),
        "writer_id": "api",
        "task_id": ws["task_id"],
        "thread_id": ws["thread_id"],
        "run_id": ws["run_id"],
        "payload": {
            "batch_id": req.batch_id,
            "committed_count": len(result.committed_ids or []),
            "committed_ids": result.committed_ids or [],
            "milestone_token_used": req.milestone_token is not None,
        },
    })

    return MemoryCommitResponse(
        ok=True,
        committed_ids=result.committed_ids or [],
    )


@app.get(
    "/runs/{run_id}/memory/search", response_model=MemorySearchResponse
)
def memory_search(
    run_id: str,
    q: str = "",
    top_k: int = 8,
    scope: Optional[str] = None,
    status: str = "active",
) -> MemorySearchResponse:
    """Search long-term memory with filters.

    Default status=active. Filters by scope if provided.
    """
    wsm = _wsm(run_id)
    if not wsm.exists():
        raise HTTPException(status_code=404, detail="run not found")

    # Build filters
    filters: Dict[str, Any] = {}
    if scope:
        filters["scope"] = scope
    if status:
        filters["status"] = status

    # Search (memory store filters by status internally)
    results = MEMORY.search(query=q, filters=filters, top_k=top_k)

    # Format results
    items = []
    for mem in results:
        items.append({
            "memory_id": mem.get("memory_id", ""),
            "content": mem.get("content", ""),
            "confidence": mem.get("confidence", 0.0),
            "type": mem.get("type", ""),
            "scope": mem.get("scope", ""),
            "status": mem.get("status", ""),
        })

    return MemorySearchResponse(
        ok=True,
        items=items,
        count=len(items),
    )


@app.post(
    "/runs/{run_id}/resume/snapshot", response_model=ResumeSnapshotResponse
)
def resume_snapshot(
    run_id: str, req: ResumeSnapshotRequest
) -> ResumeSnapshotResponse:
    """Create a resume pack snapshot (manifest + optional zip).

    Returns pack paths and manifest hashes.
    """
    rd = _run_dir(run_id)
    wsm = _wsm(run_id)
    if not wsm.exists():
        raise HTTPException(status_code=404, detail="run not found")

    ws = wsm.load()

    # Get last ledger sequence for pointer
    led = _ledger(run_id)
    ledger_path = rd / "ledger" / "run.v2.1.jsonl"
    last_seq = 0
    if ledger_path.exists():
        lines = ledger_path.read_text(encoding="utf-8").strip().splitlines()
        if lines:
            try:
                last_event = json.loads(lines[-1])
                last_seq = last_event.get("sequence_id", 0)
            except Exception:
                pass

    pointers = dict(req.pointers)
    pointers["ledger_last_seq"] = last_seq

    result = snapshot_resume_pack(
        run_dir=rd,
        output_dir=rd / "resume",
        zip_pack=req.zip_pack,
        pointers=pointers,
    )

    if not result.ok:
        return ResumeSnapshotResponse(ok=False, error=result.error)

    # Log to ledger
    led.append({
        "_schema_version": "2.1",
        "event_id": str(uuid.uuid4()),
        "parent_event_id": None,
        "sequence_id": None,
        "event_type": "RESUME_SNAPSHOT",
        "timestamp": utc_iso(),
        "writer_id": "api",
        "task_id": ws["task_id"],
        "thread_id": ws["thread_id"],
        "run_id": ws["run_id"],
        "payload": {
            "pack_id": result.pack_id,
            "pack_dir": str(result.pack_dir) if result.pack_dir else None,
            "pack_zip": str(result.pack_zip) if result.pack_zip else None,
        },
    })

    return ResumeSnapshotResponse(
        ok=True,
        pack_id=result.pack_id,
        pack_dir=str(result.pack_dir) if result.pack_dir else None,
        pack_zip=str(result.pack_zip) if result.pack_zip else None,
        manifest_path=str(result.manifest_path) if result.manifest_path else None,
    )


@app.post("/runs/resume/load", response_model=ResumeLoadResponse)
def resume_load(req: ResumeLoadRequest) -> ResumeLoadResponse:
    """Load a resume pack into a new run.

    Creates new run_id (or uses provided one).
    Validates manifest and file hashes.
    Handles missing LTM IDs gracefully.
    """
    pack_path = Path(req.pack_path)
    if not pack_path.exists():
        return ResumeLoadResponse(
            ok=False, error=f"pack path not found: {req.pack_path}"
        )

    # Determine target run directory
    if req.new_run_id:
        target_run_dir = RUNS_ROOT / req.new_run_id
        if target_run_dir.exists():
            return ResumeLoadResponse(
                ok=False,
                error=f"run_id already exists: {req.new_run_id}",
            )
    else:
        # Will be created by load_resume_pack
        target_run_dir = RUNS_ROOT / "temp_load"

    result = load_resume_pack(
        pack_path=pack_path,
        target_run_dir=target_run_dir,
        new_run_id=req.new_run_id,
    )

    if not result.ok:
        return ResumeLoadResponse(ok=False, error=result.error)

    # Create RUN_START event in ledger
    led = _ledger(result.run_id or "")
    led.append({
        "_schema_version": "2.1",
        "event_id": str(uuid.uuid4()),
        "parent_event_id": None,
        "sequence_id": None,
        "event_type": "RUN_START",
        "timestamp": utc_iso(),
        "writer_id": "api",
        "task_id": result.ws["task_id"] if result.ws else "",
        "thread_id": result.ws["thread_id"] if result.ws else "",
        "run_id": result.run_id or "",
        "payload": {
            "source": "resume_pack_load",
            "pack_path": str(pack_path),
        },
    })

    return ResumeLoadResponse(
        ok=True,
        run_id=result.run_id,
        ws=result.ws,
    )
