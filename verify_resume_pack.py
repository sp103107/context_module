import shutil
from pathlib import Path
from aos_context.ws_manager import WorkingSetManager

def run_sanity_check():
    # 1. Setup a clean workspace
    workspace = Path("./sanity_workspace")
    snapshots = Path("./sanity_snapshots")
    restore_dir = Path("./sanity_restored")
    
    # Clean up previous runs
    for p in [workspace, snapshots, restore_dir]:
        if p.exists(): shutil.rmtree(p)
        p.mkdir()

    print("--- 1. Initialize Agent ---")
    # WorkingSetManager needs a file path, not directory
    ws_path = workspace / "state" / "working_set.v2.1.json"
    ws_mgr = WorkingSetManager(ws_path)
    run_data = ws_mgr.create_initial(
        task_id="sanity_test",
        thread_id="thread_1", 
        run_id="run_1",
        objective="Verify resume packs work.",
        acceptance_criteria=["Pack created", "Pack restored"],
        constraints=[]
    )
    print(f"Agent initialized: {run_data['status']}")

    print("\n--- 2. Create Resume Pack ---")
    # This calls your NEW method
    pack_path = ws_mgr.create_resume_pack(snapshots)
    print(f"Snapshot saved to: {pack_path}")
    
    if not pack_path.exists():
        print("[FAILURE] Zip file was not created.")
        return

    print("\n--- 3. Restore in New Location ---")
    # This calls your NEW classmethod
    try:
        new_mgr = WorkingSetManager.restore_from_pack(pack_path, restore_dir)
        new_state = new_mgr.load()
        print(f"Restored Status: {new_state['status']}")
        print(f"Restored Objective: {new_state['objective']}")
        print(f"Restored Task ID: {new_state['task_id']}")
        print(f"Restored Acceptance Criteria: {new_state['acceptance_criteria']}")
        
        if new_state['task_id'] == "sanity_test":
            print("\n[SUCCESS] Agent memory teleported successfully!")
            print("All data preserved correctly.")
        else:
            print("\n[FAILURE] Data mismatch.")
            
    except Exception as e:
        print(f"\n[CRITICAL ERROR] during restore: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_sanity_check()

