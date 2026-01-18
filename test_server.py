"""Quick test script for the server endpoints."""
import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_server():
    print("Testing AoS Context Server...")
    
    # Test health
    print("\n1. Testing /health")
    resp = requests.get(f"{BASE_URL}/health")
    print(f"   Status: {resp.status_code}")
    print(f"   Response: {resp.json()}")
    
    # Test create run
    print("\n2. Testing POST /runs")
    run_data = {
        "objective": "Test objective",
        "acceptance_criteria": ["Test 1", "Test 2"],
        "constraints": ["No errors"]
    }
    resp = requests.post(f"{BASE_URL}/runs", json=run_data)
    print(f"   Status: {resp.status_code}")
    result = resp.json()
    print(f"   Response: {result}")
    run_id = result.get("run_id")
    
    if not run_id:
        print("   [FAILURE] No run_id returned")
        return
    
    # Test get run
    print(f"\n3. Testing GET /runs/{run_id}")
    resp = requests.get(f"{BASE_URL}/runs/{run_id}")
    print(f"   Status: {resp.status_code}")
    ws = resp.json()
    print(f"   Status: {ws.get('status')}")
    print(f"   Objective: {ws.get('objective')}")
    expected_seq = ws.get("_update_seq", 0)
    
    # Test patch run
    print(f"\n4. Testing PATCH /runs/{run_id}")
    patch_data = {
        "patch": {"status": "BUSY", "next_action": "Testing"},
        "expected_seq": expected_seq
    }
    resp = requests.patch(f"{BASE_URL}/runs/{run_id}", json=patch_data)
    print(f"   Status: {resp.status_code}")
    result = resp.json()
    print(f"   Response: {result.get('ok')}")
    
    # Test propose memory
    print(f"\n5. Testing POST /runs/{run_id}/memory/propose")
    memory_data = {
        "mcrs": [{
            "_schema_version": "2.1",
            "op": "add",
            "type": "fact",
            "scope": "global",
            "content": "Server test memory",
            "confidence": 0.9,
            "rationale": "Test",
            "source_refs": []
        }],
        "scope_filters": {}
    }
    resp = requests.post(f"{BASE_URL}/runs/{run_id}/memory/propose", json=memory_data)
    print(f"   Status: {resp.status_code}")
    result = resp.json()
    print(f"   Response: {result}")
    batch_id = result.get("batch_id")
    
    if batch_id:
        # Test commit memory
        print(f"\n6. Testing POST /runs/{run_id}/memory/commit")
        commit_data = {"batch_id": batch_id}
        resp = requests.post(f"{BASE_URL}/runs/{run_id}/memory/commit", json=commit_data)
        print(f"   Status: {resp.status_code}")
        result = resp.json()
        print(f"   Response: {result}")
    
    # Test snapshot
    print(f"\n7. Testing POST /runs/{run_id}/snapshot")
    resp = requests.post(f"{BASE_URL}/runs/{run_id}/snapshot")
    print(f"   Status: {resp.status_code}")
    result = resp.json()
    print(f"   Response: {result}")
    
    print("\n[SUCCESS] All tests completed!")

if __name__ == "__main__":
    try:
        test_server()
    except requests.exceptions.ConnectionError:
        print("[ERROR] Server not running. Start with: python server.py")
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()

