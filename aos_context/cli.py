from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from aos_context.config import DEFAULT_CONFIG
from aos_context.context_brief import render_context_brief
from aos_context.ledger import FileLedger, utc_iso
from aos_context.memory import InMemoryMemoryStore
from aos_context.resume_pack import snapshot_resume_pack
from aos_context.ws_manager import WorkingSetManager


def main() -> None:
    p = argparse.ArgumentParser(prog="aos-context")
    sub = p.add_subparsers(dest="cmd", required=True)

    demo = sub.add_parser("demo", help="Create a demo run dir and apply one ws_patch")
    demo.add_argument("--root", default="runs", help="Root directory for runs")

    args = p.parse_args()

    if args.cmd == "demo":
        root = Path(args.root)
        run_id = f"run_{uuid.uuid4().hex}"
        run_dir = root / run_id
        (run_dir / "state").mkdir(parents=True, exist_ok=True)
        (run_dir / "ledger").mkdir(parents=True, exist_ok=True)
        (run_dir / "episodes").mkdir(parents=True, exist_ok=True)
        (run_dir / "resume").mkdir(parents=True, exist_ok=True)

        ws_path = run_dir / "state" / "working_set.v2.1.json"
        wsm = WorkingSetManager(ws_path, config=DEFAULT_CONFIG)
        ws = wsm.create_initial(
            task_id=f"task_{uuid.uuid4().hex}",
            thread_id=f"thread_{uuid.uuid4().hex}",
            run_id=run_id,
            objective="Build Context Management v2.1 scaffolding.",
            acceptance_criteria=["Schemas validate", "WS patch applies", "Ledger appends"],
            constraints=["No unknown WS fields", "Commit memory only at milestones"],
            current_stage="BOOT",
        )

        ledger = FileLedger(run_dir / "ledger" / "run.v2.1.jsonl")
        ledger.append(
            {
                "_schema_version": "2.1",
                "event_id": str(uuid.uuid4()),
                "parent_event_id": None,
                "sequence_id": None,
                "event_type": "RUN_START",
                "timestamp": utc_iso(),
                "writer_id": "cli",
                "task_id": ws["task_id"],
                "thread_id": ws["thread_id"],
                "run_id": ws["run_id"],
                "payload": {"config": {"ws_max_tokens": DEFAULT_CONFIG.ws_max_tokens}},
            }
        )

        patch = {
            "_schema_version": "2.1",
            "expected_seq": 0,
            "set": {
                "status": "BUSY",
                "current_stage": "PLAN",
                "next_action": "Generate schemas and Python skeleton.",
                "sliding_context": [
                    {
                        "id": "ctx1",
                        "content": "We use WS/RL/EP/LTM + Resume Pack.",
                        "timestamp": utc_iso(),
                        "priority": 2,
                    }
                ],
            },
        }

        r = wsm.apply_patch(patch)
        if not r.ok:
            raise SystemExit(r.error)

        brief = render_context_brief(r.new_ws or ws, ltm_results=[])
        print("\n--- Context Brief ---\n")
        print(brief)

        rp = snapshot_resume_pack(run_dir=run_dir, output_dir=run_dir / "resume", pointers={"ledger_last_seq": 1})
        if not rp.ok:
            raise SystemExit(rp.error)

        print(f"\nCreated run at: {run_dir}")
        print(f"Resume pack: {rp.pack_dir}")
        if rp.pack_zip:
            print(f"Resume pack zip: {rp.pack_zip}")


if __name__ == "__main__":
    main()
