from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from aos_context.config import DEFAULT_CONFIG
from aos_context.memory import InMemoryMemoryStore, MemoryStore
from aos_context.ws_manager import WorkingSetManager, WSLockError

app = FastAPI(title="AoS Context Server", version="2.1.0")

# Workspace directory for storing runs
WORKSPACE_DIR = Path("./server_workspace")
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

# Global cache of active managers
active_managers: Dict[str, WorkingSetManager] = {}

# Initialize memory store
# Default: InMemoryMemoryStore
# For Qdrant: Set QDRANT_URL and QDRANT_COLLECTION env vars
memory_store: MemoryStore

if os.environ.get("QDRANT_URL"):
    # Qdrant configuration from environment
    from qdrant_client import QdrantClient
    from aos_context.memory_qdrant import QdrantMemoryStore

    qdrant_url = os.environ.get("QDRANT_URL", "http://localhost:6333")
    collection_name = os.environ.get(
        "QDRANT_COLLECTION", "agent_memories"
    )

    # Create Qdrant client
    client = QdrantClient(url=qdrant_url)

    # Embedding function - can be overridden via env var
    # Default: dummy embedder (for testing)
    # In production, use OpenAI or HuggingFace
    def dummy_embedder(text: str) -> List[float]:
        # Simple hash-based embedding for testing
        # In production, replace with real embedding model
        import hashlib
        h = hashlib.md5(text.encode()).hexdigest()
        return [float(int(h[i : i + 2], 16)) / 255.0 for i in range(0, 16, 2)][:384]

    embedding_fn = dummy_embedder

    # Try to create collection if it doesn't exist
    try:
        from qdrant_client.http import models

        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=len(embedding_fn("test")), distance=models.Distance.COSINE
            ),
        )
    except Exception:
        pass  # Collection might already exist

    memory_store = QdrantMemoryStore(
        client=client,
        collection_name=collection_name,
        embedding_fn=embedding_fn,
    )
else:
    # Default: In-memory store
    memory_store = InMemoryMemoryStore()


def get_manager(run_id: str) -> WorkingSetManager:
    """Get or load WorkingSetManager for a run_id.

    Checks cache first, then loads from disk if exists.
    Raises 404 if not found.

    Args:
        run_id: Run identifier

    Returns:
        WorkingSetManager instance

    Raises:
        HTTPException: 404 if run not found
    """
    # Check cache
    if run_id in active_managers:
        return active_managers[run_id]

    # Check if run exists on disk
    run_dir = WORKSPACE_DIR / run_id
    ws_path = run_dir / "state" / "working_set.v2.1.json"

    if ws_path.exists():
        # Load existing manager
        wsm = WorkingSetManager(ws_path)
        active_managers[run_id] = wsm
        return wsm

    # Not found
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Run {run_id} not found",
    )


# Request/Response Models
class CreateRunRequest(BaseModel):
    task_id: Optional[str] = None
    thread_id: Optional[str] = None
    run_id: Optional[str] = None
    objective: str
    acceptance_criteria: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)


class CreateRunResponse(BaseModel):
    run_id: str
    status: str


class PatchRunRequest(BaseModel):
    patch: Dict[str, Any]
    expected_seq: int


class PatchRunResponse(BaseModel):
    ok: bool
    ws: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ProposeMemoryRequest(BaseModel):
    mcrs: List[Dict[str, Any]]
    scope_filters: Dict[str, Any] = Field(default_factory=dict)


class ProposeMemoryResponse(BaseModel):
    ok: bool
    batch_id: Optional[str] = None
    error: Optional[str] = None


class CommitMemoryRequest(BaseModel):
    batch_id: str


class CommitMemoryResponse(BaseModel):
    ok: bool
    committed_ids: Optional[List[str]] = None
    error: Optional[str] = None


class SnapshotResponse(BaseModel):
    ok: bool
    pack_path: Optional[str] = None
    error: Optional[str] = None


