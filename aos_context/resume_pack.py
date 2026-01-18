from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from aos_context.ledger import utc_iso
from aos_context.validation import assert_valid


@dataclass
class ResumePackResult:
    ok: bool
    pack_dir: Optional[Path] = None
    pack_zip: Optional[Path] = None
    manifest_path: Optional[Path] = None
    pack_id: Optional[str] = None
    error: Optional[str] = None


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_resume_pack(
    *,
    run_dir: Path,
    output_dir: Path,
    engine_versions: Optional[list[str]] = None,
    pointers: Optional[Dict[str, Any]] = None,
    zip_pack: bool = True,
) -> ResumePackResult:
    """Create a portable Resume Pack directory (and optional zip).

    Pack contains:
    - state/working_set.v2.1.json
    - episodes/last_episode.v2.1.json (if present)
    - ledger/run.v2.1.jsonl
    - manifest.v2.1.json

    Only relative paths are stored in manifest.
    """

    engine_versions = engine_versions or ["aos-context/2.1.0"]
    pointers = pointers or {}

    pack_id = f"pack_{uuid.uuid4().hex}"
    pack_dir = output_dir / pack_id
    if pack_dir.exists():
        shutil.rmtree(pack_dir)
    pack_dir.mkdir(parents=True, exist_ok=True)

    # Copy canonical files if they exist
    files_to_copy = []
    ws_path = run_dir / "state" / "working_set.v2.1.json"
    if ws_path.exists():
        files_to_copy.append(ws_path)
    ledger_path = run_dir / "ledger" / "run.v2.1.jsonl"
    if ledger_path.exists():
        files_to_copy.append(ledger_path)

    # last episode is the newest by mtime
    episodes_dir = run_dir / "episodes"
    last_ep = None
    if episodes_dir.exists():
        eps = sorted(episodes_dir.glob("*.v2.1.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if eps:
            last_ep = eps[0]
            files_to_copy.append(last_ep)

    rel_map: Dict[str, str] = {}
    for src in files_to_copy:
        rel = src.relative_to(run_dir)
        dst = pack_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        rel_map[str(rel)] = _sha256_file(dst)

    manifest: Dict[str, Any] = {
        "_schema_version": "2.1",
        "pack_id": pack_id,
        "created_at": utc_iso(),
        "compatible_engine_versions": engine_versions,
        "files": rel_map,
        "pointers": pointers,
    }

    try:
        assert_valid("resume_pack_manifest.v2.1.schema.json", manifest)
    except Exception as e:
        return ResumePackResult(ok=False, error=f"manifest schema: {e}")

    manifest_path = pack_dir / "manifest.v2.1.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    pack_zip = None
    if zip_pack:
        pack_zip = output_dir / f"{pack_id}.zip"
        if pack_zip.exists():
            pack_zip.unlink()
        shutil.make_archive(str(pack_zip).replace(".zip", ""), "zip", root_dir=pack_dir)

    return ResumePackResult(ok=True, pack_dir=pack_dir, pack_zip=pack_zip, manifest_path=manifest_path, pack_id=pack_id)


@dataclass
class LoadResumePackResult:
    ok: bool
    run_id: Optional[str] = None
    ws: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


def load_resume_pack(
    *,
    pack_path: Path,
    target_run_dir: Path,
    new_run_id: Optional[str] = None,
) -> LoadResumePackResult:
    """Load a resume pack into a target run directory.

    If pack_path is a zip, extracts it first.
    Validates manifest and file hashes.
    Handles missing LTM IDs gracefully (treats as hints).
    """
    import zipfile

    # Extract if zip
    if pack_path.suffix == ".zip":
        extract_dir = pack_path.parent / pack_path.stem
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(pack_path, "r") as zf:
                zf.extractall(extract_dir)
            pack_dir = extract_dir
        except Exception as e:
            return LoadResumePackResult(ok=False, error=f"extract zip: {e}")
    else:
        pack_dir = pack_path

    # Load and validate manifest
    manifest_path = pack_dir / "manifest.v2.1.json"
    if not manifest_path.exists():
        return LoadResumePackResult(ok=False, error="manifest not found")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert_valid("resume_pack_manifest.v2.1.schema.json", manifest)
    except Exception as e:
        return LoadResumePackResult(ok=False, error=f"manifest invalid: {e}")

    # Verify file hashes
    files = manifest.get("files", {})
    for rel_path, expected_hash in files.items():
        src_file = pack_dir / rel_path
        if not src_file.exists():
            return LoadResumePackResult(
                ok=False, error=f"missing file in pack: {rel_path}"
            )
        actual_hash = _sha256_file(src_file)
        if actual_hash != expected_hash:
            return LoadResumePackResult(
                ok=False,
                error=f"hash mismatch for {rel_path}: expected {expected_hash}, got {actual_hash}",
            )

    # Create target run directory structure
    target_run_dir.mkdir(parents=True, exist_ok=True)
    for sub in ["state", "ledger", "episodes", "resume", "artifacts"]:
        (target_run_dir / sub).mkdir(parents=True, exist_ok=True)

    # Copy files to target (preserve relative structure)
    ws_data = None
    for rel_path in files.keys():
        src_file = pack_dir / rel_path
        dst_file = target_run_dir / rel_path
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)

        # Load WS if present
        if rel_path == "state/working_set.v2.1.json":
            try:
                ws_data = json.loads(dst_file.read_text(encoding="utf-8"))
                assert_valid("working_set.v2.1.schema.json", ws_data)
            except Exception as e:
                return LoadResumePackResult(
                    ok=False, error=f"WS validation failed: {e}"
                )

    if not ws_data:
        return LoadResumePackResult(ok=False, error="working_set not found in pack")

    # Generate new run_id if not provided
    if new_run_id:
        run_id = new_run_id
    else:
        run_id = f"run_{uuid.uuid4().hex}"
        # Update WS with new run_id
        ws_data["run_id"] = run_id

    # Update target directory name if needed
    if target_run_dir.name != run_id:
        # Target was a parent directory, create run_id subdir
        final_run_dir = target_run_dir.parent / run_id
        if final_run_dir.exists():
            shutil.rmtree(final_run_dir)
        shutil.move(str(target_run_dir), str(final_run_dir))
        target_run_dir = final_run_dir
        # Update WS path
        ws_path = final_run_dir / "state" / "working_set.v2.1.json"
        ws_data["run_id"] = run_id
        ws_path.write_text(
            json.dumps(ws_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return LoadResumePackResult(ok=True, run_id=run_id, ws=ws_data)
