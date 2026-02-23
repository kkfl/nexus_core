import requests, uuid, time, sys

import os

BASE = os.getenv("AUTOMATION_AGENT_BASE", "http://localhost:8013/v1")
HEADERS = {
    "X-Service-ID": "nexus",
    "X-Agent-Key": os.getenv("NEXUS_AUTOMATION_KEY", "<REDACTED_API_KEY>"),
    "Content-Type": "application/json"
}

def trigger_and_wait(automation_id, name):
    print(f"\n--- Testing Automation: {name} ({automation_id}) ---")
    run_payload = {
        "idempotency_key": str(uuid.uuid4()),
        "tenant_id": "nexus",
        "env": "prod"
    }
    
    r2 = requests.post(f"{BASE}/automations/{automation_id}/run", headers=HEADERS, json=run_payload, timeout=5)
    if r2.status_code != 202:
        print(f"Trigger failed: {r2.status_code} {r2.text}")
        return False
        
    run_id = r2.json()["id"]
    print(f" -> Triggered run: {run_id}")
    
    for _ in range(15):
        time.sleep(2)
        r3 = requests.get(f"{BASE}/runs/{run_id}", headers=HEADERS, params={"tenant_id": "nexus", "env": "prod"}, timeout=5)
        status = r3.json().get("status")
        print(f"   Status: {status}")
        if status in ("succeeded", "failed"):
            
            r4 = requests.get(f"{BASE}/runs/{run_id}/steps", headers=HEADERS, params={"tenant_id": "nexus", "env": "prod"}, timeout=5)
            steps = r4.json()
            for s in steps:
                print(f"   Step [{s['step_id']}] status={s['status']}")
                if s.get("last_error_redacted"):
                    print(f"     Error: {s['last_error_redacted'][:150]}")
            
            return status == "succeeded"
            
    print(" -> Timed out waiting.")
    return False

def main():
    # 1. Get all automations
    r = requests.get(f"{BASE}/automations", headers=HEADERS, params={"tenant_id": "nexus", "env": "prod"}, timeout=5)
    autos = r.json()
    
    for a in autos:
        if a["name"] in ("Monitoring Targets Sync", "System Status Check", "System Status Daily Digest"):
            success = trigger_and_wait(a["id"], a["name"])
            if not success:
               print(f"FAILED to run {a['name']}")
               sys.exit(1)
               
    print("\nSUCCESS: All status automations ran successfully!")

if __name__ == "__main__":
    main()