# API Endpoints
@app.post("/runs", response_model=CreateRunResponse)
async def create_run(req: CreateRunRequest) -> CreateRunResponse:
    """Create a new run and initialize WorkingSetManager.

    Args:
        req: Run creation request

    Returns:
        CreateRunResponse with run_id and status
    """
    # Generate run_id if not provided
    run_id = req.run_id or f"run_{uuid.uuid4().hex[:16]}"

    # Generate task_id and thread_id if not provided
    task_id = req.task_id or f"task_{uuid.uuid4().hex[:16]}"
    thread_id = req.thread_id or f"thread_{uuid.uuid4().hex[:16]}"

    # Create run directory
    run_dir = WORKSPACE_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Initialize WorkingSetManager
    ws_path = run_dir / "state" / "working_set.v2.1.json"
    wsm = WorkingSetManager(ws_path, config=DEFAULT_CONFIG)

    # Create initial working set
    ws = wsm.create_initial(
        task_id=task_id,
        thread_id=thread_id,
        run_id=run_id,
        objective=req.objective,
        acceptance_criteria=req.acceptance_criteria,
        constraints=req.constraints,
    )

    # Cache manager
    active_managers[run_id] = wsm

    return CreateRunResponse(run_id=run_id, status=ws["status"])


@app.get("/runs/{run_id}")
async def get_run(run_id: str) -> Dict[str, Any]:
    """Get full working set state for a run.

    Args:
        run_id: Run identifier

    Returns:
        Full working set JSON
    """
    wsm = get_manager(run_id)
    return wsm.load()


@app.patch("/runs/{run_id}", response_model=PatchRunResponse)
async def patch_run(run_id: str, req: PatchRunRequest) -> PatchRunResponse:
    """Update working set with optimistic locking.

    Args:
        run_id: Run identifier
        req: Patch request with patch dict and expected_seq

    Returns:
        PatchRunResponse with updated WS or error
    """
    wsm = get_manager(run_id)

    # Build patch dict
    patch = {
        "_schema_version": "2.1",
        "expected_seq": req.expected_seq,
        "set": req.patch,
    }

    try:
        result = wsm.apply_patch(patch)
        if result.ok:
            return PatchRunResponse(ok=True, ws=result.new_ws)
        else:
            # Check if it's a lock error
            if "LOCK_ERROR" in (result.error or ""):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Conflict: State has changed. Reload and retry.",
                )
            return PatchRunResponse(ok=False, error=result.error)
    except WSLockError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflict: State has changed. Reload and retry.",
        )


@app.post("/runs/{run_id}/memory/propose", response_model=ProposeMemoryResponse)
async def propose_memory(
    run_id: str, req: ProposeMemoryRequest
) -> ProposeMemoryResponse:
    """Propose memory change requests (MCRs) for staging.

    Args:
        run_id: Run identifier
        req: Propose request with MCRs and scope filters

    Returns:
        ProposeMemoryResponse with batch_id
    """
    # Verify run exists
    get_manager(run_id)

    result = memory_store.propose(req.mcrs, scope_filters=req.scope_filters)
    if result.ok:
        return ProposeMemoryResponse(ok=True, batch_id=result.batch_id)
    else:
        return ProposeMemoryResponse(ok=False, error=result.error)


@app.post("/runs/{run_id}/memory/commit", response_model=CommitMemoryResponse)
async def commit_memory(
    run_id: str, req: CommitMemoryRequest
) -> CommitMemoryResponse:
    """Commit staged memory batch to active status.

    Args:
        run_id: Run identifier
        req: Commit request with batch_id

    Returns:
        CommitMemoryResponse with committed memory IDs
    """
    # Verify run exists
    get_manager(run_id)

    result = memory_store.commit(req.batch_id)
    if result.ok:
        return CommitMemoryResponse(
            ok=True, committed_ids=result.committed_ids
        )
    else:
        return CommitMemoryResponse(ok=False, error=result.error)


@app.post("/runs/{run_id}/snapshot", response_model=SnapshotResponse)
async def snapshot_run(run_id: str) -> SnapshotResponse:
    """Create a resume pack snapshot for a run.

    Args:
        run_id: Run identifier

    Returns:
        SnapshotResponse with pack path
    """
    wsm = get_manager(run_id)

    # Create snapshots directory
    snapshots_dir = WORKSPACE_DIR / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    try:
        pack_path = wsm.create_resume_pack(snapshots_dir)
        return SnapshotResponse(ok=True, pack_path=str(pack_path))
    except Exception as e:
        return SnapshotResponse(ok=False, error=str(e))


@app.get("/health")
async def health() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "aos-context-server"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

